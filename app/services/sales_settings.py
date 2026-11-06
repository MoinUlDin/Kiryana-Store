from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domain.pricing import ROUND_NONE, ROUND_RUPEE
from app.repositories.settings_repo import SettingsRepo

ROUNDING_KEY = "sales.rounding"
LIMIT_KEY = "sales.cashier_discount_limit_pct"
DEFAULT_LIMIT = Decimal(10)


class SalesSettings:
    """The few shop-wide knobs the sale screen depends on. Defaults match the SRS."""

    def __init__(self, settings: SettingsRepo) -> None:
        self._settings = settings

    def rounding(self) -> str:
        return ROUND_NONE if self._settings.get(ROUNDING_KEY) == ROUND_NONE else ROUND_RUPEE

    def set_rounding(self, mode: str) -> None:
        if mode not in (ROUND_RUPEE, ROUND_NONE):
            raise ValueError(mode)
        self._settings.set(ROUNDING_KEY, mode)

    def discount_limit_percent(self) -> Decimal:
        """Discounts above this share of the bill need the 'unlimited discount' permission."""
        raw = self._settings.get(LIMIT_KEY)
        try:
            value = Decimal(raw) if raw is not None else DEFAULT_LIMIT
        except InvalidOperation:
            return DEFAULT_LIMIT
        return value if 0 <= value <= 100 else DEFAULT_LIMIT

    def set_discount_limit_percent(self, value: Decimal | int | str) -> None:
        pct = Decimal(value)
        if not pct.is_finite() or not 0 <= pct <= 100:
            raise ValueError("limit must be between 0 and 100")
        self._settings.set(LIMIT_KEY, str(pct))
