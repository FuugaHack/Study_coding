"""PostgreSQL の async_tasks をキューとして使う (docs/expansion/m4-design.md §3, ADR-9)。

- 登録は API の DB トランザクションと一緒にコミットされる
- 取り出しは FOR UPDATE SKIP LOCKED。複数のワーカーが同じタスクを取らない
- 処理中のタスクには期限 (locked_until) を付け、ワーカーが落ちても別のワーカーが取り直す
- 完了・失敗の書き込みは attempts が取り出し時と同じときだけ行う (フェンシング)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.async_task import AsyncTask, TaskStatus

TIMEOUT_MESSAGE = "AI の処理が時間内に終わりませんでした。もう一度お試しください"


@dataclass(frozen=True)
class ClaimedTask:
    id: uuid.UUID
    task_type: str
    user_id: uuid.UUID | None
    input_data: dict
    attempts: int


async def enqueue(
    db: AsyncSession, *, task_type: str, user_id: str | uuid.UUID | None, input_data: dict
) -> AsyncTask:
    """タスクを登録する (コミットは呼び出し側のトランザクションで行う)。"""
    task = AsyncTask(
        id=uuid.uuid4(),
        user_id=uuid.UUID(str(user_id)) if user_id is not None else None,
        task_type=task_type,
        status=TaskStatus.pending,
        input_data=input_data,
    )
    db.add(task)
    await db.flush()
    return task


async def fail_exhausted(db: AsyncSession) -> int:
    """期限切れで、再試行の上限に達した処理中タスクを失敗にする。"""
    res = await db.execute(
        update(AsyncTask)
        .where(
            AsyncTask.status == TaskStatus.processing,
            AsyncTask.locked_until < func.now(),
            AsyncTask.attempts >= settings.AI_TASK_MAX_ATTEMPTS,
        )
        .values(status=TaskStatus.failed, error_message=TIMEOUT_MESSAGE, completed_at=func.now())
        .execution_options(synchronize_session=False)
    )
    return res.rowcount or 0


async def claim(db: AsyncSession) -> ClaimedTask | None:
    """実行できるタスクを 1 件取り出し、processing にする。"""
    now = func.now()
    candidate = (
        select(AsyncTask.id)
        .where(
            or_(
                and_(AsyncTask.status == TaskStatus.pending, AsyncTask.run_after <= now),
                and_(
                    AsyncTask.status == TaskStatus.processing,
                    AsyncTask.locked_until < now,
                    AsyncTask.attempts < settings.AI_TASK_MAX_ATTEMPTS,
                ),
            )
        )
        .order_by(AsyncTask.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    res = await db.execute(
        update(AsyncTask)
        .where(AsyncTask.id == candidate)
        .values(
            status=TaskStatus.processing,
            attempts=AsyncTask.attempts + 1,
            started_at=now,
            locked_until=now + timedelta(seconds=settings.AI_TASK_TIMEOUT_S),
        )
        .returning(
            AsyncTask.id,
            AsyncTask.task_type,
            AsyncTask.user_id,
            AsyncTask.input_data,
            AsyncTask.attempts,
        )
        .execution_options(synchronize_session=False)
    )
    row = res.first()
    if row is None:
        return None
    return ClaimedTask(
        id=row.id,
        task_type=row.task_type,
        user_id=row.user_id,
        input_data=row.input_data,
        attempts=row.attempts,
    )


def _owned(task: ClaimedTask):
    return and_(
        AsyncTask.id == task.id,
        AsyncTask.attempts == task.attempts,
        AsyncTask.status == TaskStatus.processing,
    )


async def mark_completed(db: AsyncSession, task: ClaimedTask, result: dict) -> bool:
    res = await db.execute(
        update(AsyncTask)
        .where(_owned(task))
        .values(
            status=TaskStatus.completed,
            result_data=result,
            error_message=None,
            completed_at=func.now(),
            locked_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    return bool(res.rowcount)


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=5 * 2 ** (attempts - 1))


async def mark_failed(db: AsyncSession, task: ClaimedTask, message: str, *, retryable: bool) -> str:
    """失敗を記録する。再試行できるなら pending に戻す。戻り値は新しい状態。"""
    if retryable and task.attempts < settings.AI_TASK_MAX_ATTEMPTS:
        await db.execute(
            update(AsyncTask)
            .where(_owned(task))
            .values(
                status=TaskStatus.pending,
                run_after=func.now() + retry_delay(task.attempts),
                locked_until=None,
            )
            .execution_options(synchronize_session=False)
        )
        return "pending"
    await db.execute(
        update(AsyncTask)
        .where(_owned(task))
        .values(
            status=TaskStatus.failed,
            error_message=message,
            completed_at=func.now(),
            locked_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    return "failed"
