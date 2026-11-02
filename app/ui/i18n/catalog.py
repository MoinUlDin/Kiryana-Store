"""Translation catalogs (pure Python, no Qt). One flat JSON file per language."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LangInfo:
    code: str
    native_name: str
    rtl: bool


LANGUAGES: dict[str, LangInfo] = {
    "en": LangInfo("en", "English", False),
    "ur": LangInfo("ur", "اردو", True),
}
DEFAULT_LANGUAGE = "en"


class Catalog:
    def __init__(self, data: dict[str, dict[str, str]]) -> None:
        self._data = data

    @classmethod
    def load_dir(cls, directory: Path) -> "Catalog":
        data = {}
        for code in LANGUAGES:
            data[code] = json.loads((directory / f"{code}.json").read_text(encoding="utf-8"))
        return cls(data)

    def keys(self, lang: str) -> set[str]:
        return set(self._data[lang])

    def raw(self, lang: str, key: str) -> str | None:
        return self._data.get(lang, {}).get(key)

    def tr(self, lang: str, key: str, **values: object) -> str:
        """Look up key in lang, fall back to English, then to the key itself."""
        text = self.raw(lang, key)
        if text is None:
            text = self.raw(DEFAULT_LANGUAGE, key)
        if text is None:
            return key
        try:
            return text.format(**values) if values else text
        except (KeyError, IndexError):
            return text
