"""AI タスクのワーカー。API プロセスとは別に `python -m app.worker` で動かす。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.logging import get_logger
from app.services.ai_usage import BudgetExceededError, MeteredLLM
from app.services.llm import AIConfigurationError, AIOutputError, AIUnavailableError, LLMClient
from app.worker import queue
from app.worker.queue import ClaimedTask

logger = get_logger(__name__)

GENERIC_FAILURE = "AI の処理に失敗しました。時間をおいてもう一度お試しください"


class PermanentTaskError(Exception):
    """再試行しても結果が変わらない失敗。message はユーザーにそのまま見せる。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class TaskContext:
    task: ClaimedTask
    session_factory: async_sessionmaker[AsyncSession]
    llm: MeteredLLM

    async def complete(self, purpose: str, system_prompt: str, user_message: str):
        return await self.llm.complete(
            purpose=purpose,
            user_id=self.task.user_id,
            task_id=self.task.id,
            system_prompt=system_prompt,
            user_message=user_message,
        )


Handler = Callable[[TaskContext], Awaitable[dict]]


class Worker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        handlers: dict[str, Handler] | None = None,
    ):
        if handlers is None:
            from app.worker.handlers import HANDLERS

            handlers = HANDLERS
        self.session_factory = session_factory
        self.llm = MeteredLLM(llm, session_factory)
        self.handlers = handlers

    async def run_once(self) -> bool:
        """タスクを 1 件処理する。処理するものがなければ False。"""
        async with self.session_factory() as db:
            await queue.fail_exhausted(db)
            task = await queue.claim(db)
            await db.commit()
        if task is None:
            return False

        structlog.contextvars.bind_contextvars(
            task_id=str(task.id), task_type=task.task_type, attempt=task.attempts
        )
        start = time.perf_counter()
        try:
            result, error, retryable = await self._execute(task)
            async with self.session_factory() as db:
                if error is None:
                    written = await queue.mark_completed(db, task, result)
                    state = "completed" if written else "superseded"
                else:
                    state = await queue.mark_failed(db, task, error, retryable=retryable)
                await db.commit()
            logger.info(
                "task_finished",
                state=state,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
        finally:
            structlog.contextvars.unbind_contextvars("task_id", "task_type", "attempt")
        return True

    async def _execute(self, task: ClaimedTask) -> tuple[dict, str | None, bool]:
        """(結果, ユーザー向けエラー, 再試行するか)"""
        handler = self.handlers.get(task.task_type)
        if handler is None:
            logger.error("unknown_task_type")
            return {}, GENERIC_FAILURE, False
        ctx = TaskContext(task=task, session_factory=self.session_factory, llm=self.llm)
        try:
            # 期限 (locked_until) より前に打ち切り、別のワーカーとの二重実行を避ける
            result = await asyncio.wait_for(handler(ctx), timeout=settings.AI_TASK_TIMEOUT_S * 0.9)
            return result, None, False
        except PermanentTaskError as e:
            logger.info("task_rejected", reason=e.message)
            return {}, e.message, False
        except BudgetExceededError as e:
            return {}, e.detail, False
        except AIConfigurationError as e:
            # 認証情報・モデルの利用許可・モデル ID の誤りなど。再試行しても直らない
            logger.error("llm_misconfigured", error=e.reason)
            return {}, GENERIC_FAILURE, False
        except (AIUnavailableError, AIOutputError, ValidationError, TimeoutError) as e:
            logger.warning("task_retryable_error", error=type(e).__name__)
            return {}, GENERIC_FAILURE, True
        except Exception:
            logger.exception("task_crashed")
            return {}, GENERIC_FAILURE, True

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                worked = await self.run_once()
            except Exception:  # DB の一時的な切断などでループを止めない
                logger.exception("worker_loop_error")
                worked = False
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), settings.AI_WORKER_POLL_INTERVAL_S)
                except TimeoutError:
                    pass
