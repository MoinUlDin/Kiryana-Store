import re
from pathlib import Path

from app.ui.i18n.catalog import LANGUAGES, Catalog
from app.ui.ribbon_spec import ACTION_IDS, ACTIONS, TABS

I18N_DIR = Path(__file__).resolve().parent.parent / "app" / "ui" / "i18n"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def load():
    return Catalog.load_dir(I18N_DIR)


def test_both_languages_have_identical_keys():
    cat = load()
    assert cat.keys("en") == cat.keys("ur")


def test_placeholders_match_between_languages():
    cat = load()
    for key in cat.keys("en"):
        assert set(PLACEHOLDER.findall(cat.raw("en", key))) == set(PLACEHOLDER.findall(cat.raw("ur", key))), key


def test_no_empty_translations():
    cat = load()
    for lang in LANGUAGES:
        for key in cat.keys(lang):
            assert cat.raw(lang, key).strip(), (lang, key)


def test_fallback_and_formatting():
    cat = Catalog({"en": {"a": "Hello {name}", "only_en": "x"}, "ur": {"a": "سلام {name}"}})
    assert cat.tr("ur", "a", name="Ali") == "سلام Ali"
    assert cat.tr("ur", "only_en") == "x"          # falls back to English
    assert cat.tr("ur", "missing.key") == "missing.key"
    assert cat.tr("en", "a") == "Hello {name}"      # no values given: left untouched


def test_ribbon_spec_keys_exist_in_catalog():
    cat = load()
    keys = cat.keys("en")
    assert "app.title" in keys and "file.button" in keys
    for action in ACTIONS:
        assert f"act.{action.id}" in keys, action.id
    for tab in TABS:
        assert f"tab.{tab.key}" in keys, tab.key
        for group in tab.groups:
            assert f"group.{group.key}" in keys, group.key
            for action_id, _large in group.items:
                assert action_id in ACTION_IDS, action_id


def test_shortcuts_are_unique():
    shortcuts = [a.shortcut for a in ACTIONS if a.shortcut]
    assert len(shortcuts) == len(set(shortcuts))
    ids = [a.id for a in ACTIONS]
    assert len(ids) == len(set(ids))


def test_ribbon_spec_permissions_exist():
    from app.domain.permissions import PERMS_BY_KEY
    for action in ACTIONS:
        if action.perm:
            assert action.perm in PERMS_BY_KEY, (action.id, action.perm)
