"""Where the app keeps its files. Data lives outside the install folder so
upgrades and uninstalls never touch shop data."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "KiryanaPOS"


def data_dir() -> Path:
    override = os.environ.get("KIRYANA_POS_DATA")  # handy for development and tests
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def db_path() -> Path:
    return data_dir() / "pos.db"


def backup_dir() -> Path:
    return data_dir() / "backups"


def log_dir() -> Path:
    return data_dir() / "logs"


def ensure_dirs() -> None:
    for path in (data_dir(), backup_dir(), log_dir()):
        path.mkdir(parents=True, exist_ok=True)


def project_root() -> Path:
    """Folder holding assets/. Works both from source and from a PyInstaller build."""
    import sys
    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root) if frozen_root else Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return project_root() / "assets"


def fonts_dir() -> Path:
    return assets_dir() / "fonts"
