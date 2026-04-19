"""
Structured logging for Mazao AI agent.
Every log line is machine-parseable JSON in production,
human-readable in development.
"""

import logging
import sys
import os
import structlog
from typing import Any


def setup_logging() -> None:
    """
    Configure structlog for the application.
    - Development: colourised, human-readable
    - Production:  JSON, one line per event (ingestible by Railway / Datadog)
    """
    is_dev = os.getenv("APP_ENV", "development") == "development"

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_dev:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
