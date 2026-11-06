"""Search-text normalisation so Urdu and English search behave the way shopkeepers expect."""
from __future__ import annotations

import re
import unicodedata

_DIACRITICS = re.compile("[\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED]")
_MAP = str.maketrans({
    "\u064A": "\u06CC",  # Arabic yeh   -> Farsi/Urdu yeh
    "\u0649": "\u06CC",  # alef maksura -> Urdu yeh
    "\u0643": "\u06A9",  # Arabic kaf   -> Urdu kaf
    "\u0647": "\u06C1",  # Arabic heh   -> Urdu heh goal
    "\u0629": "\u06C1",  # teh marbuta  -> Urdu heh goal
    **{chr(0x0660 + i): str(i) for i in range(10)},  # Arabic-Indic digits
    **{chr(0x06F0 + i): str(i) for i in range(10)},  # Eastern Arabic-Indic digits
})


def normalize_search(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower().translate(_MAP)
    text = _DIACRITICS.sub("", text).replace("\u200c", "").replace("\u200d", "")
    return " ".join(text.split())
