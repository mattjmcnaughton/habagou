"""Structured logging configuration."""

import logging
from typing import Any

import structlog

from habagou.config import settings


def configure_logging() -> None:
    """Configure structlog for the application."""
    log_level = logging.getLevelNamesMapping().get(
        settings.log_level.upper(), logging.INFO
    )
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.log_format == "console"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def log_request(**fields: Any) -> None:
    """Emit one structured request log entry."""
    structlog.get_logger("habagou.requests").info("request_completed", **fields)
