from __future__ import annotations

from app.security.passwords import ValidationError
from app.ui.i18n.manager import I18n


def error_text(i18n: I18n, exc: Exception) -> str:
    """Turn a service exception into a message in the current language."""
    if isinstance(exc, ValidationError):
        return i18n.tr(exc.code, **exc.params)
    if isinstance(exc, PermissionError):
        return i18n.tr("error.not_allowed")
    raise exc  # a real bug: let it reach the crash handler instead of hiding it
