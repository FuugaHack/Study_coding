from datetime import date

from sqlalchemy import Boolean, case, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import QuestionAttempt, UserStats, XpEvent


class GamificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---- question attempts ----

    async def create_question_attempt(
        self,
        *,
        user_id: str,
        question_id: str,
        course_id: str,
        is_correct: bool | None,
        answer: dict,
        content_version: str,
        activity_date: date,
        time_spent_seconds: int | None,
    ) -> QuestionAttempt:
        attempt = QuestionAttempt(
            user_id=user_id,
            question_id=question_id,
            course_id=course_id,
            is_correct=is_correct,
            answer=answer,
            content_version=content_version,
            activity_date=activity_date,
            time_spent_seconds=time_spent_seconds,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def get_question_status(self, user_id: str) -> dict[str, bool]:
        """{question_id: solved} — solved は一度でも正解 (または自己チェック) したか。"""
        solved = func.bool_or(func.coalesce(QuestionAttempt.is_correct, True)).cast(Boolean)
        stmt = (
            select(QuestionAttempt.question_id, solved)
            .where(QuestionAttempt.user_id == user_id)
            .group_by(QuestionAttempt.question_id)
        )
        rows = await self.db.execute(stmt)
        return {qid: bool(ok) for qid, ok in rows.all()}

    async def count_incorrect(self, user_id: str, question_id: str) -> int:
        stmt = select(func.count()).where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.question_id == question_id,
            QuestionAttempt.is_correct.is_(False),
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def today_question_counts(self, user_id: str, today: date) -> tuple[int, int]:
        """(今日正解した異なる問題数, 今日挑戦した異なる問題数)"""
        correct_qid = case((QuestionAttempt.is_correct.is_(True), QuestionAttempt.question_id))
        stmt = select(
            func.count(distinct(correct_qid)),
            func.count(distinct(QuestionAttempt.question_id)),
        ).where(QuestionAttempt.user_id == user_id, QuestionAttempt.activity_date == today)
        correct, attempted = (await self.db.execute(stmt)).one()
        return int(correct), int(attempted)

    # ---- xp events / stats ----

    async def insert_xp_event(
        self,
        *,
        user_id: str,
        amount: int,
        coins: int,
        reason: str,
        idempotency_key: str,
        activity_date: date,
    ) -> bool:
        """冪等に XP イベントを追加する。新規に追加できたら True。"""
        stmt = (
            pg_insert(XpEvent)
            .values(
                user_id=user_id,
                amount=amount,
                coins=coins,
                reason=reason,
                idempotency_key=idempotency_key,
                activity_date=activity_date,
            )
            .on_conflict_do_nothing(constraint="uq_xp_events_user_key")
            .returning(XpEvent.id)
        )
        inserted = (await self.db.execute(stmt)).scalar_one_or_none()
        return inserted is not None

    async def has_xp_event(self, user_id: str, idempotency_key: str) -> bool:
        stmt = select(XpEvent.id).where(
            XpEvent.user_id == user_id, XpEvent.idempotency_key == idempotency_key
        )
        return (await self.db.execute(stmt)).first() is not None

    async def today_xp_excluding(self, user_id: str, today: date, excluded_reason: str) -> int:
        stmt = select(func.coalesce(func.sum(XpEvent.amount), 0)).where(
            XpEvent.user_id == user_id,
            XpEvent.activity_date == today,
            XpEvent.reason != excluded_reason,
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def completed_quest_keys(self, user_id: str, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        stmt = select(XpEvent.idempotency_key).where(
            XpEvent.user_id == user_id, XpEvent.idempotency_key.in_(keys)
        )
        return set((await self.db.execute(stmt)).scalars().all())

    async def get_stats(self, user_id: str) -> UserStats | None:
        return await self.db.get(UserStats, user_id)

    async def lock_stats(self, user_id: str) -> UserStats:
        """user_stats 行を (無ければ作成して) 行ロック付きで取得する。"""
        await self.db.execute(
            pg_insert(UserStats).values(user_id=user_id).on_conflict_do_nothing()
        )
        stmt = (
            select(UserStats)
            .where(UserStats.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(stmt)).scalar_one()
