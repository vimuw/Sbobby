"""
Structured logging helpers for El Sbobinator.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import IO

LOGGER_NAME = "el_sbobinator"
_CONTEXT_KEYS = ("run_id", "session_dir", "stage", "input_file")


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        context_bits: list[str] = []
        for key in _CONTEXT_KEYS:
            value = getattr(record, key, None)
            if value:
                context_bits.append(f"{key}={value}")
        if context_bits:
            return f"{base} [{' '.join(context_bits)}]"
        return base


def configure_logging(stream: IO[str] | None = None) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_el_sbobinator_configured", False):
        return logger

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(
        StructuredFormatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger._el_sbobinator_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str = LOGGER_NAME, **context: str) -> logging.LoggerAdapter:
    base = configure_logging()
    logger = base if name == LOGGER_NAME else logging.getLogger(name)
    if logger is not base:
        logger.setLevel(base.level)
        logger.propagate = True  # propagate to parent; parent has propagate=False
    clean_context = {key: value for key, value in context.items() if value}
    return logging.LoggerAdapter(logger, clean_context)


def attach_file_handler(log_path: str) -> logging.Handler | None:
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            StructuredFormatter("%(asctime)s %(levelname)s %(message)s")
        )
        configure_logging().addHandler(handler)
        return handler
    except Exception:
        return None


def detach_file_handler(handler: logging.Handler | None) -> None:
    if handler is None:
        return
    logger = configure_logging()
    try:
        logger.removeHandler(handler)
    except Exception:
        pass
    try:
        handler.close()
    except Exception:
        pass
