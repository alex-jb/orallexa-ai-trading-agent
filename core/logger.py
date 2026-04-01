"""
core/logger.py
──────────────────────────────────────────────────────────────────
Centralized logging for the Orallexa project.

Usage:
    from core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Analysis started for %s", ticker)
    logger.warning("Data stale: %d minutes old", age)
    logger.error("API failed", exc_info=True)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger("orallexa")
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — all logs
    fh = logging.FileHandler(_LOG_DIR / "orallexa.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler — warnings and above
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'orallexa' namespace."""
    _configure()
    if not name.startswith("orallexa."):
        name = f"orallexa.{name}"
    return logging.getLogger(name)
