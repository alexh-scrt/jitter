"""Structured logging setup with Rich console output."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

_configured = False


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure root logger with Rich console and optional file handler."""
    global _configured
    if _configured:
        return

    root = logging.getLogger("jitter")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Rich console handler
    console = RichHandler(
        rich_tracebacks=True,
        show_path=False,
        markup=True,
    )
    console.setLevel(logging.DEBUG)
    root.addHandler(console)

    # File handler (if configured)
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the 'jitter' namespace."""
    return logging.getLogger(f"jitter.{name}")
