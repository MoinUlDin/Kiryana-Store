import pytest

from app.db.connection import connect
from app.db.migrator import migrate
from app.repositories.settings_repo import SettingsRepo


@pytest.fixture
def repo(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    yield SettingsRepo(conn)
    conn.close()


def test_default_when_missing(repo):
    assert repo.get("language") is None
    assert repo.get("language", "en") == "en"


def test_set_get_and_overwrite(repo):
    repo.set("language", "ur")
    assert repo.get("language") == "ur"
    repo.set("language", "en", user_id=5)
    assert repo.get("language") == "en"
