"""AI の使用量 (トークン・費用) の記録と利用上限 (docs/expansion/m4-design.md §4)。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.exceptions import RateLimitError
from app.core.logging import get_logger
from app.models.ai_ops import AiUsage
from app.services.llm import LLMClient, LLMResponse

logger = get_logger(__name__)

_MTOK = Decimal(1_000_000)


class BudgetExceededError(RateLimitError):
    pass


def cost_usd(input_tokens: int, output_tokens: int) -> Decimal:
    cost = (
        Decimal(input_tokens) * Decimal(str(settings.AI_PRICE_INPUT_PER_MTOK))
        + Decimal(output_tokens) * Decimal(str(settings.AI_PRICE_OUTPUT_PER_MTOK))
    ) / _MTOK
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def day_start_utc(now: datetime | None = None) -> datetime:
    """APP_TIMEZONE での「今日」の 0 時 (UTC)。"""
    tz = ZoneInfo(settings.APP_TIMEZONE)
    local = (now or datetime.now(UTC)).astimezone(tz)
    return datetime.combine(local.date(), time.min, tzinfo=tz).astimezone(UTC)


def _as_uuid(user_id: str | uuid.UUID | None) -> uuid.UUID | None:
    if user_id is None or isinstance(user_id, uuid.UUID):
        return user_id
    return uuid.UUID(user_id)


async def check_budget(db: AsyncSession, user_id: str | uuid.UUID | None) -> None:
    """今日の使用量が上限に達していたら BudgetExceededError。

    user_id が None (システムのタスク) のときは全体の上限だけを確認する。
    """
    since = day_start_utc()
    global_cost = await db.scalar(
        select(func.coalesce(func.sum(AiUsage.cost_usd), 0)).where(AiUsage.created_at >= since)
    )
    if Decimal(global_cost) >= Decimal(str(settings.AI_GLOBAL_DAILY_COST_LIMIT_USD)):
        logger.warning("ai_global_budget_exceeded", cost_usd=str(global_cost))
        raise BudgetExceededError(
            "AI 機能の本日の利用枠に達しました。明日になってからもう一度お試しください"
        )
    uid = _as_uuid(user_id)
    if uid is None:
        return
    user_tokens = await db.scalar(
        select(func.coalesce(func.sum(AiUsage.input_tokens + AiUsage.output_tokens), 0)).where(
            AiUsage.user_id == uid, AiUsage.created_at >= since
        )
    )
    if int(user_tokens) >= settings.AI_USER_DAILY_TOKEN_LIMIT:
        raise BudgetExceededError(
            "本日の AI 機能の利用上限に達しました。明日になってからもう一度お試しください"
        )


async def record_usage(
    db: AsyncSession,
    *,
    user_id: str | uuid.UUID | None,
    task_id: str | uuid.UUID | None,
    purpose: str,
    response: LLMResponse,
) -> AiUsage:
    row = AiUsage(
        user_id=_as_uuid(user_id),
        task_id=_as_uuid(task_id),
        purpose=purpose,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=cost_usd(response.input_tokens, response.output_tokens),
    )
    db.add(row)
    await db.flush()
    return row


async def usage_summary(db: AsyncSession, days: int = 7) -> list[dict]:
    """日別 (APP_TIMEZONE)・用途別の使用量。"""
    tz = settings.APP_TIMEZONE
    since = day_start_utc() - timedelta(days=days - 1)
    day = func.date(func.timezone(tz, AiUsage.created_at)).label("day")
    rows = await db.execute(
        select(
            day,
            AiUsage.purpose,
            func.count().label("calls"),
            func.sum(AiUsage.input_tokens).label("input_tokens"),
            func.sum(AiUsage.output_tokens).label("output_tokens"),
            func.sum(AiUsage.cost_usd).label("cost_usd"),
        )
        .where(AiUsage.created_at >= since)
        .group_by(day, AiUsage.purpose)
        .order_by(day, AiUsage.purpose)
    )
    return [
        {
            "day": r.day if isinstance(r.day, date) else r.day,
            "purpose": r.purpose,
            "calls": r.calls,
            "input_tokens": int(r.input_tokens),
            "output_tokens": int(r.output_tokens),
            "cost_usd": Decimal(r.cost_usd),
        }
        for r in rows
    ]


class MeteredLLM:
    """利用上限の確認 → LLM 呼び出し → 使用量の記録 をまとめたもの (ワーカー専用)。

    使用量はその後の処理が失敗しても残るよう、応答の直後に別トランザクションでコミットする。
    DB のロックは LLM の呼び出し中に持たない。
    """

    def __init__(self, llm: LLMClient, session_factory: async_sessionmaker[AsyncSession]):
        self.llm = llm
        self.session_factory = session_factory

    async def complete(
        self,
        *,
        purpose: str,
        user_id: str | uuid.UUID | None,
        task_id: str | uuid.UUID | None,
        system_prompt: str,
        user_message: str,
    ) -> LLMResponse:
        async with self.session_factory() as db:
            await check_budget(db, user_id)

        async def call_and_record() -> LLMResponse:
            response = await self.llm.complete(system_prompt, user_message)
            async with self.session_factory() as db:
                usage = await record_usage(
                    db, user_id=user_id, task_id=task_id, purpose=purpose, response=response
                )
                await db.commit()
            logger.info(
                "llm_call",
                purpose=purpose,
                model=response.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=str(usage.cost_usd),
            )
            return response

        # タスクが時間切れで中断されても、LLM の呼び出し (別スレッドで続き、課金される) が
        # 終わったら使用量を記録する。shield しないと記録されずに利用上限をすり抜ける
        return await asyncio.shield(asyncio.ensure_future(call_and_record()))
