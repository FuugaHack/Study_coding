from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/learning_platform"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # AI の呼び出し先: anthropic (Claude API を直接) / bedrock (Claude in Amazon Bedrock)
    AI_PROVIDER: str = "bedrock"

    # Claude API (AI_PROVIDER=anthropic のとき)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL_ID: str = "claude-opus-5-5"

    # AWS
    AWS_REGION: str = "ap-northeast-1"
    # Claude in Amazon Bedrock (bedrock-mantle) のモデル ID。anthropic. の接頭辞が付く
    BEDROCK_MODEL_ID: str = "anthropic.claude-opus-5-5"
    # 出力の上限 (思考を含む)。現行モデルは思考が常に有効なので小さくしすぎない
    BEDROCK_MAX_TOKENS: int = 16000
    # 思考の深さ: low / medium / high / xhigh / max
    AI_EFFORT: str = "medium"
    # Amazon Bedrock API キー。空なら AWS の認証情報チェーン (AWS_ACCESS_KEY_ID など) を使う。
    # .env の値は os.environ に入らないので、ここで受けてクライアントへ明示的に渡す
    AWS_BEARER_TOKEN_BEDROCK: str = ""

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # 学習日付の境界 (ストリーク・デイリークエスト)
    APP_TIMEZONE: str = "Asia/Tokyo"

    # コード実行ランナー (apps/runner)
    RUNNER_SOCKET: str = "/sock/runner.sock"
    RUNNER_TOKEN: str = "change-me-runner-token"
    RUNNER_RATE_LIMIT_PER_MINUTE: int = 20

    # AI レビュー。false にすると AI 機能は 503 を返す (認証情報がない開発環境など)
    AI_REVIEW_ENABLED: bool = True

    # AI ワーカー (docs/expansion/m4-design.md §3)
    AI_WORKER_CONCURRENCY: int = 2
    AI_WORKER_POLL_INTERVAL_S: float = 1.0
    AI_TASK_TIMEOUT_S: int = 180
    AI_TASK_MAX_ATTEMPTS: int = 3

    # AI の費用計測と利用上限 (単価は USD / 100 万トークン)
    # 既定値は Claude Opus 5.5 の Anthropic 公開価格。
    # Bedrock の価格 (リージョン指定のエンドポイントは +10%) に合わせて設定する
    AI_PRICE_INPUT_PER_MTOK: float = 4.0
    AI_PRICE_OUTPUT_PER_MTOK: float = 20.0
    AI_USER_DAILY_TOKEN_LIMIT: int = 200_000
    AI_GLOBAL_DAILY_COST_LIMIT_USD: float = 10.0

    # ログ: json (本番) / console (開発)
    LOG_FORMAT: str = "json"
    LOG_LEVEL: str = "INFO"

    # Rate Limiting
    AI_RATE_LIMIT_PER_MINUTE: int = 10
    AI_RATE_LIMIT_PER_HOUR: int = 100

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
