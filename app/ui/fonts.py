from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtGui import QFontDatabase

log = logging.getLogger(__name__)

# First installed family in each list wins. Segoe UI / Tahoma are Windows fallbacks.
PREFERRED = {
    "en": ["Inter", "Inter Variable", "Segoe UI"],
    "ur": ["Jameel Noori Nastaleeq", "Noto Nastaliq Urdu", "Urdu Typesetting", "Tahoma"],
}


def load_fonts(directory: Path) -> list[str]:
    """Register every .ttf/.otf in `directory` with Qt. Returns the family names found."""
    families: list[str] = []
    if not directory.is_dir():
        log.warning("font folder not found: %s", directory)
        return families
    for path in sorted(list(directory.glob("*.ttf")) + list(directory.glob("*.otf"))):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            log.warning("could not load font file %s", path.name)
            continue
        families.extend(QFontDatabase.applicationFontFamilies(font_id))
    log.info("loaded font families: %s", sorted(set(families)))
    return families


def family_for(lang: str) -> str:
    installed = set(QFontDatabase.families())
    for name in PREFERRED.get(lang, []):
        if name in installed:
            return name
    log.warning("no preferred font installed for %s; using default", lang)
    return PREFERRED[lang][-1]
