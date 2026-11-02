from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app import paths


def setup_logging(level: int = logging.INFO) -> None:
    handler = RotatingFileHandler(
        paths.log_dir() / "app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
