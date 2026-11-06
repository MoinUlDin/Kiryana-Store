from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from app.domain.clock import local_today_iso
from app.domain.quantity import Quantity
from app.repositories.settings_repo import SettingsRepo
from app.repositories.stock_repo import StockRepo

EXPIRY_DAYS_KEY = "alerts.expiry_days"
DEFAULT_EXPIRY_DAYS = 30


@dataclass(frozen=True)
class ExpiryAlert:
    batch_id: int
    item_id: int
    item_name_en: str
    item_name_ur: str | None
    short_code: str
    unit: str
    qty_left: Quantity
    expiry_date: str
    days_left: int  # negative = already expired

    @property
    def expired(self) -> bool:
        return self.days_left < 0

    def display_name(self, lang: str) -> str:
        return self.item_name_ur if (lang == "ur" and self.item_name_ur) else self.item_name_en


class AlertService:
    def __init__(self, conn: sqlite3.Connection, settings: SettingsRepo,
                 today: Callable[[], str] = local_today_iso) -> None:
        self._stock = StockRepo(conn)
        self._settings = settings
        self._today = today

    def expiry_days(self) -> int:
        raw = self._settings.get(EXPIRY_DAYS_KEY)
        try:
            return max(0, int(raw)) if raw is not None else DEFAULT_EXPIRY_DAYS
        except ValueError:
            return DEFAULT_EXPIRY_DAYS

    def set_expiry_days(self, days: int) -> None:
        if not 0 <= days <= 3650:
            raise ValueError("days out of range")
        self._settings.set(EXPIRY_DAYS_KEY, str(days))

    def expiry_alerts(self, within_days: int | None = None, expired_only: bool = False) -> list[ExpiryAlert]:
        """Batches still holding stock that are expired or expire within `within_days` (default: the setting)."""
        today = date.fromisoformat(self._today())
        days = self.expiry_days() if within_days is None else within_days
        last = (today + timedelta(days=days)).isoformat()
        rows = self._stock.expiry_rows(last, today.isoformat(), expired_only)
        return [
            ExpiryAlert(r["batch_id"], r["item_id"], r["name_en"], r["name_ur"], r["short_code"], r["unit"],
                        Quantity(r["qty_left_milli"]), r["expiry_date"],
                        (date.fromisoformat(r["expiry_date"]) - today).days)
            for r in rows
        ]
