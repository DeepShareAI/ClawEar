"""Rotating file logging for ble-explorer-mcp."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / "Library" / "Logs" / "ble-explorer-mcp"
LOG_FILE = LOG_DIR / "server.log"


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure the package root logger with a rotating file handler.

    5MB per file, 5 backups. Returns the configured logger.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger = logging.getLogger("ble_explorer_mcp")
    logger.setLevel(level.upper())
    # Idempotent: clear existing handlers so re-configuration doesn't duplicate.
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    return logger
