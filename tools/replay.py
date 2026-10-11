"""Replay a discovery log (JSON lines with "ts" and "dps") through the state machine and print the events.

Usage:  python -m tools.replay tests/fixtures/discovery_2026-10-11.jsonl [--db /tmp/replay.db] [--lang en|tr]
Does not touch the charger or Telegram; it only exercises Monitor + Reports.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from zoneinfo import ZoneInfo

from evsarj.config import Settings
from evsarj.db import DB
from evsarj.monitor import Monitor, Session
from evsarj.reports import Reports


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t


class PrintSink:
    def __init__(self, tz: ZoneInfo, clock: Clock, verbose: bool = True):
        self.tz = tz
        self.clock = clock
        self.verbose = verbose
        self.events: list[tuple[float, str, str]] = []

    def _stamp(self, ts: float) -> str:
        return dt.datetime.fromtimestamp(ts, self.tz).strftime("%H:%M:%S")

    def event(self, ts, etype, text, details, session_id):
        self.events.append((ts, etype, text))
        if self.verbose:
            print(f"[{self._stamp(ts)}] EVENT {etype:<16} session={session_id} | {text.splitlines()[0]}")
            if etype == "unplugged":
                for line in text.splitlines()[1:]:
                    print("      " + line)

    def live_create(self, session: Session):
        if self.verbose:
            print(f"[{self._stamp(self.clock.now())}] LIVE create (session {session.id})")
        session.live_message_id = 1000 + session.id

    def live_update(self, session: Session, final: bool = False):
        if self.verbose:
            print(f"[{self._stamp(self.clock.now())}] LIVE edit{' (final)' if final else ''} (session {session.id})")

    def interim(self, session: Session):
        if self.verbose:
            print(f"[{self._stamp(self.clock.now())}] INTERIM report (session {session.id})")

    def session_closed(self, session: Session, text: str):
        pass

    def fast(self, fast: bool):
        pass


def replay(log_path: str, db_path: str, lang: str = "en", verbose: bool = True) -> tuple[PrintSink, DB]:
    if os.path.exists(db_path):
        os.remove(db_path)
    settings = Settings()
    settings.language = lang
    tz = settings.tz
    db = DB(db_path)
    clock = Clock()
    sink = PrintSink(tz, clock, verbose)
    mon = Monitor(settings, db, sink, Reports(settings), now_fn=clock.now)
    records = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if not r.get("dps"):
                continue
            ts = dt.datetime.fromisoformat(r["ts"]).replace(tzinfo=tz).timestamp()
            records.append((ts, r["dps"], r.get("kind") == "poll_status"))
    records.sort(key=lambda x: x[0])
    if not records:
        sys.exit("no records")
    clock.t = records[0][0]
    mon.on_conn(clock.t, "online", {"outage_s": 0})
    next_tick = clock.t
    for ts, dps, snapshot in records:
        while next_tick < ts:
            clock.t = next_tick
            mon.on_tick(next_tick)
            next_tick += 1.0
        clock.t = ts
        mon.on_dps(ts, dps, snapshot=snapshot and not mon.initialized)
    for _ in range(120):  # let pending time-based decisions settle
        next_tick += 1.0
        clock.t = next_tick
        mon.on_tick(next_tick)
    return sink, db


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--db", default=os.path.join(tempfile.gettempdir(), "evsarj-replay.db"))
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()
    sink, db = replay(args.log, args.db, args.lang)
    print(f"\n{len(sink.events)} events. Sessions:")
    for row in db.all_sessions():
        print({k: row[k] for k in ("id", "plug_ts", "charge_start_ts", "unplug_ts", "charge_s", "energy_kwh", "energy_calc_kwh", "peak_kw", "end_reason")})
    for row in db.q("SELECT * FROM segments"):
        print("segment", dict(row))


if __name__ == "__main__":
    main()
