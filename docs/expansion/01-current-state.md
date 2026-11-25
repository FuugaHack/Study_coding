# 01. 既存システム調査・差分・技術的負債

調査日: 2026-11-25 / 対象: `develop` (8f0238e)

## 1. 現状アーキテクチャ

```
apps/frontend   Vite + React 18 + TS + Tailwind + TanStack Query + Zustand + Monaco
apps/backend    FastAPI + SQLAlchemy 2 (async) + Alembic + PostgreSQL16 + Redis7 + Bedrock(Claude)
packages/shared-types   backend schemas と手動同期する TS 型
docker-compose  db / redis / backend / frontend (dev)
```

レイヤー: `api (router) → services → repositories → models`。DI は `app/dependencies.py`。

## 2. 機能ごとの実装状況

| 領域 | 状態 | 実体 |
|---|---|---|
| 認証 (登録/ログイン/ゲスト/リフレッシュ) | ✅ 実装済 | JWT access+refresh。`/auth/*` |
| DB コース/レッスン (3コース/7レッスン) | ⚠️ API はあるがナビから到達不可 | `/courses`, `LessonPage` |
| **カタログ (28コース/115問)** | ⚠️ **フロント静的データ** | `apps/frontend/src/data/catalog.ts`。正解がクライアントに同梱・採点もクライアント・進捗は保存されない |
| コーディング (Repository→Issue→Editor UI) | ⚠️ 静的データ + 実行なし | `data/codingCatalog.ts` |
| コード採点 | ❌ ダミー | `course_service._grade`: 提出があれば一律 50 点 |
| AI コードレビュー | 🟡 同期実行 | `/ai/review`。観点は正確性/効率/可読性/BP。構造化出力なし |
| AI 問題生成 | 🟡 同期実行 | `/practice/generate`。品質レビューなし・重複検出なし |
| 復習レコメンド | 🟡 | `/recommend/review`。誤答/経過日数/苦手タグでスコアリング |
| 苦手タグ集計 | 🟡 | `user_weakness_profiles`。DB レッスン提出時のみ更新 |
| 学習ストリーク | 🟡 記録のみ | `learning_streaks` に日次集計を保存するが連続日数の算出・表示なし。日付は UTC |
| XP / レベル / クエスト / バッジ | ❌ なし | |
| スキルツリー / 解放 | ❌ 見た目のみ | カタログの `status: "locked"` は静的値。解放条件なし |
| 資格対策 / 用語学習 / 実践プロジェクト / キャリア | ❌ なし | |
| モバイル | ❌ なし | |
| テスト / CI | ❌ なし | `tests/` も `.github/workflows` も無い |

## 3. 追加要件との差分 (要約)

| 要件 | 既存で流用できるもの | 不足 |
|---|---|---|
| 1. AI 問題/回答レビュー | `BedrockService`, `AIReviewService`, `async_tasks` | 問題品質レビューの保存/再レビュー、構造化評価、段階ヒント、テストケース実行 (サンドボックス) |
| 2. 開発工程の実践学習 | カタログの practice カテゴリ (3コース/6問) | 18 工程のコース、架空クライアント案件モード、AI ロールプレイ |
| 3. モダン技術コンテンツ | 28 コース | Go/Rust/Kotlin/Swift/GraphQL/K8s/Terraform/MCP 等 |
| 4. 資格対策 | 復習レコメンド (簡易) | 試験範囲マスタ、模試、タイマー、SRS、学習計画 |
| 5. 用語学習 | なし | 用語マスタ、フラッシュカード/マッチング |
| 6. ゲーミフィケーション | `learning_streaks` | XP/レベル/ストリーク計算/クエスト/バッジ/スキルツリー/フレンド |
| 7. パーソナライズ | weakness, recommendation | 実力診断、ロードマップ生成、AI メンターチャット |
| 8. モバイル | shared-types | Expo アプリ、プッシュ通知、オフライン |
| 9. UI/UX | Tailwind + アニメーション一部 | マスコット、正解演出、ダークモード、a11y |
| 10. 非機能 | レート制限、セキュリティヘッダ | テスト/CI、構造化ログ、AI コスト計測、コンテンツのバージョン管理、サンドボックス |

## 4. 課題・技術的負債 (優先度順)

| # | 課題 | 影響 | 対応 |
|---|---|---|---|
| D1 | **学習コンテンツがフロント静的データ。正解がブラウザに露出し、進捗が保存されない** | ゲーミフィケーション/パーソナライズ/モバイル同期の前提が成立しない | **M1** でサーバー移行 |
| D2 | コンテンツが 2 系統 (DB `courses/lessons` と静的カタログ) | 重複実装・どちらが正か不明 | M1 でカタログを正とし、DB コースは M3 で統合判断 |
| D3 | テスト・CI が無い | 回帰を検知できない | **M1** で pytest + GitHub Actions 導入 |
| D4 | コード採点がダミー (一律 50 点) | 学習結果が嘘になる | M3: サンドボックス実行 |
| D5 | `LessonDetailResponse` が `content` を丸ごと返す (`correct_index` 含む) | 正解の露出 | M3 (DB レッスン統合時) |
| D6 | AI 呼び出しが API リクエスト内で同期実行 (`async_tasks` はあるがワーカー無し) | 最大 60s × リトライでリクエスト占有 | M4: BackgroundTasks → 将来 SQS |
| D7 | ストリーク日付が UTC | JST 0〜9 時の学習が前日扱い | M1 で `APP_TIMEZONE` 導入 |
| D8 | モデルの一部が PG 固有型 (`ARRAY`, `JSONB`) を直接使用、他は `GUID`/`JSONType` | SQLite でのテスト不可・一貫性なし | テストは PostgreSQL で実施 (M1)。型統一は随時 |
| D9 | `shared-types` は手動同期 | 型ズレ | M5 で OpenAPI → TS 自動生成を検討 |
| D10 | `docs/architecture_design.md` の記述 (SQS/ECS 等) と実装の乖離 | 誤解 | 本ドキュメント群を正とする |
| D11 | AI 利用コスト・トークンの計測がない | コスト管理不可 | M4 |
| D12 | README の `npm install` で npm 11 が lockfile を書き換える | ノイズ | `engines`/`packageManager` 固定を検討 |
