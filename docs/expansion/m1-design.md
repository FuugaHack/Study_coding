# M1 詳細設計: 学習エンジン + ゲーミフィケーション基盤

## 1. コンテンツ

- ファイル: `apps/backend/app/content/catalog.json` (Git 管理)
- 読み込み: `app/content/loader.py` が起動時に 1 回ロードし pydantic で検証。ファイルの SHA-256 先頭 12 文字を `content_version` とする。
- 検証ルール: 問題 ID の一意性、`prerequisites` が存在するコースを指し循環しないこと、choice の正解が選択肢に含まれること、code の穴の数 (`___`) と正解数が一致すること。違反時は起動失敗 (テストでも検出)。

## 2. DB (migration `0002_gamification`)

```
question_attempts
  id UUID PK, user_id FK users CASCADE, question_id varchar(100), course_id varchar(100),
  is_correct bool NULL (text 型の自己チェックは NULL), answer JSONB,
  content_version varchar(20), time_spent_seconds int NULL, attempted_at timestamptz
  INDEX (user_id, attempted_at), INDEX (user_id, question_id)

user_stats
  user_id UUID PK FK users CASCADE, total_xp int, coins int,
  current_streak int, longest_streak int, last_active_date date NULL, updated_at timestamptz

xp_events
  id UUID PK, user_id FK users CASCADE, amount int, coins int,
  reason varchar(30), idempotency_key varchar(150), created_at timestamptz,
  activity_date date,  -- APP_TIMEZONE 基準の日付
  UNIQUE (user_id, idempotency_key), INDEX (user_id, activity_date)
```

## 3. 報酬ルール

| イベント | XP | 冪等キー |
|---|---|---|
| 問題に初めて正解 | easy 10 / normal 15 / hard 20 | `q:{question_id}:first` |
| 正解済み問題の再正解 (復習) | 2 (1 問 1 日 1 回) | `q:{question_id}:review:{date}` |
| text 型の自己チェック (初回・空欄でない回答) | 5 | `q:{question_id}:first` |
| DB レッスン初回正解 | 20 | `lesson:{lesson_id}:first` |
| デイリークエスト達成 | クエスト毎 (+コイン 5) | `quest:{quest_id}:{date}` |

- 不正解では減点しない。
- text 型を空欄のまま「解答例を見る」と、解答例は表示するが回答としては記録しない (XP なし・未解決・クエスト進捗にも数えない)。
- 正解が表示された後 (同じ問題で 2 回以上不正解) の初回正解は、満額ではなく復習 XP (2) とする。
- 同時実行: 回答処理の冒頭で `user_stats` 行をロックし、同一ユーザーの回答を直列化する。ロック順は常に `user_stats → xp_events`。
- レベル: レベル L に必要な累計 XP = `25 × L × (L − 1)` (L2=50, L3=150, L4=300, L5=500 …)。
- ストリーク: 当日初めて XP を得たときに更新。`last_active_date` が昨日なら +1、今日なら維持、それ以外は 1 にリセット。表示時は「昨日まで続いていて今日まだ」の場合も継続扱い (途切れるのは日付が 2 日以上空いたとき)。

## 4. デイリークエスト (コード定義)

| ID | 内容 | 目標 | 報酬 |
|---|---|---|---|
| `daily_correct_3` | 今日 3 問正解する | 3 | 15 XP + 5 コイン |
| `daily_attempt_5` | 今日 5 問に挑戦する (異なる問題) | 5 | 10 XP + 5 コイン |
| `daily_xp_50` | 今日 50 XP 獲得する (クエスト報酬を除く) | 50 | 20 XP + 5 コイン |

進捗は当日の `question_attempts` / `xp_events` から算出。回答処理の最後に達成判定し、達成済みなら冪等キー付きで報酬を付与。

## 5. コース解放

- `prerequisites` の全コースが「クリア」(問題の 70% 以上を一度でも正解 / text は自己チェック済み) なら解放。
- 進捗率 = 解いた問題数 / 全問題数。`status`: `locked` / `not-started` / `in-progress` / `completed` (100%)。
- ロック中のコースの問題に回答した場合は 403。

## 6. API

| Method | Path | 説明 |
|---|---|---|
| GET | `/api/v1/catalog/courses` | コース一覧 + ユーザー進捗 (問題は含まない) |
| GET | `/api/v1/catalog/courses/{course_id}` | コース詳細 + 問題 (正解・解説・解答例を除く) + 解答済み問題 ID |
| POST | `/api/v1/catalog/questions/{question_id}/answer` | 採点・記録・報酬付与。レスポンスに正誤・解説・正解・報酬 |
| GET | `/api/v1/gamification/me` | レベル/XP/ストリーク/コイン/今日のクエスト |

回答レスポンス例:
```json
{
  "question_id": "q-html-heading",
  "result": "correct",               // correct | incorrect | self_check
  "correct_answer": "<h1>",
  "explanation": "...",
  "reward": {
    "xp_gained": 25, "coins_gained": 5,
    "total_xp": 175, "level": 3, "leveled_up": true,
    "current_streak": 4,
    "completed_quests": [{"id": "daily_correct_3", "title": "今日 3 問正解する", "reward_xp": 15}]
  },
  "stats": { ... GET /gamification/me と同じ ... }
}
```

不正解時の正解表示: 1 回目の不正解では `correct_answer` を返さず「もう一度」を促す (段階ヒントの第一歩)。2 回目以降の不正解、または正解時に正解を返す。

## 7. フロントエンド

- `src/data/catalog.ts` の静的データを削除し `src/api/catalog.ts` に置換。
- `QuestionItem` は回答を API に送り、結果で表示を切り替える。
- `GamificationBar` (ヘッダー): レベル・XP バー・🔥ストリーク・🪙コイン。
- `RewardToast`: +XP / レベルアップ / クエスト達成の演出 (`prefers-reduced-motion` を尊重)。
- ダッシュボード: レベル進捗カード + 今日のクエスト。
