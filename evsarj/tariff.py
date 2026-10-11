"""Tariff bands, cost and car estimates (battery percentage, range, latest finish)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings, Tariff

BANDS = ("day", "peak", "night")
# Time-of-use boundaries in local time: day 06–17, peak 17–22, night 22–06
BAND_EDGES = [(6, "day"), (17, "peak"), (22, "night")]


def band_at(ts: float, tz: ZoneInfo) -> str:
    hour = datetime.fromtimestamp(ts, tz).hour
    if 6 <= hour < 17:
        return "day"
    if 17 <= hour < 22:
        return "peak"
    return "night"


def _next_edge(ts: float, tz: ZoneInfo) -> float:
    d = datetime.fromtimestamp(ts, tz)
    for hour, _ in BAND_EDGES:
        edge = d.replace(hour=hour, minute=0, second=0, microsecond=0)
        if edge > d:
            return edge.timestamp()
    nxt = (d + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
    return nxt.timestamp()


def split_interval(t0: float, t1: float, tz: ZoneInfo) -> list[tuple[str, float]]:
    """Split [t0, t1) into tariff bands: [(band, seconds), ...]."""
    out: list[tuple[str, float]] = []
    cur = t0
    while cur < t1:
        edge = min(_next_edge(cur, tz), t1)
        out.append((band_at(cur, tz), edge - cur))
        cur = edge
    return out


def cost_of(energy_by_band: dict[str, float], tariff: Tariff) -> float:
    return sum(energy_by_band.get(b, 0.0) * tariff.price_for_band(b) for b in BANDS)


def battery_pct(energy_kwh: float, s: Settings) -> float:
    """Estimated battery percentage added (charge efficiency applied, capped at 100 %)."""
    return min(100.0, energy_kwh * s.charge_efficiency / s.battery_kwh * 100.0)


def range_km(energy_kwh: float, s: Settings) -> float:
    return energy_kwh * s.charge_efficiency / s.consumption_kwh_100km * 100.0


def latest_end(now: float, energy_kwh: float, current_kw: float, avg_kw: float, s: Settings) -> float | None:
    """Latest finish time assuming the battery started empty (timestamp)."""
    rate = current_kw if current_kw > 1.0 else avg_kw
    if rate < 0.3:
        return None
    remaining = max(0.0, s.battery_kwh / s.charge_efficiency - energy_kwh)
    return now + remaining / rate * 3600.0 + 10 * 60
