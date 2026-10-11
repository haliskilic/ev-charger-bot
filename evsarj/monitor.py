"""State machine: turns DP updates into events, sessions and charging segments.

Rules derived from the measurements in docs/DP-MAP.md:
  * A work_state (DP3) transition is accepted only after `debounce_s` (5 s); the charger shows `free` + 6 A for 3 s after a reboot.
  * "Charging started" is decided by power > 0; the charger also reports `charging` with 0 A right after the car unlocks.
  * Manual stop = `switch` off + `wait`; but `switch` flips off for 6 s on unplug, so the decision waits 10 s.
  * Car full / car stopped = `switch` on and power at 0 for 60 s.
  * DP25 (session counter) arrives on unplug or when the charger closes its record (12-hour limit).
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import dp as DP
from .config import Settings
from .db import DB
from .reports import Reports
from .tariff import BANDS, split_interval

log = logging.getLogger("evsarj.monitor")

P_ON = 0.05  # kW: above this the car is drawing current
ZERO_END_S = 60  # power at 0 for this long ends a charging segment
MANUAL_WAIT_S = 10  # after switch-off: unplug or manual stop?
UNPLUG_DP25_WAIT_S = 15  # wait for DP25 after an unplug
DP25_DECIDE_S = 20  # DP25 while plugged: unplug follows, or the charger closed its record?
REBOOT_WINDOW_S = 30
NOCHARGE_AFTER_S = 180
SCHEDULED_AFTER_S = 30
WARN_PERSIST_S = 60
WARN_REPEAT_S = 30 * 60
SAMPLE_IDLE_S = 60


class Sink(Protocol):
    def event(self, ts: float, etype: str, text: str, details: dict | None, session_id: int | None) -> None: ...
    def live_create(self, session: "Session") -> None: ...
    def live_update(self, session: "Session", final: bool = False) -> None: ...
    def interim(self, session: "Session") -> None: ...
    def session_closed(self, session: "Session", text: str) -> None: ...
    def fast(self, fast: bool) -> None: ...


@dataclass
class PhaseStats:
    v_min: float | None = None
    v_max: float | None = None
    v_sum: float = 0.0
    v_n: int = 0
    i_min: float | None = None
    i_max: float | None = None
    i_sum: float = 0.0
    i_n: int = 0

    def update(self, v: float, i: float) -> None:
        if i > 0.2:  # voltage/current are only meaningful while current flows
            self.v_min = v if self.v_min is None else min(self.v_min, v)
            self.v_max = v if self.v_max is None else max(self.v_max, v)
            self.v_sum += v
            self.v_n += 1
            self.i_min = i if self.i_min is None else min(self.i_min, i)
            self.i_max = i if self.i_max is None else max(self.i_max, i)
            self.i_sum += i
            self.i_n += 1

    @property
    def v_avg(self) -> float | None:
        return self.v_sum / self.v_n if self.v_n else None

    @property
    def i_avg(self) -> float | None:
        return self.i_sum / self.i_n if self.i_n else None

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict | None) -> "PhaseStats":
        p = cls()
        if d:
            p.__dict__.update(d)
        return p


@dataclass
class Segment:
    id: int
    start_ts: float
    energy: float = 0.0
    peak_kw: float = 0.0
    zero_since: float | None = None
    end_reason: str | None = None
    history: deque = field(default_factory=lambda: deque(maxlen=400))  # (ts, kw)
    warned: set = field(default_factory=set)
    timers: dict = field(default_factory=dict)


@dataclass
class Session:
    id: int
    plug_ts: float
    charge_start_ts: float | None = None
    charge_end_ts: float | None = None
    unplug_ts: float | None = None
    energy_calc: float = 0.0
    energy_by_band: dict = field(default_factory=lambda: {b: 0.0 for b in BANDS})
    energy_device: float | None = None
    energy_device2: float | None = None
    device_closed_ts: float | None = None
    peak_kw: float = 0.0
    charge_s_closed: float = 0.0
    phases: dict = field(default_factory=lambda: {k: PhaseStats() for k in ("a", "b", "c")})
    warnings: list = field(default_factory=list)  # [{"c": code, "t": ts, ...params}]
    notes: list = field(default_factory=list)  # [{"c": code, ...params}]
    counters: dict = field(default_factory=lambda: {"manual_stops": 0, "resumes": 0, "outages": 0, "car_stops": 0})
    live_message_id: int | None = None
    interim_mark: int = 0
    scheduled_notified: bool = False
    nocharge_notified: bool = False
    seg: Segment | None = None
    seg_count: int = 0
    last_end_reason: str | None = None

    def charge_s(self, now: float) -> float:
        extra = (now - self.seg.start_ts) if self.seg else 0.0
        return self.charge_s_closed + extra

    def energy_best(self) -> float:
        return self.energy_device if self.energy_device is not None else self.energy_calc

    def avg_kw(self, now: float) -> float:
        s = self.charge_s(now)
        return self.energy_calc / (s / 3600.0) if s > 60 else 0.0


@dataclass
class DeviceState:
    work_state: str | None = None
    work_state_ts: float = 0.0
    switch: bool | None = None
    switch_ts: float = 0.0
    cur_set: int | None = None
    work_mode: str | None = None
    fault: int = 0
    timer_raw: str | None = None
    version: str | None = None
    phases: dict = field(default_factory=lambda: {k: (0.0, 0.0, 0.0) for k in ("a", "b", "c")})
    power_kw: float = 0.0
    power_ts: float = 0.0
    dp25: int | None = None
    dp25_ts: float = 0.0
    raw: dict = field(default_factory=dict)
    raw_ts: dict = field(default_factory=dict)
    online: bool = False
    last_rx: float = 0.0

    def plugged(self) -> bool:
        return self.work_state in DP.PLUGGED_STATES

    def sample_dict(self) -> dict:
        a, b, c = self.phases["a"], self.phases["b"], self.phases["c"]
        return {
            "work_state": self.work_state, "switch": None if self.switch is None else int(self.switch),
            "cur_set": self.cur_set, "work_mode": self.work_mode, "fault": self.fault, "power_kw": self.power_kw,
            "va": a[0], "ia": a[1], "pa": a[2], "vb": b[0], "ib": b[1], "pb": b[2], "vc": c[0], "ic": c[1], "pc": c[2],
            "timer_raw": self.timer_raw,
        }


class Monitor:
    def __init__(self, settings: Settings, db: DB, sink: Sink, reports: Reports, now_fn=time.time):
        self.s = settings
        self.db = db
        self.sink = sink
        self.R = reports
        self.now = now_fn
        self.st = DeviceState()
        self.sess: Session | None = None
        self.initialized = False
        self.started_ts = now_fn()
        self._confirmed_state: str | None = None
        self._pending_state: tuple[str, float] | None = None
        self._reboot_until = 0.0
        self._cur_set_before_reboot: int | None = None
        self._switch_off_at: float | None = None
        self._unplug_at: float | None = None  # unplug accepted, waiting for DP25
        self._unplug_while_charging = False
        self._nocurrent_since: float | None = None
        self._nocurrent_warned = False
        self._fault_since: float | None = None
        self._last_sample_ts = 0.0
        self._last_sample: dict | None = None
        self._last_integrate_ts: float | None = None
        self._last_persist = 0.0
        self._offline_since: float | None = None
        self._last_cur_set_change = 0.0
        self._dp25_pending: tuple[float, float] | None = None  # (ts, kWh) received while plugged, decision pending
        v = db.get_meta("last_dp25")
        self._last_dp25: int | None = int(v) if v else None

    # ------------------------------------------------------------------ entry points
    def on_dps(self, ts: float, dps: dict[str, Any], snapshot: bool = False) -> None:
        changes = self._apply_dps(ts, dps, snapshot)
        if not self.initialized:
            self._initialize(ts)
            return
        self._integrate(ts)
        self._react(ts, changes)
        self._evaluate(ts)
        self._maybe_sample(ts)

    def on_tick(self, ts: float) -> None:
        if not self.initialized:
            return
        self._integrate(ts)
        self._evaluate(ts)
        self._maybe_sample(ts)
        if ts - self._last_persist >= 60:
            self._persist_session()
            self._last_persist = ts

    def on_conn(self, ts: float, state: str, info: dict) -> None:
        if state == "offline":
            self.st.online = False
            self._offline_since = info.get("since") or ts
            if self.initialized:
                self._emit(ts, "offline", self.R.offline(ts, self._offline_since, self.sess, self.st))
                if self.sess:
                    self.sess.counters["outages"] += 1
                    self.sess.warnings.append({"c": "outage_start", "t": ts})
        elif state == "online":
            self.st.online = True
            self.st.last_rx = ts
            outage = info.get("outage_s") or 0.0
            if self.initialized and self._offline_since is not None:
                self._emit(ts, "online", self.R.online(ts, outage, self.st))
                if self.sess:
                    self.sess.warnings.append({"c": "outage_end", "t": ts, "dur": outage})
                    self._last_integrate_ts = ts  # energy during the outage is unknown
            self._offline_since = None
        elif state == "auth_error":
            self._emit(ts, "auth_error", self.R.auth_error())
        elif state == "ip_changed":
            self.db.set_meta("device_ip", info.get("new", ""))
            self._emit(ts, "ip_changed", self.R.ip_changed(info.get("old"), info.get("new")))

    # ------------------------------------------------------------------ applying DPs
    def _apply_dps(self, ts: float, dps: dict[str, Any], snapshot: bool) -> dict[str, tuple[Any, Any]]:
        """Write raw DPs into the device state; return {dp: (old, new)} for the ones that changed."""
        st = self.st
        st.last_rx = ts
        changes: dict[str, tuple[Any, Any]] = {}
        for key, value in dps.items():
            old = st.raw.get(key)
            st.raw[key] = value
            st.raw_ts[key] = ts
            if key in DP.DP_PHASE:
                dec = DP.decode_phase(value) if isinstance(value, str) else None
                if dec:
                    st.phases[DP.DP_PHASE[key]] = dec
                continue
            if old == value and key != DP.DP_SESSION_ENERGY:
                continue
            if key == DP.DP_WORK_STATE:
                st.work_state, st.work_state_ts = value, ts
            elif key == DP.DP_SWITCH:
                st.switch, st.switch_ts = bool(value), ts
            elif key == DP.DP_CUR_SET:
                st.cur_set = int(value)
            elif key == DP.DP_WORK_MODE:
                st.work_mode = value
            elif key == DP.DP_FAULT:
                st.fault = int(value)
            elif key == DP.DP_TIMER:
                st.timer_raw = DP.raw_hex(value) if isinstance(value, str) else str(value)
            elif key == DP.DP_VERSION:
                st.version = str(value)
            elif key == DP.DP_POWER:
                st.power_kw, st.power_ts = int(value) / 1000.0, ts
            elif key == DP.DP_SESSION_ENERGY:
                st.dp25, st.dp25_ts = int(value), ts
                last = self._last_dp25
                self._last_dp25 = int(value)
                if snapshot or not self.initialized or last == int(value):
                    continue  # startup dump or a repeated value in a query reply: not an event
                self.db.set_meta("last_dp25", str(int(value)))
            changes[key] = (old, value)
        return changes

    # ------------------------------------------------------------------ startup
    def _initialize(self, ts: float) -> None:
        self.initialized = True
        self._confirmed_state = self.st.work_state
        self._last_integrate_ts = ts
        self._cur_set_before_reboot = self.st.cur_set
        row = self.db.open_session()
        if row:
            self.sess = self._session_from_row(row)
            log.info("resuming open session #%d", self.sess.id)
            seg_row = self.db.open_segment(self.sess.id)
            if seg_row:
                self.sess.seg = Segment(id=seg_row["id"], start_ts=seg_row["start_ts"], energy=seg_row["energy_kwh"] or 0.0)
            if not self.st.plugged():
                # the car was unplugged while the bot was down
                last = self.db.q1("SELECT MAX(ts) AS t FROM samples WHERE session_id=?", (self.sess.id,))
                when = (last["t"] if last and last["t"] else ts)
                if self.sess.seg:
                    self._close_segment(when, "unknown_bot_down")
                self.sess.notes.append({"c": "unplug_bot_down"})
                self._finish_unplug(ts, unplug_ts=when, reason="bot_down_unplug")
            else:
                if self.sess.seg and self.st.power_kw <= P_ON:
                    last = self.db.q1("SELECT MAX(ts) AS t FROM samples WHERE session_id=? AND power_kw>?", (self.sess.id, P_ON))
                    self._close_segment((last["t"] if last and last["t"] else ts), "unknown_restart")
                elif not self.sess.seg and self.st.power_kw > P_ON:
                    self._open_segment(ts, quiet=True)
        elif self.st.plugged():
            self.sess = self._new_session(ts)
            self.sess.notes.append({"c": "plugged_at_start"})
            self.sess.nocharge_notified = True
            self.sess.scheduled_notified = True
            if self.st.power_kw > P_ON:
                self._open_segment(ts, quiet=True)
        self.sink.fast(self.sess is not None and self.sess.seg is not None)
        self._persist_session()

    def _session_from_row(self, row) -> Session:
        s = Session(id=row["id"], plug_ts=row["plug_ts"])
        s.charge_start_ts = row["charge_start_ts"]
        s.charge_end_ts = row["charge_end_ts"]
        s.energy_calc = row["energy_calc_kwh"] or 0.0
        s.energy_device = row["energy_device_kwh"]
        s.energy_device2 = row["energy_device2_kwh"]
        s.device_closed_ts = row["device_closed_ts"]
        s.peak_kw = row["peak_kw"] or 0.0
        s.charge_s_closed = row["charge_s"] or 0.0
        s.live_message_id = row["live_message_id"]
        cost = json.loads(row["cost_json"]) if row["cost_json"] else {}
        s.energy_by_band = {b: float(cost.get("kwh", {}).get(b, 0.0)) for b in BANDS}
        phases = json.loads(row["phase_json"]) if row["phase_json"] else {}
        s.phases = {k: PhaseStats.from_dict(phases.get(k)) for k in ("a", "b", "c")}
        s.warnings = [w for w in (json.loads(row["warnings_json"]) if row["warnings_json"] else []) if isinstance(w, dict)]
        counters = json.loads(row["counters_json"]) if row["counters_json"] else {}
        s.counters.update(counters.get("counters", {}))
        s.interim_mark = int(counters.get("interim_mark", 0))
        s.seg_count = int(counters.get("seg_count", 0))
        s.scheduled_notified = bool(counters.get("scheduled_notified", False))
        s.nocharge_notified = bool(counters.get("nocharge_notified", False))
        s.last_end_reason = counters.get("last_end_reason")
        s.notes = [n for n in (json.loads(row["notes_json"]) if row["notes_json"] else []) if isinstance(n, dict)]
        return s

    def _new_session(self, plug_ts: float) -> Session:
        sid = self.db.create_session(plug_ts)
        return Session(id=sid, plug_ts=plug_ts)

    def _persist_session(self) -> None:
        s = self.sess
        if not s:
            return
        now = self.now()
        self.db.update_session(
            s.id,
            charge_start_ts=s.charge_start_ts,
            charge_end_ts=s.charge_end_ts,
            energy_calc_kwh=round(s.energy_calc, 4),
            energy_device_kwh=s.energy_device,
            energy_device2_kwh=s.energy_device2,
            device_closed_ts=s.device_closed_ts,
            peak_kw=round(s.peak_kw, 3),
            charge_s=int(s.charge_s_closed),
            cost_json=json.dumps({"kwh": {b: round(v, 4) for b, v in s.energy_by_band.items()}}),
            phase_json=json.dumps({k: p.to_dict() for k, p in s.phases.items()}),
            warnings_json=json.dumps(s.warnings, ensure_ascii=False),
            notes_json=json.dumps(s.notes, ensure_ascii=False),
            counters_json=json.dumps({
                "counters": s.counters, "interim_mark": s.interim_mark, "seg_count": s.seg_count,
                "scheduled_notified": s.scheduled_notified, "nocharge_notified": s.nocharge_notified,
                "last_end_reason": s.last_end_reason,
            }, ensure_ascii=False),
            live_message_id=s.live_message_id,
            avg_kw=round(s.avg_kw(now), 3),
        )
        if s.seg:
            self.db.update_segment(s.seg.id, energy_kwh=round(s.seg.energy, 4))

    # ------------------------------------------------------------------ energy integration
    def _integrate(self, ts: float) -> None:
        """Assume constant power since the last integration step; add energy per tariff band."""
        if self._last_integrate_ts is None:
            self._last_integrate_ts = ts
            return
        t0, self._last_integrate_ts = self._last_integrate_ts, ts
        s = self.sess
        if not s or not s.seg or ts <= t0 or not self.st.online:
            return
        kw = 0.0 if self.st.switch is False else self.st.power_kw  # with the switch off the reported power is stale
        if kw <= P_ON:
            return
        for band, secs in split_interval(t0, ts, self.s.tz):
            e = kw * secs / 3600.0
            s.energy_calc += e
            s.energy_by_band[band] = s.energy_by_band.get(band, 0.0) + e
            s.seg.energy += e

    # ------------------------------------------------------------------ immediate reactions
    def _react(self, ts: float, changes: dict[str, tuple[Any, Any]]) -> None:
        st = self.st
        in_reboot = ts < self._reboot_until
        # Reboot signature: current limit drops to 6 while the state shows free
        if DP.DP_CUR_SET in changes and changes[DP.DP_CUR_SET][1] == 6 and changes[DP.DP_CUR_SET][0] not in (None, 6):
            self._cur_set_before_reboot = changes[DP.DP_CUR_SET][0]
            if st.work_state == "charger_free" or DP.DP_WORK_STATE in changes:
                self._start_reboot_window(ts)
                in_reboot = True
        if not in_reboot and DP.DP_CUR_SET in changes:
            old, new = changes[DP.DP_CUR_SET]
            if old is not None and new != 6:
                self._last_cur_set_change = ts
                self._emit(ts, "setting", self.R.setting_changed(ts, "what_current_limit", f"{old} A", f"{new} A"))
                self._warn({"c": "setting", "t": ts, "text": self.R.L("n_current_limit", old=old, new=new)})
        if DP.DP_WORK_MODE in changes and not in_reboot:
            old, new = changes[DP.DP_WORK_MODE]
            if old is not None:
                self._emit(ts, "setting", self.R.setting_changed(ts, "what_work_mode", self.R.mode(old), self.R.mode(new)))
        if DP.DP_TIMER in changes and not in_reboot:
            old, new = changes[DP.DP_TIMER]
            if old is not None:
                self._emit(ts, "setting", self.R.timer_changed(ts, DP.raw_hex(old), DP.raw_hex(new)))
        if DP.DP_FAULT in changes:
            self._on_fault(ts, changes[DP.DP_FAULT][1])
        if DP.DP_SWITCH in changes and changes[DP.DP_SWITCH][0] is not None:
            self._on_switch(ts, bool(changes[DP.DP_SWITCH][1]))
        if DP.DP_SESSION_ENERGY in changes:
            self._on_dp25(ts, int(changes[DP.DP_SESSION_ENERGY][1]))
        for key in changes:
            if key in (DP.DP_WORK_STATE, DP.DP_CUR_SET, DP.DP_WORK_MODE, DP.DP_SWITCH, DP.DP_FAULT, DP.DP_SESSION_ENERGY, DP.DP_TIMER):
                old, new = changes[key]
                self.db.insert_transition(ts, self.sess.id if self.sess else None, key, DP.DP_NAMES.get(key, key), old, new)
        # peak power and phase statistics
        s = self.sess
        if s and s.seg and st.power_kw > P_ON and st.switch is not False:
            s.peak_kw = max(s.peak_kw, st.power_kw)
            s.seg.peak_kw = max(s.seg.peak_kw, st.power_kw)
            s.seg.history.append((ts, st.power_kw))
            for k in ("a", "b", "c"):
                v, i, _ = st.phases[k]
                s.phases[k].update(v, i)

    def _start_reboot_window(self, ts: float) -> None:
        if ts < self._reboot_until:
            return
        self._reboot_until = ts + REBOOT_WINDOW_S
        gap = ts - self._last_sample_ts if self._last_sample_ts else 0.0
        self._emit(ts, "rebooted", self.R.rebooted(ts, gap, self.st))
        if self.sess:
            self.sess.warnings.append({"c": "reboot", "t": ts})
            self.sess.counters["outages"] += 1

    def _on_fault(self, ts: float, bitmap: int) -> None:
        if bitmap:
            self._fault_since = self._fault_since or ts
            self._emit(ts, "fault", self.R.fault(ts, bitmap, self.st))
            self._warn({"c": "fault", "t": ts, "bits": bitmap})
        elif self._fault_since is not None:
            self._emit(ts, "fault_cleared", self.R.fault_cleared(ts, ts - self._fault_since))
            self._fault_since = None

    def _on_switch(self, ts: float, on: bool) -> None:
        if not on:
            self._switch_off_at = ts  # decide in 10 s: unplug or manual stop
        else:
            self._switch_off_at = None

    def _on_dp25(self, ts: float, value: int) -> None:
        kwh = value / 100.0
        s = self.sess
        if not s:
            return
        if self._unplug_at is not None or (self.st.work_state == "charger_free" and ts - self.st.work_state_ts < 20):
            self._assign_device_energy(s, kwh)  # counter sent during the unplug
            return
        self._dp25_pending = (ts, kwh)

    @staticmethod
    def _assign_device_energy(s: Session, kwh: float) -> None:
        if s.energy_device is None:
            s.energy_device = kwh
        else:
            s.energy_device2 = kwh

    def _resolve_dp25(self, ts: float) -> None:
        if self._dp25_pending is None or not self.sess:
            self._dp25_pending = None
            return
        at, kwh = self._dp25_pending
        s = self.sess
        if self._unplug_at is not None or self.st.work_state == "charger_free":
            self._dp25_pending = None
            self._assign_device_energy(s, kwh)
        elif ts - at >= DP25_DECIDE_S:
            self._dp25_pending = None
            self._assign_device_energy(s, kwh)
            s.device_closed_ts = at
            self._emit(at, "device_record", self.R.device_record_closed(at, kwh, at - s.plug_ts, self.st))
            s.notes.append({"c": "device_record", "t": at, "kwh": kwh})

    # ------------------------------------------------------------------ time-based evaluation
    def _evaluate(self, ts: float) -> None:
        st = self.st
        s = self.sess
        in_reboot = ts < self._reboot_until
        if in_reboot and st.cur_set == self._cur_set_before_reboot and st.work_state != "charger_free":
            self._reboot_until = 0.0  # the charger recovered
            in_reboot = False

        # --- DP3 transition acceptance (debounce) ---
        raw = st.work_state
        if raw != self._confirmed_state:
            if self._pending_state is None or self._pending_state[0] != raw:
                self._pending_state = (raw, st.work_state_ts if st.work_state_ts else ts)
            since = self._pending_state[1]
            immediate = raw == "charger_charging" and st.power_kw > P_ON
            if (ts - since >= self.s.debounce_s or immediate) and not (in_reboot and raw == "charger_free"):
                old = self._confirmed_state
                self._confirmed_state = raw
                self._pending_state = None
                self._on_state(ts, old, raw, since)
        else:
            self._pending_state = None

        # --- switch went off: manual stop? ---
        if self._switch_off_at is not None and ts - self._switch_off_at >= MANUAL_WAIT_S:
            off_at = self._switch_off_at
            self._switch_off_at = None
            if st.switch is False and self._confirmed_state != "charger_free" and self._unplug_at is None and s:
                if s.seg:
                    self._close_segment(off_at, "manual_stop")
                    s.counters["manual_stops"] += 1
                    self._emit(ts, "stopped", self.R.paused_manual(off_at, s, self.now()))
                    self.sink.live_update(s)
                else:
                    s.notes.append({"c": "switch_off_idle"})

        # --- power-based charging segments ---
        if s:
            if st.power_kw > P_ON and st.online and st.switch is not False:
                if s.seg is None and self._unplug_at is None:
                    self._open_segment(ts)
                elif s.seg is not None:
                    s.seg.zero_since = None
            elif s.seg is not None:
                if s.seg.zero_since is None:
                    s.seg.zero_since = st.power_ts if st.power_ts else ts
                elif ts - s.seg.zero_since >= ZERO_END_S and self._switch_off_at is None:
                    self._end_segment_by_power(ts, s.seg.zero_since)

        self._resolve_dp25(ts)
        # --- unplug: did DP25 arrive? ---
        if self._unplug_at is not None and (ts - self._unplug_at >= UNPLUG_DP25_WAIT_S or (s and s.energy_device is not None and st.dp25_ts >= self._unplug_at - 20)):
            self._finish_unplug(ts, unplug_ts=self._unplug_at, reason="unplugged")

        # --- plugged in but not charging / scheduled waiting ---
        if s and s.seg is None and self._unplug_at is None and st.plugged() and st.online:
            since_plug = ts - s.plug_ts
            if st.work_mode in ("charge_schedule", "charge_delay") and not s.scheduled_notified and since_plug >= SCHEDULED_AFTER_S:
                s.scheduled_notified = True
                self._emit(ts, "waiting", self.R.waiting_scheduled(ts, st))
            elif s.seg_count == 0 and not s.nocharge_notified and since_plug >= NOCHARGE_AFTER_S and st.work_mode == "charge_now" and st.switch is not False:
                s.nocharge_notified = True
                self._emit(ts, "no_charge", self.R.no_charge_after_plug(ts, since_plug, st))

        # --- "charging" reported but no current ---
        if self._confirmed_state == "charger_charging" and st.power_kw <= P_ON and st.online:
            self._nocurrent_since = self._nocurrent_since or ts
            if not self._nocurrent_warned and ts - self._nocurrent_since >= self.s.no_current_s:
                self._nocurrent_warned = True
                self._emit(ts, "no_current", self.R.no_current(ts, ts - self._nocurrent_since, st))
                self._warn({"c": "no_current", "t": ts})
        else:
            self._nocurrent_since = None
            self._nocurrent_warned = False

        # --- warnings and interim reports while charging ---
        if s and s.seg and st.online:
            self._check_warnings(ts, s)
            mark = int(s.charge_s(ts) // (self.s.interim_report_min * 60))
            if mark > s.interim_mark:
                s.interim_mark = mark
                self.sink.interim(s)

    def _on_state(self, ts: float, old: str | None, new: str, since: float) -> None:
        st = self.st
        s = self.sess
        if new == "charger_free":
            if s and self._unplug_at is None:
                self._unplug_at = since
                self._unplug_while_charging = s.seg is not None
                if s.seg:
                    self._close_segment(since, "unplugged_charging")
                self.sink.fast(False)
            return
        if old in (None, "charger_free") and new in DP.PLUGGED_STATES:
            if self._unplug_at is not None:
                # plugged in again before the unplug was finalised: close the old session first
                self._finish_unplug(ts, unplug_ts=self._unplug_at, reason="unplugged")
            if not self.sess:
                self.sess = self._new_session(since)
                self._emit(ts, "plugged", self.R.plugged(since, st))
                self._persist_session()
            return
        if new == "charger_pause" and s and s.seg:
            self._close_segment(since, "paused")
            self._emit(ts, "paused", self.R.paused_device(since, s, self.now()))
            self.sink.live_update(s)
        elif new == "charger_end" and s and s.seg:
            self._close_segment(since, "car_full")
            s.counters["car_stops"] += 1
            self._emit(ts, "complete", self.R.car_stopped(since, s, taper=True, now=self.now()))
            self.sink.live_update(s)
        elif new in DP.FAULT_STATES and s and s.seg:
            self._close_segment(since, "fault")
            if not st.fault:
                self._emit(ts, "fault", self.R.fault(ts, 0, st))

    # ------------------------------------------------------------------ segments
    def _open_segment(self, ts: float, quiet: bool = False) -> None:
        s = self.sess
        if not s:
            s = self.sess = self._new_session(ts)
        seg_id = self.db.create_segment(s.id, ts)
        s.seg = Segment(id=seg_id, start_ts=ts)
        s.seg_count += 1
        self._last_integrate_ts = ts
        first = s.charge_start_ts is None
        if first:
            s.charge_start_ts = ts
        self.sink.fast(True)
        if quiet:
            return
        if first:
            self._emit(ts, "charging_started", self.R.charging_started(ts, self.st))
            self.sink.live_create(s)
        else:
            s.counters["resumes"] += 1
            self._emit(ts, "resumed", self.R.resumed(ts, self.st))
            if s.live_message_id:
                self.sink.live_update(s)
            else:
                self.sink.live_create(s)
        self._persist_session()

    def _close_segment(self, end_ts: float, reason: str) -> None:
        s = self.sess
        if not s or not s.seg:
            return
        seg = s.seg
        end_ts = max(end_ts, seg.start_ts)
        s.charge_s_closed += end_ts - seg.start_ts
        s.charge_end_ts = end_ts
        s.last_end_reason = reason
        self.db.update_segment(seg.id, end_ts=end_ts, energy_kwh=round(seg.energy, 4), end_reason=reason)
        s.seg = None
        self.sink.fast(False)
        self._persist_session()

    def _end_segment_by_power(self, ts: float, zero_since: float) -> None:
        s = self.sess
        st = self.st
        if not s or not s.seg:
            return
        seg = s.seg
        if not st.online:
            reason, taper = "outage", False
        elif st.fault:
            reason, taper = "fault", False
        elif st.switch is False:
            reason, taper = "manual_stop", False
        else:
            taper = self._is_taper(seg, zero_since)
            reason = "car_full" if taper else "car_stopped"
        self._close_segment(zero_since, reason)
        if reason in ("car_full", "car_stopped"):
            s.counters["car_stops"] += 1
            self._emit(ts, "complete" if taper else "car_stopped", self.R.car_stopped(zero_since, s, taper=taper, now=self.now()))
        elif reason == "manual_stop":
            s.counters["manual_stops"] += 1
            self._emit(ts, "stopped", self.R.paused_manual(zero_since, s, self.now()))
        elif reason == "outage":
            self._emit(ts, "charging_lost", self.R.charging_lost(zero_since, s, self.now()))
        self.sink.live_update(s)

    @staticmethod
    def _is_taper(seg: Segment, end_ts: float) -> bool:
        """Gradual decline: the last 5 minutes averaged below 60 % of the segment's peak power."""
        if end_ts - seg.start_ts < 10 * 60 or seg.peak_kw <= 0:
            return False
        last = [kw for t, kw in seg.history if end_ts - 300 <= t <= end_ts]
        if len(last) < 3:
            return False
        return (sum(last) / len(last)) < 0.6 * seg.peak_kw

    # ------------------------------------------------------------------ unplug and session close
    def _finish_unplug(self, ts: float, unplug_ts: float, reason: str) -> None:
        s = self.sess
        self._unplug_at = None
        while_charging = self._unplug_while_charging
        self._unplug_while_charging = False
        if not s:
            return
        if s.seg:
            self._close_segment(unplug_ts, "unplugged_charging")
            while_charging = True
        s.unplug_ts = unplug_ts
        end_reason = self._session_end_reason(s, reason, while_charging)
        energy_best = s.energy_best()
        cost = self.R.cost(s.energy_by_band if s.energy_calc > 0 else {}, energy_best)
        self._persist_session()
        self.db.update_session(
            s.id,
            unplug_ts=unplug_ts,
            plugged_s=int(unplug_ts - s.plug_ts),
            energy_kwh=round(energy_best, 3),
            cost=round(cost, 2),
            end_reason=end_reason,
            closed=1,
        )
        text = self.R.session_summary(s, end_reason, unplug_ts)
        self._emit(unplug_ts, "unplugged", text)
        self.sink.session_closed(s, text)
        self.sess = None
        self.sink.fast(False)

    @staticmethod
    def _session_end_reason(s: Session, unplug_reason: str, while_charging: bool) -> str:
        if s.seg_count == 0:
            return "no_charge"
        if while_charging or s.last_end_reason == "unplugged_charging":
            return "unplugged_charging"
        if unplug_reason == "bot_down_unplug" and s.last_end_reason in (None, "unknown_bot_down"):
            return "bot_down_unplug"
        return s.last_end_reason or unplug_reason

    # ------------------------------------------------------------------ warnings
    def _warn(self, entry: dict) -> None:
        if self.sess:
            self.sess.warnings.append(entry)

    def _check_warnings(self, ts: float, s: Session) -> None:
        st = self.st
        seg = s.seg
        if not seg:
            return
        currents = {k: st.phases[k][1] for k in ("a", "b", "c")}
        volts = {k: st.phases[k][0] for k in ("a", "b", "c")}
        # voltage range (only on phases carrying current)
        for k in ("a", "b", "c"):
            if currents[k] > 0.2 and volts[k] > 50 and not (self.s.voltage_min <= volts[k] <= self.s.voltage_max):
                key = f"v_{k}"
                since = seg.timers.get(key + "_since")
                if since is None:
                    seg.timers[key + "_since"] = ts
                elif ts - since >= 30 and ts - seg.timers.get(key, 0) >= WARN_REPEAT_S:
                    seg.timers[key] = ts
                    self._emit(ts, "warn_voltage", self.R.warn_voltage(ts, k, volts[k]))
                    self._warn({"c": "voltage", "t": ts, "phase": k.upper(), "v": round(volts[k])})
            else:
                seg.timers.pop(f"v_{k}_since", None)
        amps = sorted(currents.values())
        if amps[-1] > 5.0:
            if amps[0] < self.s.phase_loss_min_a:
                self._persisting(ts, seg, "phase_loss", lambda: self.R.warn_phase_loss(ts, currents))
            elif (amps[-1] - amps[0]) / amps[-1] * 100.0 > self.s.imbalance_pct:
                self._persisting(ts, seg, "imbalance", lambda: self.R.warn_imbalance(ts, currents))
            else:
                seg.timers.pop("phase_loss_since", None)
                seg.timers.pop("imbalance_since", None)
        # unexpected power drop
        if "power_drop" not in seg.warned and ts - seg.start_ts > 5 * 60 and ts - self._last_cur_set_change > 5 * 60:
            older = [kw for t, kw in seg.history if ts - 7 * 60 <= t <= ts - 2 * 60]
            near_full = s.energy_calc >= 0.6 * self.s.battery_kwh / self.s.charge_efficiency
            if older and not near_full:
                avg = sum(older) / len(older)
                if avg > 1.0 and st.power_kw < avg * (1 - self.s.power_drop_pct / 100.0):
                    since = seg.timers.setdefault("power_drop_since", ts)
                    if ts - since >= WARN_PERSIST_S:
                        seg.warned.add("power_drop")
                        self._emit(ts, "warn_power", self.R.warn_power_drop(ts, avg, st.power_kw, st))
                        self._warn({"c": "power_drop", "t": ts, "a": round(avg, 1), "b": round(st.power_kw, 1)})
                else:
                    seg.timers.pop("power_drop_since", None)

    def _persisting(self, ts: float, seg: Segment, key: str, make_text) -> None:
        if key in seg.warned:
            return
        since = seg.timers.setdefault(key + "_since", ts)
        if ts - since >= WARN_PERSIST_S:
            seg.warned.add(key)
            self._emit(ts, "warn_" + key, make_text())
            self._warn({"c": key, "t": ts})

    # ------------------------------------------------------------------ helpers
    def _emit(self, ts: float, etype: str, text: str, details: dict | None = None) -> None:
        self.sink.event(ts, etype, text, details, self.sess.id if self.sess else None)

    def _maybe_sample(self, ts: float) -> None:
        d = self.st.sample_dict()
        if d != self._last_sample or ts - self._last_sample_ts >= SAMPLE_IDLE_S:
            self.db.insert_sample(ts, self.sess.id if self.sess else None, d)
            self._last_sample = d
            self._last_sample_ts = ts

    # ------------------------------------------------------------------ status for commands
    def charging(self) -> bool:
        return bool(self.sess and self.sess.seg)

    def status_dict(self, now: float) -> dict:
        st = self.st
        return {
            "online": st.online, "work_state": st.work_state, "confirmed": self._confirmed_state, "switch": st.switch,
            "cur_set": st.cur_set, "work_mode": st.work_mode, "fault": st.fault, "power_kw": st.power_kw,
            "phases": st.phases, "last_rx": st.last_rx, "uptime_s": now - self.started_ts, "version": st.version,
            "plugged": st.plugged(), "session": self.sess, "raw": st.raw, "raw_ts": st.raw_ts, "timer_raw": st.timer_raw,
            "offline_since": self._offline_since,
        }
