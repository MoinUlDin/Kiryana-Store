from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database with the safety settings the whole app relies on.

    isolation_level=None means Python never opens transactions behind our
    back; services open them explicitly with transaction().
    """
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One service call = one transaction. Commits on success, rolls back on any error."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


@contextmanager
def atomic(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Join the caller's transaction if there is one, otherwise start our own.
    Lets a service method be safe on its own and also composable inside a bigger one."""
    if conn.in_transaction:
        yield conn
    else:
        with transaction(conn):
            yield conn
