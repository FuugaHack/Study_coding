"""`python -m app.worker` で AI ワーカーを起動する。"""

import asyncio
import signal

from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import async_session, engine
from app.services.llm import get_llm_client
from app.worker.worker import Worker


async def main() -> None:
    configure_logging()
    logger = get_logger("app.worker")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    worker = Worker(async_session, get_llm_client())
    logger.info("worker_started", concurrency=settings.AI_WORKER_CONCURRENCY)
    await asyncio.gather(*(worker.run_forever(stop) for _ in range(settings.AI_WORKER_CONCURRENCY)))
    await engine.dispose()
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
