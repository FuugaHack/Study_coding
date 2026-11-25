from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gamification import CodingProgress, CodingSubmission


class CodingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def lock_progress(self, user_id: str, question_id: str) -> CodingProgress:
        await self.db.execute(
            pg_insert(CodingProgress)
            .values(user_id=user_id, question_id=question_id)
            .on_conflict_do_nothing()
        )
        stmt = (
            select(CodingProgress)
            .where(CodingProgress.user_id == user_id, CodingProgress.question_id == question_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def get_progress(self, user_id: str, question_id: str) -> CodingProgress | None:
        return await self.db.get(CodingProgress, (user_id, question_id))

    async def all_progress(self, user_id: str) -> dict[str, CodingProgress]:
        stmt = select(CodingProgress).where(CodingProgress.user_id == user_id)
        return {p.question_id: p for p in (await self.db.execute(stmt)).scalars().all()}

    async def submission_counts(self, user_id: str) -> dict[str, int]:
        stmt = (
            select(CodingSubmission.question_id, func.count())
            .where(CodingSubmission.user_id == user_id)
            .group_by(CodingSubmission.question_id)
        )
        return dict((await self.db.execute(stmt)).all())

    async def add_submission(self, submission: CodingSubmission) -> CodingSubmission:
        self.db.add(submission)
        await self.db.flush()
        return submission

    async def get_submission(
        self, submission_id: str, user_id: str, *, for_update: bool = False
    ) -> CodingSubmission | None:
        stmt = select(CodingSubmission).where(
            CodingSubmission.id == submission_id, CodingSubmission.user_id == user_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.db.execute(stmt)).scalar_one_or_none()
