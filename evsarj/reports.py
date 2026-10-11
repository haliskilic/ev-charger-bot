"""Builds every Telegram text (HTML) from the message catalogue in i18n.py, in the configured language."""

from __future__ import annotations

import html
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import dp as DP
from .config import Settings
from .fmt import Formatter
from .i18n import Lang
from .tariff import BANDS, battery_pct, cost_of, latest_end, range_km

if TYPE_CHECKING:
    from .monitor import DeviceState, Session


def esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


class Reports:
    def __init__(self, settings: Settings):
        self.s = settings
        self.L = Lang(settings.language)
        self.F = Formatter(settings.language, settings.tz, settings.tariff.currency)

    def set_language(self, code: str) -> None:
        self.s.language = code
        self.L.set(code)
        self.F.set_language(code)

    # ---- small helpers (also used by the monitor) ----
    def hm(self, ts: float | None) -> str:
        return self.F.hm(ts)

    def dur(self, seconds: float | None) -> str:
        return self.F.duration(seconds)

    def mode(self, mode: str | None) -> str:
        return self.L("unknown") if mode is None else self.L("wm_" + mode)

    def state_name(self, state: str | None) -> str:
        return self.L("unknown") if state is None else self.L("ws_" + state)

    def fault_texts(self, bitmap: int) -> list[str]:
        out = [self.L("fault_bit", text=self.L(f"fault_{b}"), bit=b) for b in DP.fault_bits(bitmap)]
        unknown = bitmap >> DP.FAULT_BIT_COUNT
        if unknown:
            out.append(self.L("fault_unknown_bits", hex=f"{bitmap:#x}"))
        return out

    def end_reason(self, code: str | None, closed: bool = True) -> str:
        if not code:
            return self.L("er_ongoing") if not closed else self.L("none")
        return self.L("er_" + code) if self.L.has("er_" + code) else esc(code)

    def cost(self, energy_by_band: dict[str, float], energy_best: float) -> float:
        """Session cost: by tariff band when the distribution is known, otherwise energy × single price."""
        if energy_by_band and sum(energy_by_band.values()) > 0:
            calc_total = sum(energy_by_band.values())
            scale = energy_best / calc_total if calc_total > 0 and energy_best > 0 else 1.0
            return cost_of({b: v * scale for b, v in energy_by_band.items()}, self.s.tariff)
        return energy_best * self.s.tariff.single

    def cost_line(self, energy_by_band: dict[str, float]) -> str:
        t = self.s.tariff
        total = cost_of(energy_by_band, t)
        if t.type != "tou":
            return self.L("cost_single", cost=self.F.money(total), price=self.F.price(t.single))
        parts = [f"{self.L('band_' + b)} {self.F.kwh(energy_by_band.get(b, 0.0), 1)}" for b in BANDS if energy_by_band.get(b, 0.0) > 0.0005]
        return self.L("cost_tou", cost=self.F.money(total), parts=" · ".join(parts)) if parts else self.F.money(total)

    def _phases_line(self, st: "DeviceState") -> str:
        a, b, c = st.phases["a"], st.phases["b"], st.phases["c"]
        active = sum(1 for p in (a, b, c) if p[1] > 0.2)
        return self.L("phases_line", a=self.F.num(a[1], 1), b=self.F.num(b[1], 1), c=self.F.num(c[1], 1), n=active)

    def state_desc(self, online: bool, power_kw: float, work_state: str | None, switch: bool | None, work_mode: str | None) -> str:
        if not online:
            return self.L("state_offline")
        if power_kw > 0.05:
            return self.L("state_charging", kw=self.F.kw(power_kw))
        if work_state == "charger_free":
            return self.L("state_idle")
        if work_state == "charger_wait":
            if switch is False:
                return self.L("state_plugged_switch_off")
            if work_mode in ("charge_schedule", "charge_delay"):
                return self.L("state_plugged_waiting_mode", mode=self.mode(work_mode))
            return self.L("state_plugged_waiting")
        return self.state_name(work_state)

    def _desc(self, st: "DeviceState") -> str:
        return self.state_desc(st.online, st.power_kw, st.work_state, st.switch, st.work_mode)

    def _estimate_line(self, energy_kwh: float) -> str:
        return self.L("estimate_line", pct=self.F.pct(battery_pct(energy_kwh, self.s)), km=self.F.num(range_km(energy_kwh, self.s), 0))

    def warning_text(self, w: dict) -> str:
        c = w.get("c", "")
        t = self.F.hm(w.get("t"))
        if c == "outage_end":
            return self.L("w_outage_end", time=t, dur=self.dur(w.get("dur")))
        if c == "fault":
            return self.L("w_fault", time=t, texts=", ".join(self.fault_texts(int(w.get("bits", 0)))))
        if c == "voltage":
            return self.L("w_voltage", time=t, phase=w.get("phase"), v=w.get("v"))
        if c == "power_drop":
            return self.L("w_power_drop", time=t, a=self.F.num(w.get("a"), 1), b=self.F.num(w.get("b"), 1))
        if c == "setting":
            return self.L("w_setting", time=t, text=w.get("text", ""))
        return self.L("w_" + c, time=t)

    def note_text(self, n: dict) -> str:
        c = n.get("c", "")
        if c == "device_record":
            return self.L("n_device_record", time=self.F.hm(n.get("t")), kwh=self.F.kwh(n.get("kwh")))
        return self.L("n_" + c)

    # ---- events ----
    def bot_restarted(self, ts: float, st: "DeviceState", sess: "Session | None") -> str:
        head = self.L("bot_restarted", date=self.F.date_short(ts), time=self.hm(ts), online=self.L("online" if st.online else "offline"), desc=esc(self._desc(st)))
        if sess and sess.charge_start_ts:
            return head + "\n" + self.L("bot_restarted_open_charging", plug=self.hm(sess.plug_ts), kwh=self.F.kwh(sess.energy_calc, 1))
        if sess:
            return head + "\n" + self.L("bot_restarted_open_nocharge", plug=self.hm(sess.plug_ts))
        return head + " · " + self.L("bot_restarted_no_session")

    def plugged(self, ts: float, st: "DeviceState") -> str:
        return self.L("plugged", time=self.hm(ts), amps=st.cur_set if st.cur_set is not None else "—", mode=esc(self.mode(st.work_mode)))

    def charging_started(self, ts: float, st: "DeviceState") -> str:
        return self.L("charging_started", time=self.hm(ts), kw=self.F.kw(st.power_kw), phases=self._phases_line(st))

    def resumed(self, ts: float, st: "DeviceState") -> str:
        return self.L("resumed", time=self.hm(ts), kw=self.F.kw(st.power_kw), phases=self._phases_line(st))

    def paused_manual(self, ts: float, s: "Session", now: float) -> str:
        return self.L("paused_manual", time=self.hm(ts), kwh=self.F.kwh(s.energy_calc), dur=self.dur(s.charge_s(now)))

    def paused_device(self, ts: float, s: "Session", now: float) -> str:
        return self.L("paused_device", time=self.hm(ts), kwh=self.F.kwh(s.energy_calc), dur=self.dur(s.charge_s(now)))

    def car_stopped(self, ts: float, s: "Session", taper: bool, now: float) -> str:
        stats = self.L("session_stats", kwh=self.F.kwh(s.energy_calc), dur=self.dur(s.charge_s(now)), kw=self.F.kw(s.avg_kw(now)))
        return self.L("car_full" if taper else "car_stopped", time=self.hm(ts), stats=stats)

    def charging_lost(self, ts: float, s: "Session", now: float) -> str:
        return self.L("charging_lost", time=self.hm(ts), kwh=self.F.kwh(s.energy_calc), dur=self.dur(s.charge_s(now)))

    def no_current(self, ts: float, secs: float, st: "DeviceState") -> str:
        v = " / ".join(self.F.num(st.phases[k][0], 0) for k in ("a", "b", "c"))
        return self.L("no_current", time=self.hm(ts), secs=int(secs), v=v)

    def waiting_scheduled(self, ts: float, st: "DeviceState") -> str:
        return self.L("waiting_scheduled", time=self.hm(ts), mode=esc(self.mode(st.work_mode)))

    def no_charge_after_plug(self, ts: float, secs: float, st: "DeviceState") -> str:
        return self.L("no_charge_after_plug", time=self.hm(ts), dur=self.dur(secs))

    def fault(self, ts: float, bitmap: int, st: "DeviceState") -> str:
        texts = self.fault_texts(bitmap) or [self.L("fault_no_detail")]
        charging = self.L("fault_charging_stopped" if st.power_kw <= 0.05 else "fault_charging_continues")
        return self.L("fault", time=self.hm(ts), texts=esc(", ".join(texts)), state=esc(st.work_state or "?"), charging=charging)

    def fault_cleared(self, ts: float, secs: float) -> str:
        return self.L("fault_cleared", time=self.hm(ts), dur=self.dur(secs))

    def offline(self, ts: float, since: float, s: "Session | None", st: "DeviceState") -> str:
        text = self.L("offline_event", time=self.hm(ts), dur=self.dur(ts - since), last=self.hm(since))
        if s and s.seg:
            text += self.L("offline_charging", kwh=self.F.kwh(s.energy_calc))
        return text

    def online(self, ts: float, outage_s: float, st: "DeviceState") -> str:
        return self.L("online_event", time=self.hm(ts), dur=self.dur(outage_s), desc=esc(self._desc(st)))

    def rebooted(self, ts: float, gap_s: float, st: "DeviceState") -> str:
        gap = self.L("rebooted_gap", dur=self.dur(gap_s)) if gap_s >= 5 else ""
        desc = esc(self._desc(st))
        return self.L("rebooted", time=self.hm(ts), gap=gap, desc=desc[:1].upper() + desc[1:])

    def setting_changed(self, ts: float, what_key: str, old: str, new: str) -> str:
        return self.L("setting_changed", time=self.hm(ts), what=self.L(what_key), old=esc(old), new=esc(new))

    def timer_changed(self, ts: float, old: str, new: str) -> str:
        return self.L("timer_changed", time=self.hm(ts), old=esc(old), new=esc(new))

    def device_record_closed(self, ts: float, kwh: float, plugged_s: float, st: "DeviceState") -> str:
        why = self.L("device_record_12h") if plugged_s >= 11 * 3600 else ""
        extra = self.L("device_record_switch_off") if st.switch is False else ""
        return self.L("device_record_closed", why=why, time=self.hm(ts), kwh=self.F.kwh(kwh), dur=self.dur(plugged_s), extra=extra)

    def warn_voltage(self, ts: float, phase: str, volt: float) -> str:
        return self.L("warn_voltage", time=self.hm(ts), phase=phase.upper(), v=self.F.num(volt, 0), min=self.F.num(self.s.voltage_min, 0), max=self.F.num(self.s.voltage_max, 0))

    def warn_phase_loss(self, ts: float, currents: dict[str, float]) -> str:
        lost = [k.upper() for k, v in currents.items() if v < self.s.phase_loss_min_a]
        active = [f"{k.upper()} {self.F.num(v, 1)} A" for k, v in currents.items() if v >= self.s.phase_loss_min_a]
        return self.L("warn_phase_loss", time=self.hm(ts), lost=", ".join(lost), active=", ".join(active), n=len(active))

    def warn_imbalance(self, ts: float, currents: dict[str, float]) -> str:
        vals = [currents[k] for k in ("a", "b", "c")]
        diff = (max(vals) - min(vals)) / max(vals) * 100.0
        return self.L("warn_imbalance", time=self.hm(ts), amps=" / ".join(self.F.num(v, 1) for v in vals), pct=self.F.pct(diff))

    def warn_power_drop(self, ts: float, before: float, now_kw: float, st: "DeviceState") -> str:
        return self.L("warn_power_drop", time=self.hm(ts), before=self.F.kw(before, 1), now=self.F.kw(now_kw, 1), amps=st.cur_set)

    def auth_error(self) -> str:
        return self.L("auth_error")

    def ip_changed(self, old: str | None, new: str | None) -> str:
        return self.L("ip_changed", old=esc(old), new=esc(new))

    # ---- live status / interim ----
    def live_status(self, s: "Session", st: "DeviceState", now: float, final: bool = False) -> str:
        if final:
            return self.L("live_final", time=self.hm(now))
        charge_s = s.charge_s(now)
        avg = s.avg_kw(now)
        a, b, c = st.phases["a"], st.phases["b"], st.phases["c"]
        active = sum(1 for p in (a, b, c) if p[1] > 0.2)
        state = self.L("live_charging" if (s.seg and st.power_kw > 0.05) else "live_stopped", dur=self.dur(charge_s), kwh=self.F.kwh(s.energy_calc, 1))
        lines = [
            self.L("live_head", time=self.hm(now), min=self.s.live_status_min),
            state,
            "",
            self.L("live_power", kw=self.F.kw(st.power_kw, 1), n=active, amps=st.cur_set if st.cur_set is not None else "—"),
        ]
        for name, p in (("A", a), ("B", b), ("C", c)):
            lines.append(self.L("live_phase", name=name, v=self.F.num(p[0], 0), a=self.F.num(p[1], 1), kw=self.F.kw(p[2])))
        lines.append(self.L("live_avg", kw=self.F.kw(avg, 1)))
        lines.append(self.L("live_cost", cost=self.F.money(self.cost(s.energy_by_band, s.energy_calc))))
        lines.append(self._estimate_line(s.energy_calc))
        end = latest_end(now, s.energy_calc, st.power_kw, avg, self.s) if s.seg else None
        if end:
            lines.append(self.L("live_latest_end", time=self.hm(end)))
        return "\n".join(lines)

    def interim(self, s: "Session", st: "DeviceState", now: float) -> str:
        avg = s.avg_kw(now)
        vmin = min((p.v_min for p in s.phases.values() if p.v_min is not None), default=None)
        vmax = max((p.v_max for p in s.phases.values() if p.v_max is not None), default=None)
        imin = min((p.i_min for p in s.phases.values() if p.i_min is not None), default=None)
        imax = max((p.i_max for p in s.phases.values() if p.i_max is not None), default=None)
        return "\n".join([
            self.L("interim_head", time=self.hm(now), dur=self.dur(s.charge_s(now))),
            self.L("interim_energy", kwh=self.F.kwh(s.energy_calc, 1), avg=self.F.kw(avg, 1), peak=self.F.kw(s.peak_kw, 1)),
            self.L("interim_cost", cost=self.F.money(self.cost(s.energy_by_band, s.energy_calc)), pct=self.F.pct(battery_pct(s.energy_calc, self.s)), km=self.F.num(range_km(s.energy_calc, self.s), 0)),
            self.L("interim_ranges", vmin=self.F.num(vmin, 0), vmax=self.F.num(vmax, 0), imin=self.F.num(imin, 1), imax=self.F.num(imax, 1)),
            self.L("warnings_n", n=len(s.warnings)) if s.warnings else self.L("warnings_none"),
        ])

    # ---- session summary ----
    def _phase_stat_line(self, name: str, p) -> str:
        if p.v_n == 0:
            return self.L("summary_phase_none", name=name)
        v = f"{self.F.num(p.v_min, 0)}–{self.F.num(p.v_max, 0)} V" if round(p.v_min) != round(p.v_max) else f"{self.F.num(p.v_min, 0)} V"
        i = f"{self.F.num(p.i_min, 1)}–{self.F.num(p.i_max, 1)} A" if abs(p.i_max - p.i_min) >= 0.05 else f"{self.F.num(p.i_min, 1)} A"
        return self.L("summary_phase", name=name, v=v, i=i, iavg=self.F.num(p.i_avg, 1))

    def session_summary(self, s: "Session", end_reason: str, unplug_ts: float) -> str:
        plugged_s = unplug_ts - s.plug_ts
        charge_s = s.charge_s(unplug_ts)
        best = s.energy_best()
        if s.seg_count == 0:
            extra = ""
            if s.counters.get("outages"):
                extra += self.L("short_outages", n=s.counters["outages"])
            if s.warnings:
                extra += self.L("short_warnings", n=len(s.warnings))
            text = self.L("unplugged_short", time=self.hm(unplug_ts), dur=self.dur(plugged_s), extra=extra)
            if s.notes:
                text += "\n" + self.L("summary_note", text=esc("; ".join(self.note_text(n) for n in s.notes[:3])))
            return text
        lines = [self.L("unplugged", time=self.hm(unplug_ts)), "", self.L("summary_head", date=self.F.date_short(s.plug_ts))]
        if s.charge_start_ts:
            lines.append(self.L("summary_times", plug=self.hm(s.plug_ts), start=self.hm(s.charge_start_ts), end=self.hm(s.charge_end_ts), unplug=self.hm(unplug_ts)))
            wait = s.charge_start_ts - s.plug_ts
            lines.append(self.L("summary_durations", plugged=self.dur(plugged_s), charging=self.dur(charge_s)) + (self.L("summary_wait", dur=self.dur(wait)) if wait > 300 else ""))
        else:
            lines.append(self.L("summary_times_nocharge", plug=self.hm(s.plug_ts), unplug=self.hm(unplug_ts), dur=self.dur(plugged_s)))
        lines.append("")
        if s.energy_device is not None:
            lines.append(self.L("summary_energy_device", kwh=self.F.kwh(s.energy_device)))
            if s.energy_calc > 0:
                diff = abs(s.energy_device - s.energy_calc) / s.energy_device * 100.0 if s.energy_device > 0 else 0.0
                lines.append(self.L("summary_energy_calc", kwh=self.F.kwh(s.energy_calc)) + (self.L("summary_energy_diff", pct=self.F.pct(diff)) if diff >= 0.5 else ""))
            if s.energy_device2 is not None and abs(s.energy_device2 - s.energy_device) > 0.005:
                lines.append(self.L("summary_energy_device2", kwh=self.F.kwh(s.energy_device2)))
        else:
            lines.append(self.L("summary_energy_calc_only", kwh=self.F.kwh(s.energy_calc)))
        if s.charge_start_ts:
            lines.append(self.L("summary_power", avg=self.F.kw(s.avg_kw(unplug_ts)), peak=self.F.kw(s.peak_kw)))
            for k in ("a", "b", "c"):
                lines.append(self._phase_stat_line(k.upper(), s.phases[k]))
            lines.append(self.L("summary_cost", cost=self.cost_line(self._scaled_bands(s, best))))
            lines.append(self._estimate_line(best))
        lines.append(self.L("summary_reason", reason=esc(self.end_reason(end_reason))))
        c = s.counters
        parts = []
        if c.get("manual_stops"):
            parts.append(self.L("summary_manual_stops", n=c["manual_stops"]))
        if c.get("resumes"):
            parts.append(self.L("summary_resumes", n=c["resumes"]))
        if c.get("outages"):
            parts.append(self.L("summary_outages", n=c["outages"]))
        warn = self.L("summary_warn_n", n=len(s.warnings)) if s.warnings else self.L("summary_warn_none")
        lines.append(self.L("summary_counters", parts=(", ".join(parts) + " · ") if parts else "", warn=warn))
        if s.warnings:
            lines.extend(f"  · {esc(self.warning_text(w))}" for w in s.warnings[:8])
        if s.notes:
            lines.append(self.L("summary_note", text=esc("; ".join(self.note_text(n) for n in s.notes[:4]))))
        return "\n".join(lines)

    def _scaled_bands(self, s: "Session", best: float) -> dict[str, float]:
        total = sum(s.energy_by_band.values())
        if total <= 0:
            return {"day": best, "peak": 0.0, "night": 0.0}
        k = best / total if best > 0 else 1.0
        return {b: v * k for b, v in s.energy_by_band.items()}

    # ---- periodic summaries ----
    def period_summary(self, title: str, stats: dict, prev: dict | None, prev_label: str, lifetime_kwh: float, open_note: bool = False) -> str:
        n = stats["n"]
        if n == 0:
            return f"{title}\n{self.L('period_none')}" + (f"\n{self.L('lifetime', kwh=self.F.kwh(lifetime_kwh, 1))}" if lifetime_kwh else "")
        lines = [
            title,
            self.L("period_line1", n=n, kwh=self.F.kwh(stats["kwh"], 1), cost=self.F.money(stats["cost"]))
            + (self.L("period_charge_time", dur=self.dur(stats["charge_s"])) if stats["charge_s"] else ""),
            self.L("period_line2", kwh=self.F.kwh(stats["kwh"] / n, 1)) + (self.L("period_peak", kw=self.F.kw(stats["peak"], 1)) if stats["peak"] else ""),
        ]
        if prev is not None:
            if prev["n"] == 0:
                lines.append(self.L("period_prev_none", label=prev_label, kwh=self.F.kwh(stats["kwh"], 1)))
            else:
                dk = (stats["kwh"] - prev["kwh"]) / prev["kwh"] * 100.0 if prev["kwh"] else 0.0
                dt = (stats["cost"] - prev["cost"]) / prev["cost"] * 100.0 if prev["cost"] else 0.0
                lines.append(self.L("period_prev", label=prev_label, dk=self.F.pct(dk, 0, signed=True), dt=self.F.pct(dt, 0, signed=True)))
        if open_note:
            lines.append(self.L("period_open_note"))
        lines.append(self.L("lifetime", kwh=self.F.kwh(lifetime_kwh, 1)))
        return "\n".join(lines)

    def no_charge_day(self, d: datetime, online: bool) -> str:
        return self.L("no_charge_day", date=self.F.day_month(d), online=self.L("online" if online else "offline"))

    # ---- commands ----
    def status_cmd(self, info: dict, last_session, now: float, outbox_pending: int) -> str:
        lines = [self.L("status_head", time=self.hm(now))]
        if not info["online"]:
            since = info.get("offline_since")
            lines.append(self.L("status_offline", since=self.L("status_offline_since", dur=self.dur(now - since), time=self.hm(since)) if since else ""))
        else:
            lines.append(self.L("status_online", desc=esc(self.state_desc(True, info["power_kw"], info["work_state"], info["switch"], info["work_mode"]))))
        fault = info.get("fault") or 0
        lines.append(self.L(
            "status_settings",
            amps=info.get("cur_set") if info.get("cur_set") is not None else "—",
            mode=esc(self.mode(info.get("work_mode"))),
            fault=self.L("status_no_fault") if not fault else self.L("status_fault", texts=esc(", ".join(self.fault_texts(fault)))),
        ))
        ph = info["phases"]
        if any(p[1] > 0.2 for p in ph.values()):
            phases = " · ".join(self.L("status_phase_short", name=k.upper(), v=self.F.num(p[0], 0), a=self.F.num(p[1], 1)) for k, p in ph.items())
            lines.append(self.L("status_power", kw=self.F.kw(info["power_kw"]), phases=phases))
        else:
            lines.append(self.L("status_no_voltage"))
        sess = info.get("session")
        if sess:
            lines.append(self.L("status_open_session", plug=self.hm(sess.plug_ts), kwh=self.F.kwh(sess.energy_calc), dur=self.dur(sess.charge_s(now))))
        if last_session is not None:
            lines.append(self.L("status_last_session", line=self.session_line(last_session, with_date=True)))
        rx = now - info["last_rx"] if info["last_rx"] else None
        lines.append(self.L(
            "status_footer",
            ago=self.L("ago", dur=self.dur(rx)) if rx is not None else "—",
            dur=self.dur(info["uptime_s"]),
            queue=self.L("status_queue", n=outbox_pending) if outbox_pending else "",
        ))
        return "\n".join(lines)

    def session_cmd(self, sess: "Session | None", st: "DeviceState", last_session, now: float) -> str:
        if sess:
            lines = [self.L("session_open_head")]
            if sess.charge_start_ts:
                lines.append(self.L("session_open_times", plug=self.hm(sess.plug_ts), start=self.hm(sess.charge_start_ts), dur=self.dur(sess.charge_s(now))))
                lines.append(self.L("session_open_values", kwh=self.F.kwh(sess.energy_calc, 1), kw=self.F.kw(st.power_kw, 1), avg=self.F.kw(sess.avg_kw(now), 1), cost=self.F.money(self.cost(sess.energy_by_band, sess.energy_calc))))
                lines.append(self._estimate_line(sess.energy_calc))
            else:
                lines.append(self.L("session_open_nocharge", plug=self.hm(sess.plug_ts), dur=self.dur(now - sess.plug_ts)))
            return "\n".join(lines)
        if last_session is not None:
            return self.L("session_none_last", line=self.session_line(last_session, with_date=True))
        return self.L("session_none")

    def session_line(self, row, with_date: bool = False) -> str:
        """One-line session: 11.10 18:13–18:24 · 0.56 kWh · 2.20 TL · 7 min charging · car ended charging"""
        start = row["charge_start_ts"] or row["plug_ts"]
        end = row["charge_end_ts"] or row["unplug_ts"]
        energy = row["energy_kwh"] if row["energy_kwh"] is not None else row["energy_calc_kwh"]
        d = self.F.date_dm(row["plug_ts"]) + " " if with_date else ""
        parts = [f"{d}{self.hm(start)}–{self.hm(end) if end else '…'}", self.F.kwh(energy or 0.0, 2), self.F.money(row["cost"] or 0.0)]
        if row["source"] == "smartlife":
            parts.append(self.L("line_plugged", dur=self.dur(row["plugged_s"])))
            parts.append(self.L("er_smartlife"))
        else:
            parts.append(self.L("line_charging", dur=self.dur(row["charge_s"])) if row["charge_s"] else self.L("line_no_charge"))
            parts.append(esc(self.end_reason(row["end_reason"], closed=bool(row["closed"]))))
        return " · ".join(parts)

    def history_cmd(self, rows) -> str:
        if not rows:
            return self.L("history_none")
        return self.L("history_head") + "\n" + "\n".join(self.session_line(r, with_date=True) for r in rows)

    def tariff_cmd(self) -> str:
        t = self.s.tariff
        if t.type == "tou":
            text = self.L("tariff_tou", day=self.F.price(t.day), peak=self.F.price(t.peak), night=self.F.price(t.night))
        else:
            text = self.L("tariff_single", price=self.F.price(t.single))
        return "\n".join([
            self.L("tariff_head", text=text),
            self.L("tariff_car", kwh=self.F.kwh(self.s.battery_kwh, 1), eff=self.F.pct(self.s.charge_efficiency * 100), cons=self.F.num(self.s.consumption_kwh_100km, 1)),
            self.L("tariff_howto"),
            self.L("tariff_usage"),
        ])

    def settings_cmd(self) -> str:
        s = self.s
        return "\n".join([
            self.L("settings_head"),
            self.L("settings_line1", live=s.live_status_min, interim=s.interim_report_min, q1=s.quiet_start, q2=s.quiet_end),
            self.L("settings_line2", nochg=self.L("yes" if s.no_charge_day_message else "no"), vmin=self.F.num(s.voltage_min, 0), vmax=self.F.num(s.voltage_max, 0), imb=self.F.pct(s.imbalance_pct), lang=self.L("lang_name")),
            self.L("settings_howto"),
        ])

    def raw_cmd(self, raw: dict, raw_ts: dict, now: float) -> str:
        if not raw:
            return self.L("raw_none")
        lines = [self.L("raw_head", time=self.F.hms(now))]
        for key in sorted(raw, key=lambda k: int(k) if k.isdigit() else 999):
            age = now - raw_ts.get(key, now)
            lines.append(f"<code>{key:>2} {esc(DP.describe_dp(key, raw[key], self.L))}</code>  <i>({self.L('ago', dur=self.dur(age))})</i>")
        return "\n".join(lines)

    def help_cmd(self) -> str:
        return self.L("help")
