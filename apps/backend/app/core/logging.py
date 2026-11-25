"""構造化ログ (structlog) の設定。

- LOG_FORMAT=json (既定) は 1 行 1 JSON、console は開発用の読みやすい形式
- 標準 logging (uvicorn・SQLAlchemy など) の出力も同じ形式にそろえる
- ユーザーのコード・プロンプト・LLM の出力はログに出さない (docs/expansion/m4-design.md §6)
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.config import settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    shared: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.LOG_FORMAT == "console"
        else structlog.processors.JSONRenderer(ensure_ascii=False)
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())
    # アクセスログは RequestLoggingMiddleware が出すので重複させない
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
