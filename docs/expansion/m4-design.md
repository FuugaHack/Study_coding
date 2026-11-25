# M4 詳細設計: AI 問題品質レビュー + AI ワーカー分離 + コスト計測 + 構造化ログ

## 1. スコープ

| 項目 | この PR | 備考 |
|---|---|---|
| AI 処理のワーカー分離 | ✅ | すべての LLM 呼び出しを `python -m app.worker` に移す。API は登録して 202 を返すだけ |
| トークン・コストの計測 | ✅ | `ai_usage` に呼び出しごとに記録 |
| 利用上限 (ユーザー単位・全体) | ✅ | 1 日あたりのトークン数 (ユーザー) と費用 (全体) |
| 問題品質の静的チェック | ✅ | 決定的なルール。エラーがあれば CI が落ちる |
| 問題品質の AI レビュー | ✅ (仕組み) | 7 観点・構造化 JSON・公式ドキュメント URL 必須。結果は `question_reviews` に保存 |
| 要修正 → 修正 → 再レビューの流れ | ✅ | 問題の内容ハッシュで「古いレビュー」を検出する。運用は CLI |
| 構造化ログ (structlog) | ✅ | JSON ログ・リクエスト ID |
| 全 115 問の AI レビュー実施 | ❌ | Bedrock (有料) の利用承認が必要。承認後に CLI 1 回で実行できる (§5.5) |
| 管理画面 | ❌ | 管理者ロールが未実装のため CLI で運用する。権限設計と合わせて別 Issue |
| 参照 URL の実在確認 (HTTP アクセス) | ❌ | ワーカーから外部への通信を増やすため見送り。公式ドメインの許可リストで代替 |

## 2. 現状の問題

- `/ai/review` と `/practice/generate` は 202 とタスク ID を返す API になっているが、実際には **リクエストの中で LLM を同期実行** している (コメントに「本番では SQS ワーカーで処理」)。LLM の応答時間 (数秒〜数十秒) がそのまま API の応答時間になる。
- M3 のコード AI レビュー (`POST /coding/submissions/{id}/review`) も同期実行。
- トークン数・費用を記録していない。上限はリクエスト回数のレート制限 (`rate_limit_ai`) だけ。
- 失敗時に `str(e)` をそのまま `error_message` としてユーザーに返している (内部情報の漏えい)。
- ログは `logging.basicConfig` のテキスト出力のみ。

## 3. ワーカー (ADR-9)

**キューは既存の `async_tasks` テーブル (PostgreSQL) を使う。** 取り出しは `FOR UPDATE SKIP LOCKED`。

- 理由
  - 新しいインフラ (SQS・Celery・arq など) を増やさずに済む。
  - タスクの登録が API の DB トランザクションと一緒にコミットされるので、「登録したのにキューに入っていない」状態が起きない。
  - ステータス確認 API (`GET /ai/review/{id}` など) が既にこのテーブルを読んでいる。
- 想定規模 (1 秒に数件) では十分。規模が大きくなったら SQS に置き換えられるよう、登録・取り出しは `app/worker/queue.py` に閉じ込める。

### 3.1 状態遷移

```
pending ──(取り出し)──> processing ──> completed
   ^                        │
   └──(一時的な失敗・再試行)─┤
                            └──> failed (恒久的な失敗 / 再試行の上限)
```

| 列 (追加) | 用途 |
|---|---|
| `attempts` | 取り出された回数。`AI_TASK_MAX_ATTEMPTS` (3) に達したら failed |
| `run_after` | この時刻以降に実行する (再試行の待ち時間) |
| `locked_until` | 処理中のタスクの期限。ワーカーが落ちて期限を過ぎたら、別のワーカーが取り直す |
| `user_id` | NULL を許可 (問題レビューなどシステムのタスク) |

- 完了・失敗の書き込みは `attempts` が取り出し時と同じときだけ行う (フェンシング)。期限切れで別のワーカーが取り直した後に、古いワーカーが結果を上書きしないようにするため。
- 失敗の分類
  - `PermanentTaskError`: 利用上限超過、対象が存在しない、など。再試行しない。
  - それ以外 (LLM の一時的な失敗、出力形式の不正など): `run_after` を 5 秒 × 2^(attempts-1) 後にして再試行する。
- ユーザーに返す `error_message` は固定の日本語メッセージのみ。例外の詳細はログにだけ出す。
- タスクの種類 (`task_type`) ごとにハンドラーを登録する: `code_review` / `ai_review` (既存) / `problem_generation` (既存) / `question_review`。

### 3.2 API の変更

| API | 変更 |
|---|---|
| `POST /ai/review`、`POST /practice/generate` | 登録して 202 を返すだけになる。レスポンスの形は変えない (フロントは既にポーリングしている) |
| `POST /coding/submissions/{id}/review` | 202 + 状態 (`pending` / `processing` / `completed` / `failed`) を返す。同じ提出に対して重複登録しない |
| `GET /coding/submissions/{id}/review` | 追加。状態とレビュー結果を返す。フロントはこれをポーリングする |

`POST /coding/submissions/{id}/review` の応答形式の変更は M3 (未マージ) の API に対するもので、リリース済みの API の破壊的変更ではない。

## 4. コスト計測と利用上限

- `ai_usage` テーブル: 呼び出しごとに用途・モデル・入力/出力トークン数・費用 (USD)・ユーザー・タスクを記録する。
- 費用は設定値の単価から計算する: `AI_PRICE_INPUT_PER_MTOK` / `AI_PRICE_OUTPUT_PER_MTOK` (100 万トークンあたりの USD。既定値は Claude Sonnet 4 の公開価格 3 / 15)。
- 上限 (1 日の区切りは `APP_TIMEZONE`)
  - `AI_USER_DAILY_TOKEN_LIMIT` (既定 200,000): ユーザーごとの入力 + 出力トークン数。
  - `AI_GLOBAL_DAILY_COST_LIMIT_USD` (既定 10): システム全体の費用 (問題レビューを含む)。
- 確認するタイミングは 2 回。
  - 登録時: 超過していたら 429。
  - 実行直前 (ワーカー): 登録後に上限に達した場合は、タスクを `PermanentTaskError` で失敗させる。
- 1 回の呼び出しが上限を少し超えることはある (呼び出す前には使用量が分からないため)。最大で `BEDROCK_MAX_TOKENS` 分の超過。
- 使用量は LLM の応答直後に別トランザクションでコミットする。その後の処理が失敗しても、費用の記録は残る。
- `python -m app.cli usage` で日別・用途別の集計を表示する。

## 5. 問題品質レビュー

### 5.1 二段構え

| 段階 | 内容 | 実行 |
|---|---|---|
| 静的チェック | 決定的なルール (下表)。`error` があれば CI が落ちる | `python -m app.cli questions lint` / pytest |
| AI レビュー | 7 観点を LLM が評価し、公式ドキュメントを根拠に示す | `python -m app.cli questions enqueue` → ワーカー |

静的チェックのルール:

| ルール | 重要度 |
|---|---|
| 解説が空 | error |
| 選択肢の重複・空の選択肢 | error |
| 正解の文字列が問題文にそのまま含まれている (選択式) | warning |
| 解説が短い (20 文字未満) | warning |
| 複数選択なのに正解が 1 つ | warning |
| 類似した問題がある (文字 bigram の Jaccard 係数。多くの問題に共通する定型句は除外) | warning |

### 5.2 AI レビューの観点

| key | 観点 |
|---|---|
| `accuracy` | 問題文・選択肢の技術的な正確性 |
| `answer_validity` | 正解と解説の妥当性 |
| `multiple_answers` | 正解が複数ありうる、または正解がない |
| `outdated` | 技術情報の陳腐化 (非推奨の API・古いバージョン前提) |
| `difficulty` | 難易度の妥当性 (提案する難易度を返す) |
| `duplication` | 重複・類似 (静的チェックで見つけた類似候補を LLM に渡す) |
| `wording` | 誤字・曖昧な表現 |

出力は pydantic で検証し、指摘ごとに重要度 (`low` / `medium` / `high`)・修正案・根拠 URL を持つ。

### 5.3 判定 (`apply_quality_guard`)

LLM の判定をそのまま使わず、次の規則で状態を決める。

| 条件 | 状態 |
|---|---|
| `medium` 以上の指摘がある (LLM が「問題なし」と言っても) | `needs_fix` (要修正) |
| 根拠 URL の中に公式ドキュメント (許可リストのドメイン) が 1 つもない | `unverified` (人の確認が必要) |
| 上記以外 | `passed` |

- 根拠 URL は `https` のみを受け付ける。許可リスト外の URL は「非公式」として印を付けて残す。
- LLM が存在しない URL を作る可能性は残る。許可リストのドメインに限ることで、少なくとも出典の種類は保証する。実在確認は今後の課題 (§1)。

### 5.4 保存と「最新のレビュー」

- `question_reviews`: 問題 ID・**内容ハッシュ**・状態・結果 (JSON)・モデル・タスク ID・人による判断 (`dismissed` とメモ)。履歴として追記していく。
- 内容ハッシュ = 問題 1 問分の JSON (キー順を正規化) の SHA-256 先頭 16 文字。
- 問題ごとの現在の状態:

| 状態 | 意味 |
|---|---|
| `unreviewed` | AI レビューが一度もない |
| `stale` | レビューはあるが、その後に問題が修正された (ハッシュ不一致) |
| `passed` / `needs_fix` / `unverified` | 現在の内容に対する最新レビューの結果 |
| `dismissed` | AI の指摘を人が確認し、対応不要と判断した (メモ必須) |

### 5.5 運用の流れ

```
lint (CI) ─> enqueue --stale ─> worker ─> report
                                   │
                    needs_fix ─> catalog.json を修正 (PR) ─> ハッシュが変わり stale ─> enqueue --stale
                    AI の誤り ─> dismiss <review_id> --note "..."
```

```bash
docker compose exec backend python -m app.cli questions lint
docker compose exec backend python -m app.cli questions enqueue --stale   # unreviewed + stale
docker compose exec backend python -m app.cli questions report --output review-report.md
docker compose exec backend python -m app.cli questions dismiss <review_id> --note "理由"
docker compose exec backend python -m app.cli usage --days 7
```

- 要修正の問題も学習者には表示し続ける (非表示にすると進捗率やクエストの計算が変わるため)。修正はコンテンツの PR で行う。
- コンテンツ (`catalog.json`) の問題に任意で `references` (参考 URL) を持たせられるようにし、AI レビューに渡す。

## 6. 構造化ログ

- `app/core/logging.py` で structlog を設定する。`LOG_FORMAT=json` (既定) / `console` (開発用)。
- リクエストごとに `X-Request-ID` (受け取るか生成する) をログに付け、レスポンスヘッダーにも返す。
- ワーカーはタスク ID・種類・試行回数・所要時間・トークン数・費用をログに出す。
- **ユーザーのコード・プロンプト・LLM の出力はログに出さない** (個人の回答内容のため)。

## 7. LLM の呼び出し (Bedrock)

- Anthropic SDK の `AsyncAnthropicBedrockMantle` で Claude in Amazon Bedrock (`bedrock-mantle` エンドポイント、Messages API 形式) を呼ぶ。旧実装の boto3 `invoke_model` (`bedrock-runtime`) からの置き換え。
- 既定モデルは `anthropic.claude-opus-5-5`。思考は常に有効で、深さは `AI_EFFORT` (既定 medium) で調整する。`temperature` などのサンプリング設定は現行モデルでは 400 になるため送らない。
- SDK の再試行は 0 回にし、再試行はワーカーに任せる (呼び出しごとに使用量を記録するため)。
- エラーの扱い: 401 / 403 / 404 / 400 と認証情報なしは「設定の誤り」として再試行せずに失敗にする。429 / 5xx / 通信失敗は再試行する。`stop_reason` が `refusal` / `max_tokens` のときは出力不正として再試行する。
- 入力トークン数にはキャッシュの読み書き分も含める (費用はやや多めに見積もられる)。

## 8. 設定値

| 変数 | 既定 | 説明 |
|---|---|---|
| `AI_WORKER_CONCURRENCY` | 2 | ワーカー 1 プロセスの同時処理数 |
| `AI_WORKER_POLL_INTERVAL_S` | 1.0 | 空のときの待ち時間 |
| `AI_TASK_TIMEOUT_S` | 180 | 1 タスクの制限時間 (`locked_until` にも使う) |
| `AI_TASK_MAX_ATTEMPTS` | 3 | 再試行を含む最大実行回数 |
| `BEDROCK_MODEL_ID` | anthropic.claude-opus-5-5 | Bedrock のモデル ID |
| `BEDROCK_MAX_TOKENS` | 16000 | 出力の上限 (思考を含む) |
| `AI_EFFORT` | medium | 思考の深さ |
| `AI_PRICE_INPUT_PER_MTOK` / `AI_PRICE_OUTPUT_PER_MTOK` | 4.0 / 20.0 | 単価 (USD / 100 万トークン)。Bedrock の価格に合わせる |
| `AI_USER_DAILY_TOKEN_LIMIT` | 200000 | ユーザーごとの 1 日の上限 |
| `AI_GLOBAL_DAILY_COST_LIMIT_USD` | 10.0 | 全体の 1 日の上限 |
| `LOG_FORMAT` / `LOG_LEVEL` | json / INFO | ログ |
