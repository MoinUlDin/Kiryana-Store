"""Shared test helpers (plain functions, no pytest magic)."""
from datetime import datetime, timedelta, timezone

from app.db.connection import connect
from app.db.migrator import migrate
from app.security import passwords
from app.services.container import build_services

passwords.SCRYPT_N = 2 ** 4  # fast hashing for tests only; production uses 2**14


class FakeClock:
    def __init__(self):
        self.moment = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.moment

    def advance(self, **kw):
        self.moment += timedelta(**kw)


def make_services(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    return build_services(conn)
