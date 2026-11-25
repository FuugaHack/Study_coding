"""テスト共通設定。

テストは実 PostgreSQL に対して実行する (ADR-8)。
接続先は TEST_DATABASE_URL (既定: docker compose の db サービス上の learning_platform_test)。
DB が無ければ作成し、セッション開始時にスキーマを作り直す。
"""
import asyncio
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# テストは開発用とは別の Redis DB 番号を使う (app.config の読み込みより前に設定する)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://redis:6379/15")

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:password@db:5432/learning_platform_test",
)


async def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


async def _reset_schema() -> None:
    from app.models import Base

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    asyncio.run(_ensure_database())
    asyncio.run(_reset_schema())


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from app.models import Base

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # テスト間の独立性: 全テーブルを空にする
    async with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    await engine.dispose()


@pytest.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    from app.db.session import get_db
    from app.main import app

    async def _get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """ゲストユーザーでログイン済みのクライアント。"""
    res = await client.post("/api/v1/auth/guest")
    assert res.status_code == 201, res.text
    client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
    return client


@pytest.fixture(autouse=True)
async def _fresh_redis_pool():
    """テストごとにイベントループが変わるため、ループに紐づく Redis 接続を作り直す。"""
    from app.core import rate_limit

    rate_limit._pool = None
    yield
    if rate_limit._pool is not None:
        # 同じ Redis を共有するテスト間でレート制限のカウントが残らないようにする
        await rate_limit._pool.flushdb()
        await rate_limit._pool.aclose()
        rate_limit._pool = None
