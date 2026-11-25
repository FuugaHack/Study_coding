# Programming Learning Platform

AIで個別最適化するプログラミング学習プラットフォーム。モノレポ構成。

リポジトリ: https://github.com/FuugaHack/Study_coding

## ブランチ運用

- `main` — リリース対象。直接 push 不可、PR 経由でのみマージ可能。force push / 削除も禁止。
- `develop` — 開発用デフォルトブランチ。日々の作業はここに乗せる。
- 機能追加は `develop` から feature ブランチを切って PR → `develop` にマージ。
- リリース時は `develop` → `main` の PR を作成してマージ。

## 構成

```
.
├── apps/
│   ├── backend/      FastAPI + SQLAlchemy + Alembic + Bedrock
│   └── frontend/     Vite + React + TypeScript + Tailwind + TanStack Query
├── packages/
│   └── shared-types/ バックエンド schemas と揃えた TS 型定義
├── docs/
└── docker-compose.yml
```

## セットアップ

```bash
# フロントエンド依存
npm install

# バックエンド依存
cd apps/backend && pip install -e .

# 起動（すべて）
docker compose up

# 個別起動
npm run dev              # フロントエンド (http://localhost:3000)
npm run backend:dev      # バックエンド  (http://localhost:8000)
```

## DB セットアップ (初回・開発用)

```bash
# Postgres を起動
docker compose up -d db

# 初期マイグレーション適用
docker compose run --rm backend alembic upgrade head

# サンプルコース・レッスン投入
docker compose run --rm backend python -m scripts.seed
```

## 開発時の自動ゲストログイン

`apps/frontend/.env.development` の `VITE_DEV_AUTO_GUEST=true` が有効な間は、
ログイン画面を経由せず `/auth/guest` を自動で叩いて新しいゲストユーザでサービスに入ります。
ログイン機能を実際に確認したくなったら `false` にしてください。

## テスト

```bash
# backend (docker compose の db を使用。learning_platform_test DB を自動作成)
docker compose exec backend pytest

# コード実行ランナー (隔離された runner コンテナの中で実行する)
docker compose exec runner pytest -q tests

# frontend
npm run typecheck --workspace apps/frontend
npm run build --workspace apps/frontend
```

CI (`.github/workflows/ci.yml`) でも同じものが PR ごとに実行されます。

## 設計ドキュメント

- [docs/expansion/01-current-state.md](docs/expansion/01-current-state.md) — 既存調査・差分・技術的負債
- [docs/expansion/02-requirements-and-architecture.md](docs/expansion/02-requirements-and-architecture.md) — 要件定義・技術選定
- [docs/expansion/03-roadmap.md](docs/expansion/03-roadmap.md) — ロードマップ
- [docs/expansion/m1-design.md](docs/expansion/m1-design.md) — M1 詳細設計 (学習エンジン + ゲーミフィケーション)
- [docs/expansion/m2-design.md](docs/expansion/m2-design.md) — M2 詳細設計 (バッジ / ステージマップ / 飛び級 / ボス戦)
- [docs/expansion/m3-design.md](docs/expansion/m3-design.md) — M3 詳細設計 (コード実行サンドボックス / AI レビュー / 段階ヒント)
- [docs/expansion/m4-design.md](docs/expansion/m4-design.md) — M4 詳細設計 (AI ワーカー / コスト計測と利用上限 / 問題品質レビュー / 構造化ログ)

学習コンテンツは `apps/backend/app/content/catalog.json` (クイズ) と `coding.json` (コーディング問題) で管理しています。
コーディング問題の模範解答は、`docker compose exec backend pytest tests/test_coding_content.py` で実際にランナー上で実行して検証されます。
問題を追加・修正したら `docker compose exec backend pytest tests/test_domain.py` で検証してください。

### AI 処理と問題品質レビュー

AI の処理 (コードレビュー・問題生成・問題品質レビュー) は API ではなく `worker` サービス (`python -m app.worker`) が実行します。
`docker compose up` で一緒に起動します。運用操作は CLI で行います。

```bash
docker compose exec backend python -m app.cli questions lint                  # 静的チェック (CI でも実行)
docker compose exec backend python -m app.cli questions enqueue               # 未レビュー・要再レビューの問題を AI レビューに登録
docker compose exec backend python -m app.cli questions report --output r.md  # レビュー結果のレポート
docker compose exec backend python -m app.cli questions dismiss <id> --note "理由"  # AI の指摘を対応不要にする
docker compose exec backend python -m app.cli usage --days 7                  # AI の使用量と費用
docker compose exec backend python -m app.cli ai check                        # Bedrock の接続確認 (1 回だけ課金される)
```

#### Bedrock (Claude) の設定

AI 機能は Claude in Amazon Bedrock (`bedrock-mantle` エンドポイント) を Anthropic SDK で呼びます。既定のモデルは `anthropic.claude-opus-5-5`、リージョンは `AWS_REGION` (既定 ap-northeast-1) です。

1. AWS コンソールの [Amazon Bedrock model access](https://console.aws.amazon.com/bedrock/home#/modelaccess) で、使うモデル (Claude Opus 5.5) を利用可能にする
2. 認証情報を `apps/backend/.env` に設定する (どちらか)
   - Amazon Bedrock API キー: `AWS_BEARER_TOKEN_BEDROCK=...` (IAM 権限 `bedrock-mantle:CallWithBearerToken` と `bedrock-mantle:CreateInference` が必要)
   - IAM の認証情報: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (権限 `bedrock-mantle:CreateInference`)
3. `docker compose up -d --force-recreate backend worker` で反映し、`python -m app.cli ai check` で確認する
4. `AI_PRICE_INPUT_PER_MTOK` / `AI_PRICE_OUTPUT_PER_MTOK` を Bedrock の価格に合わせる (費用の計算と上限に使う)

## 環境変数

- `apps/frontend/.env` — `VITE_API_BASE_URL`
- `apps/backend/.env`  — `APP_TIMEZONE` (既定 Asia/Tokyo), `AI_REVIEW_ENABLED` (AWS の認証情報がない環境では false 推奨), `RUNNER_TOKEN` (本番では必ず変更), `AI_USER_DAILY_TOKEN_LIMIT` / `AI_GLOBAL_DAILY_COST_LIMIT_USD` (AI の利用上限), `AI_PRICE_*_PER_MTOK` (費用計算の単価), `LOG_FORMAT` (json / console), `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, AWS 関連
