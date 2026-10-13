"""Daily / weekly / monthly statistics computed from the sessions table."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from .config import Settings
from .db import DB


def _energy(row) -> float:
    return float(row["energy_kwh"] if row["energy_kwh"] is not None else (row["energy_calc_kwh"] or 0.0))


def period_stats(db: DB, settings: Settings, t0: float, t1: float, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    n = kwh = cost = charge_s = peak = 0.0
    open_n = 0
    for row in db.sessions_in(t0, t1):
        e = _energy(row)
        if e < 0.01:
            continue
        n += 1
        kwh += e
        if row["cost"] is not None:
            cost += float(row["cost"])
        else:  # open session: approximate with the single price
            cost += e * settings.tariff.single
        charge_s += float(row["charge_s"] or 0.0)
        peak = max(peak, float(row["peak_kw"] or 0.0))
        if not row["closed"]:
            open_n += 1
            seg = db.open_segment(row["id"])  # stored charge_s covers closed segments only
            if seg is not None:
                charge_s += max(0.0, min(now, t1) - float(seg["start_ts"]))
    return {"n": int(n), "kwh": kwh, "cost": cost, "charge_s": charge_s, "peak": peak, "open_n": open_n}


def day_bounds(d: datetime) -> tuple[float, float]:
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def week_bounds(d: datetime) -> tuple[float, float, datetime, datetime]:
    """Monday 00:00 – next Monday 00:00; also returns (first day, last day)."""
    start = (d - timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start.timestamp(), end.timestamp(), start, end - timedelta(days=1)


def month_bounds(d: datetime) -> tuple[float, float, datetime]:
    start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start.timestamp(), nxt.timestamp(), start


def prev_month(d: datetime) -> datetime:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)
