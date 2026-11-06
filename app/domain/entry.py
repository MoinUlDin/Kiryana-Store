"""The fast-entry box on the sale screen: '2.5*SUG' means 2.5 of item SUG."""
from __future__ import annotations

import re

from app.domain.parsing import parse_quantity
from app.domain.quantity import Quantity
from app.security.passwords import ValidationError

# Only * and the multiplication sign. A plain 'x' would clash with codes like '2x4'. No commas, so '1,5' is never read as 15.
_ENTRY = re.compile(r"^\s*([0-9.\u0660-\u0669\u06F0-\u06F9\u066B]+)\s*[*\u00D7]\s*(.+?)\s*$")


def split_quantity(text: str) -> tuple[Quantity | None, str]:
    """('2.5*SUG') -> (Quantity 2.5, 'SUG'). Without a valid leading quantity: (None, whole text)."""
    match = _ENTRY.match(text)
    if match:
        try:
            qty = parse_quantity(match.group(1))
        except ValidationError:
            return None, text.strip()
        if qty.milli > 0:
            return qty, match.group(2)
    return None, text.strip()
