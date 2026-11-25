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

学習コンテンツ (カタログ) は `apps/backend/app/content/catalog.json` で管理しています。
問題を追加・修正したら `docker compose exec backend pytest tests/test_domain.py` で検証してください。

## 環境変数

- `apps/frontend/.env` — `VITE_API_BASE_URL`
- `apps/backend/.env`  — `APP_TIMEZONE` (既定 Asia/Tokyo), `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, AWS 関連
