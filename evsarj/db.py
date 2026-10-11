"""SQLite layer: raw samples (rolling retention), state transitions, sessions, charging segments, events, message queue, settings.

Retention (see [retention] in config.toml): samples are kept for N days, transitions and events for N months;
sessions are kept forever (they are tiny). Old rows are deleted daily so the database cannot fill the disk.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    session_id INTEGER,
    work_state TEXT, switch INTEGER, cur_set INTEGER, work_mode TEXT, fault INTEGER,
    power_kw REAL,
    va REAL, ia REAL, pa REAL,
    vb REAL, ib REAL, pb REAL,
    vc REAL, ic REAL, pc REAL,
    timer_raw TEXT
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);

CREATE TABLE IF NOT EXISTS transitions (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    session_id INTEGER,
    dp TEXT NOT NULL, code TEXT NOT NULL,
    old TEXT, new TEXT
);
CREATE INDEX IF NOT EXISTS idx_transitions_ts ON transitions(ts);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'bot',
    plug_ts REAL, charge_start_ts REAL, charge_end_ts REAL, unplug_ts REAL,
    plugged_s INTEGER, charge_s INTEGER,
    energy_kwh REAL, energy_calc_kwh REAL, energy_device_kwh REAL, energy_device2_kwh REAL,
    peak_kw REAL, avg_kw REAL,
    cost REAL, cost_json TEXT,
    phase_json TEXT, warnings_json TEXT, counters_json TEXT,
    end_reason TEXT, device_closed_ts REAL, notes_json TEXT,
    live_message_id INTEGER,
    closed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_plug ON sessions(plug_ts);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    start_ts REAL NOT NULL, end_ts REAL,
    energy_kwh REAL NOT NULL DEFAULT 0,
    end_reason TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    session_id INTEGER,
    type TEXT NOT NULL,
    text TEXT NOT NULL,
    details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    created_ts REAL NOT NULL,
    event_ts REAL NOT NULL,
    kind TEXT NOT NULL,            -- msg | live_create | edit
    text TEXT NOT NULL,
    silent INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    message_id INTEGER,
    extra_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, id);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

# Older databases (first release) used these column names.
MIGRATIONS = [
    ("sessions", "cost_tl", "ALTER TABLE sessions RENAME COLUMN cost_tl TO cost"),
    ("sessions", "notes", "ALTER TABLE sessions RENAME COLUMN notes TO notes_json"),
]


class DB:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        for table, old_col, sql in MIGRATIONS:
            cols = {r["name"] for r in self.q(f"PRAGMA table_info({table})")}
            if old_col in cols:
                self.x(sql)

    # ---- generic ----
    def close(self) -> None:
        self.conn.close()

    def q(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, tuple(params)).fetchall()

    def q1(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, tuple(params)).fetchone()

    def x(self, sql: str, params: Iterable[Any] = ()) -> int:
        cur = self.conn.execute(sql, tuple(params))
        return cur.lastrowid or 0

    # ---- settings / meta ----
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.q1("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def all_settings(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self.q("SELECT key,value FROM settings")}

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.q1("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.x("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # ---- samples / transitions ----
    def insert_sample(self, ts: float, session_id: int | None, d: dict[str, Any]) -> None:
        self.x(
            "INSERT INTO samples(ts,session_id,work_state,switch,cur_set,work_mode,fault,power_kw,va,ia,pa,vb,ib,pb,vc,ic,pc,timer_raw)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts, session_id, d.get("work_state"), d.get("switch"), d.get("cur_set"), d.get("work_mode"), d.get("fault"),
                d.get("power_kw"), d.get("va"), d.get("ia"), d.get("pa"), d.get("vb"), d.get("ib"), d.get("pb"),
                d.get("vc"), d.get("ic"), d.get("pc"), d.get("timer_raw"),
            ),
        )

    def insert_transition(self, ts: float, session_id: int | None, dp: str, code: str, old: Any, new: Any) -> None:
        self.x(
            "INSERT INTO transitions(ts,session_id,dp,code,old,new) VALUES(?,?,?,?,?,?)",
            (ts, session_id, dp, code, None if old is None else str(old), None if new is None else str(new)),
        )

    def samples_between(self, t0: float, t1: float) -> list[sqlite3.Row]:
        return self.q("SELECT * FROM samples WHERE ts>=? AND ts<? ORDER BY ts", (t0, t1))

    def purge(self, samples_days: int, transitions_months: int, events_months: int) -> dict[str, int]:
        """Delete old rows (rolling retention). Returns row counts per table."""
        now = time.time()
        out = {}
        out["samples"] = self.conn.execute("DELETE FROM samples WHERE ts<?", (now - samples_days * 86400,)).rowcount
        out["transitions"] = self.conn.execute("DELETE FROM transitions WHERE ts<?", (now - transitions_months * 30.44 * 86400,)).rowcount
        out["events"] = self.conn.execute("DELETE FROM events WHERE ts<?", (now - events_months * 30.44 * 86400,)).rowcount
        out["outbox"] = self.conn.execute("DELETE FROM outbox WHERE status<>'pending' AND created_ts<?", (now - 30 * 86400,)).rowcount
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return out

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")

    # ---- events / queue ----
    def insert_event(self, ts: float, session_id: int | None, etype: str, text: str, details: dict | None = None) -> int:
        return self.x(
            "INSERT INTO events(ts,session_id,type,text,details_json) VALUES(?,?,?,?,?)",
            (ts, session_id, etype, text, json.dumps(details, ensure_ascii=False) if details else None),
        )

    def enqueue(self, kind: str, text: str, event_ts: float, silent: bool = False, message_id: int | None = None, extra: dict | None = None) -> int:
        return self.x(
            "INSERT INTO outbox(created_ts,event_ts,kind,text,silent,message_id,extra_json) VALUES(?,?,?,?,?,?,?)",
            (time.time(), event_ts, kind, text, 1 if silent else 0, message_id, json.dumps(extra, ensure_ascii=False) if extra else None),
        )

    def next_outbox(self) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM outbox WHERE status='pending' ORDER BY id LIMIT 1")

    def outbox_pending_count(self) -> int:
        return self.q1("SELECT COUNT(*) AS n FROM outbox WHERE status='pending'")["n"]

    def outbox_done(self, row_id: int, message_id: int | None) -> None:
        self.x("UPDATE outbox SET status='sent', message_id=COALESCE(?,message_id) WHERE id=?", (message_id, row_id))

    def outbox_fail(self, row_id: int, error: str, final: bool) -> None:
        self.x(
            "UPDATE outbox SET attempts=attempts+1, last_error=?, status=CASE WHEN ? THEN 'failed' ELSE status END WHERE id=?",
            (error[:300], 1 if final else 0, row_id),
        )

    def drop_pending_edits_for(self, message_id: int, keep_id: int) -> None:
        """Keep only the newest pending edit of a live message."""
        self.x("UPDATE outbox SET status='failed', last_error='superseded' WHERE kind='edit' AND status='pending' AND message_id=? AND id<>?", (message_id, keep_id))

    # ---- sessions ----
    def create_session(self, plug_ts: float, source: str = "bot") -> int:
        return self.x("INSERT INTO sessions(source,plug_ts) VALUES(?,?)", (source, plug_ts))

    def open_session(self) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM sessions WHERE closed=0 AND source='bot' ORDER BY id DESC LIMIT 1")

    def update_session(self, session_id: int, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))

    def session(self, session_id: int) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM sessions WHERE id=?", (session_id,))

    def last_closed_session(self) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM sessions WHERE closed=1 ORDER BY COALESCE(unplug_ts, plug_ts) DESC LIMIT 1")

    def recent_sessions(self, n: int = 10) -> list[sqlite3.Row]:
        return self.q("SELECT * FROM sessions ORDER BY COALESCE(charge_start_ts, plug_ts) DESC LIMIT ?", (n,))

    def sessions_in(self, t0: float, t1: float) -> list[sqlite3.Row]:
        """Sessions whose charge start (or plug-in, if never charged) falls in [t0, t1)."""
        return self.q(
            "SELECT * FROM sessions WHERE COALESCE(charge_start_ts, plug_ts)>=? AND COALESCE(charge_start_ts, plug_ts)<? ORDER BY plug_ts",
            (t0, t1),
        )

    def lifetime_kwh(self) -> float:
        row = self.q1("SELECT COALESCE(SUM(COALESCE(energy_kwh, energy_calc_kwh, 0)),0) AS e FROM sessions")
        return float(row["e"])

    def all_sessions(self) -> list[sqlite3.Row]:
        return self.q("SELECT * FROM sessions ORDER BY plug_ts")

    def has_import(self, plug_ts: float, unplug_ts: float) -> bool:
        return self.q1("SELECT 1 FROM sessions WHERE source='smartlife' AND plug_ts=? AND unplug_ts=?", (plug_ts, unplug_ts)) is not None

    # ---- segments ----
    def create_segment(self, session_id: int, start_ts: float) -> int:
        return self.x("INSERT INTO segments(session_id,start_ts) VALUES(?,?)", (session_id, start_ts))

    def update_segment(self, seg_id: int, **fields: Any) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE segments SET {cols} WHERE id=?", (*fields.values(), seg_id))

    def open_segment(self, session_id: int) -> sqlite3.Row | None:
        return self.q1("SELECT * FROM segments WHERE session_id=? AND end_ts IS NULL ORDER BY id DESC LIMIT 1", (session_id,))

    def segments_of(self, session_id: int) -> list[sqlite3.Row]:
        return self.q("SELECT * FROM segments WHERE session_id=? ORDER BY start_ts", (session_id,))
