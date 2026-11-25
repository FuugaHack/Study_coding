from datetime import date, datetime

from sqlalchemy import Boolean, case, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import (
    ChallengeSession,
    CourseAchievement,
    QuestionAttempt,
    UserBadge,
    UserStats,
    XpEvent,
)


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

    async def period_question_counts(
        self, user_id: str, start: date, end: date
    ) -> tuple[int, int]:
        """期間内の (正解した異なる問題数, 挑戦した異なる問題数)"""
        correct_qid = case((QuestionAttempt.is_correct.is_(True), QuestionAttempt.question_id))
        stmt = select(
            func.count(distinct(correct_qid)),
            func.count(distinct(QuestionAttempt.question_id)),
        ).where(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.activity_date.between(start, end),
        )
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

    async def period_xp_excluding(
        self, user_id: str, start: date, end: date, excluded_reason: str
    ) -> int:
        stmt = select(func.coalesce(func.sum(XpEvent.amount), 0)).where(
            XpEvent.user_id == user_id,
            XpEvent.activity_date.between(start, end),
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

    async def active_days(self, user_id: str, start: date, end: date) -> int:
        """XP を得た日数 (コインの消費などは除く)。"""
        stmt = select(func.count(distinct(XpEvent.activity_date))).where(
            XpEvent.user_id == user_id,
            XpEvent.activity_date.between(start, end),
            XpEvent.amount > 0,
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def count_xp_events(self, user_id: str, reason: str) -> int:
        stmt = select(func.count()).where(XpEvent.user_id == user_id, XpEvent.reason == reason)
        return int((await self.db.execute(stmt)).scalar_one())

    # ---- badges ----

    async def owned_badges(self, user_id: str) -> dict[str, datetime]:
        stmt = select(UserBadge.badge_id, UserBadge.earned_at).where(UserBadge.user_id == user_id)
        return dict((await self.db.execute(stmt)).all())

    async def insert_badge(self, user_id: str, badge_id: str) -> bool:
        stmt = (
            pg_insert(UserBadge)
            .values(user_id=user_id, badge_id=badge_id)
            .on_conflict_do_nothing()
            .returning(UserBadge.badge_id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    # ---- course achievements ----

    async def course_achievements(self, user_id: str) -> dict[str, set[str]]:
        stmt = select(CourseAchievement.course_id, CourseAchievement.kind).where(
            CourseAchievement.user_id == user_id
        )
        result: dict[str, set[str]] = {}
        for course_id, kind in (await self.db.execute(stmt)).all():
            result.setdefault(course_id, set()).add(kind)
        return result

    async def insert_achievement(self, user_id: str, course_id: str, kind: str) -> bool:
        stmt = (
            pg_insert(CourseAchievement)
            .values(user_id=user_id, course_id=course_id, kind=kind)
            .on_conflict_do_nothing()
            .returning(CourseAchievement.kind)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    # ---- challenge sessions ----

    async def create_challenge(self, session: ChallengeSession) -> ChallengeSession:
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_challenge(self, challenge_id: str, user_id: str) -> ChallengeSession | None:
        stmt = (
            select(ChallengeSession)
            .where(ChallengeSession.id == challenge_id, ChallengeSession.user_id == user_id)
            .with_for_update()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def count_challenges(
        self, user_id: str, course_id: str, mode: str, on_date: date
    ) -> int:
        stmt = select(func.count()).where(
            ChallengeSession.user_id == user_id,
            ChallengeSession.course_id == course_id,
            ChallengeSession.mode == mode,
            ChallengeSession.activity_date == on_date,
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def in_open_challenge(self, user_id: str, question_id: str, since: datetime) -> bool:
        """question_id を含む、受験中 (未提出かつ期限内) のチャレンジがあるか。"""
        stmt = select(ChallengeSession.id).where(
            ChallengeSession.user_id == user_id,
            ChallengeSession.status == "open",
            ChallengeSession.expires_at > since,
            ChallengeSession.question_ids.contains([question_id]),
        )
        return (await self.db.execute(stmt.limit(1))).first() is not None

    async def bosses_defeated(self, user_id: str, start: date, end: date) -> int:
        stmt = select(func.count()).where(
            ChallengeSession.user_id == user_id,
            ChallengeSession.mode == "boss",
            ChallengeSession.status == "passed",
            ChallengeSession.activity_date.between(start, end),
        )
        return int((await self.db.execute(stmt)).scalar_one())

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
