import sqlite3

import pytest

from app.db.connection import connect, transaction
from app.db.migrator import DEFAULT_DIR, MigrationError, current_version, migrate

LATEST = len(list(DEFAULT_DIR.glob('*.sql')))


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    yield c
    c.close()


def test_fresh_database_migrates_and_is_idempotent(conn):
    assert current_version(conn) == 0
    assert migrate(conn) == LATEST
    assert current_version(conn) == LATEST
    assert migrate(conn) == LATEST  # second run does nothing
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"settings", "audit_log", "users", "role_permissions", "approval_pins"} <= tables


def test_connection_pragmas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL


def test_audit_log_is_append_only(conn):
    migrate(conn)
    conn.execute("INSERT INTO audit_log(action) VALUES ('test')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_log SET action = 'x'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_log")


def test_refuses_database_newer_than_app(conn):
    migrate(conn)
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(MigrationError, match="newer"):
        migrate(conn)


def test_failed_migration_rolls_back(conn, tmp_path):
    d = tmp_path / "migs"
    d.mkdir()
    (d / "0001_ok.sql").write_text("CREATE TABLE a (id INTEGER);")
    (d / "0002_bad.sql").write_text("CREATE TABLE b (id INTEGER); THIS IS NOT SQL;")
    with pytest.raises(MigrationError):
        migrate(conn, migrations_dir=d)
    assert current_version(conn) == 1  # 0001 stayed, 0002 fully rolled back
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "a" in tables and "b" not in tables


def test_numbering_gap_detected(conn, tmp_path):
    d = tmp_path / "migs"
    d.mkdir()
    (d / "0001_a.sql").write_text("CREATE TABLE a (id INTEGER);")
    (d / "0003_c.sql").write_text("CREATE TABLE c (id INTEGER);")
    with pytest.raises(MigrationError, match="gap"):
        migrate(conn, migrations_dir=d)


def test_pre_upgrade_backup_created(conn, tmp_path):
    d = tmp_path / "migs"
    d.mkdir()
    (d / "0001_a.sql").write_text("CREATE TABLE a (id INTEGER);")
    migrate(conn, migrations_dir=d)
    (d / "0002_b.sql").write_text("CREATE TABLE b (id INTEGER);")
    backups = tmp_path / "bk"
    migrate(conn, migrations_dir=d, backup_dir=backups)
    assert len(list(backups.glob("pre_upgrade_v1_*.db"))) == 1


def test_transaction_helper_rolls_back(conn):
    migrate(conn)
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO settings(key, value) VALUES ('k', 'v')")
            raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0
    with transaction(conn):
        conn.execute("INSERT INTO settings(key, value) VALUES ('k', 'v')")
    assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1
