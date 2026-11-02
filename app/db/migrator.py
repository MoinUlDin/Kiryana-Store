"""Numbered SQL migrations. The applied version lives in PRAGMA user_version.

Rules for migration files (app/db/migrations/NNNN_name.sql):
  * numbers start at 0001 and have no gaps
  * no BEGIN/COMMIT inside; the migrator wraps each file in a transaction
  * never edit a migration that has shipped; add a new one
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DIR = Path(__file__).parent / "migrations"
_NAME = re.compile(r"^(\d{4})_[\w\-]+\.sql$")


class MigrationError(RuntimeError):
    pass


def _discover(directory: Path) -> list[tuple[int, Path]]:
    found = []
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.match(path.name)
        if not match:
            raise MigrationError(f"bad migration file name: {path.name}")
        found.append((int(match.group(1)), path))
    for expected, (number, path) in enumerate(found, start=1):
        if number != expected:
            raise MigrationError(f"migration numbering gap or duplicate at {path.name}")
    return found


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _backup_before_upgrade(conn: sqlite3.Connection, backup_dir: Path, version: int) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"pre_upgrade_v{version}_{stamp}.db"
    dest = sqlite3.connect(str(target))
    try:
        conn.backup(dest)  # SQLite online backup API: safe while the DB is in use
    finally:
        dest.close()
    return target


def migrate(
    conn: sqlite3.Connection,
    migrations_dir: Path = DEFAULT_DIR,
    backup_dir: Path | None = None,
) -> int:
    """Bring the database up to the latest version. Returns the new version."""
    migrations = _discover(migrations_dir)
    latest = len(migrations)
    version = current_version(conn)

    if version > latest:
        raise MigrationError(
            f"database is version {version} but this app only knows up to {latest}; "
            "install the newer version of the app"
        )
    if version == latest:
        return version

    if version > 0 and backup_dir is not None:
        saved = _backup_before_upgrade(conn, backup_dir, version)
        log.info("pre-upgrade backup saved to %s", saved)

    for number, path in migrations[version:]:
        log.info("applying migration %s", path.name)
        script = f"BEGIN IMMEDIATE;\n{path.read_text(encoding='utf-8')}\nPRAGMA user_version = {number};\nCOMMIT;"
        try:
            conn.executescript(script)
        except Exception as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise MigrationError(f"migration {path.name} failed: {exc}") from exc
    return latest
