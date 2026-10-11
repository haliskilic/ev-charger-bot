"""Locale-aware formatting of numbers, durations, dates and times."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "tr": ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
}
DAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "tr": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"],
}
DUR_UNITS = {
    "en": {"s": "s", "m": "min", "h": "h", "d": "d"},
    "tr": {"s": "sn", "m": "dk", "h": "sa", "d": "gün"},
}


class Formatter:
    def __init__(self, lang: str, tz: ZoneInfo, currency: str = "€"):
        self.lang = lang if lang in MONTHS else "en"
        self.tz = tz
        self.currency = currency

    def set_language(self, lang: str) -> None:
        self.lang = lang if lang in MONTHS else "en"

    # ---- numbers ----
    def num(self, value: float | None, nd: int = 1, unit: str = "") -> str:
        if value is None:
            return "—"
        s = f"{value:,.{nd}f}"
        if self.lang == "tr":
            s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s} {unit}".strip() if unit else s

    def kw(self, value: float | None, nd: int = 2) -> str:
        return self.num(value, nd, "kW")

    def kwh(self, value: float | None, nd: int = 2) -> str:
        return self.num(value, nd, "kWh")

    def money(self, value: float | None) -> str:
        return self.num(value, 2, self.currency)

    def price(self, value: float) -> str:
        """Unit price, e.g. '3.92 TL' (the caller appends '/kWh')."""
        return self.num(value, 2, self.currency)

    def pct(self, value: float | None, nd: int = 0, signed: bool = False) -> str:
        if value is None:
            return "—"
        s = self.num(abs(value), nd)
        body = f"%{s}" if self.lang == "tr" else f"{s}%"
        if signed:
            return ("+" if value >= 0 else "−") + body
        return body

    # ---- durations ----
    def duration(self, seconds: float | None) -> str:
        if seconds is None:
            return "—"
        u = DUR_UNITS[self.lang]
        seconds = int(round(seconds))
        if seconds < 60:
            return f"{seconds} {u['s']}"
        minutes = int(round(seconds / 60))
        if minutes < 60:
            return f"{minutes} {u['m']}"
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return f"{hours} {u['h']} {minutes} {u['m']}" if minutes else f"{hours} {u['h']}"
        days, hours = divmod(hours, 24)
        return f"{days} {u['d']} {hours} {u['h']}" if hours else f"{days} {u['d']}"

    # ---- dates and times ----
    def dt(self, ts: float | None) -> datetime | None:
        return datetime.fromtimestamp(ts, self.tz) if ts is not None else None

    def hm(self, ts: float | None) -> str:
        d = self.dt(ts)
        return d.strftime("%H:%M") if d else "—"

    def hms(self, ts: float | None) -> str:
        d = self.dt(ts)
        return d.strftime("%H:%M:%S") if d else "—"

    def date_short(self, ts: float | None) -> str:
        d = self.dt(ts)
        if not d:
            return "—"
        return d.strftime("%d.%m.%Y") if self.lang == "tr" else d.strftime("%Y-%m-%d")

    def date_dm(self, ts: float | None) -> str:
        d = self.dt(ts)
        if not d:
            return "—"
        return d.strftime("%d.%m") if self.lang == "tr" else d.strftime("%d %b")

    def date_long(self, d: datetime) -> str:
        m, w = MONTHS[self.lang][d.month - 1], DAYS[self.lang][d.weekday()]
        return f"{d.day} {m} {d.year} {w}" if self.lang == "tr" else f"{w}, {d.day} {m} {d.year}"

    def month_name(self, d: datetime) -> str:
        return f"{MONTHS[self.lang][d.month - 1]} {d.year}"

    def month_only(self, d: datetime) -> str:
        return MONTHS[self.lang][d.month - 1]

    def day_month(self, d: datetime) -> str:
        return f"{d.day} {MONTHS[self.lang][d.month - 1]}"

    def range_days(self, start: datetime, end: datetime) -> str:
        m = MONTHS[self.lang]
        if start.month == end.month:
            return f"{start.day}–{end.day} {m[end.month - 1]} {end.year}"
        return f"{start.day} {m[start.month - 1]} – {end.day} {m[end.month - 1]} {end.year}"

    def when(self, ts: float, now: float | None = None) -> str:
        """Event time: 'HH:MM' if today, otherwise with the date."""
        d = self.dt(ts)
        n = self.dt(now) if now else datetime.now(self.tz)
        if d.date() == n.date():
            return d.strftime("%H:%M")
        return f"{self.date_dm(ts)} {d.strftime('%H:%M')}"
