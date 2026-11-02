from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from app.ui.i18n.catalog import DEFAULT_LANGUAGE, LANGUAGES, Catalog, LangInfo


class I18n(QObject):
    """Holds the current language and tells the UI when it changes."""

    language_changed = pyqtSignal(str)

    def __init__(self, catalog: Catalog, language: str = DEFAULT_LANGUAGE) -> None:
        super().__init__()
        self._catalog = catalog
        self._lang = language if language in LANGUAGES else DEFAULT_LANGUAGE

    @property
    def lang(self) -> str:
        return self._lang

    @property
    def info(self) -> LangInfo:
        return LANGUAGES[self._lang]

    @property
    def is_rtl(self) -> bool:
        return self.info.rtl

    def tr(self, key: str, **values: object) -> str:
        return self._catalog.tr(self._lang, key, **values)

    def set_language(self, code: str) -> None:
        if code in LANGUAGES and code != self._lang:
            self._lang = code
            self.language_changed.emit(code)
