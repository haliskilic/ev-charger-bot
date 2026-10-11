"""Data points (DPs) of the charger: the map verified by measurement (see docs/DP-MAP.md) and decoders.

Observed on a Hici 22 kW charger (Tuya category qccdz, protocol 3.4):
  3  work_state         enum   charger_free / charger_wait / charger_charging (+ defined but never seen: insert, pause, end, fault, free_fault)
  4  charge_cur_set     A      6..48 (briefly 6 right after a reboot)
  6/7/8 phase_a/b/c     raw    7 bytes: voltage(2B, x0.1 V) + current(3B, x0.001 A) + power(2B, x0.001 kW)
  9  power_total        kW     x0.001 (equals the sum of the three phases)
  10 fault              bitmap 16 bits
  14 work_mode          enum   charge_now / charge_pct / charge_energy / charge_schedule / charge_delay
  18 switch             bool   the "start/stop charging" toggle of the app; flips off for 6 s on unplug, then back on
  19 local_timer        raw    2 bytes, 0000 when empty (format with a timer set not yet observed)
  23 system_version     str    "V1"
  25 charge_energy_once kWh    x0.01; sent only on unplug or when the charger closes its record (12-hour limit)
"""

from __future__ import annotations

import base64

DP_WORK_STATE = "3"
DP_CUR_SET = "4"
DP_PHASE = {"6": "a", "7": "b", "8": "c"}
DP_POWER = "9"
DP_FAULT = "10"
DP_WORK_MODE = "14"
DP_SWITCH = "18"
DP_TIMER = "19"
DP_VERSION = "23"
DP_SESSION_ENERGY = "25"

DP_NAMES = {
    "3": "work_state",
    "4": "charge_cur_set",
    "6": "phase_a",
    "7": "phase_b",
    "8": "phase_c",
    "9": "power_total",
    "10": "fault",
    "14": "work_mode",
    "18": "switch",
    "19": "local_timer",
    "23": "system_version",
    "25": "charge_energy_once",
}

WORK_STATES = ("charger_free", "charger_insert", "charger_wait", "charger_charging", "charger_pause", "charger_end", "charger_fault", "charger_free_fault")
WORK_MODES = ("charge_now", "charge_pct", "charge_energy", "charge_schedule", "charge_delay")
FAULT_BIT_COUNT = 16

PLUGGED_STATES = {"charger_insert", "charger_wait", "charger_charging", "charger_pause", "charger_end", "charger_fault"}
FAULT_STATES = {"charger_fault", "charger_free_fault"}


def decode_phase(value: str) -> tuple[float, float, float] | None:
    """Decode a base64 phase record into (voltage V, current A, power kW)."""
    try:
        raw = base64.b64decode(value)
    except Exception:
        return None
    if len(raw) < 7:
        return None
    volt = int.from_bytes(raw[0:2], "big") / 10.0
    amp = int.from_bytes(raw[2:5], "big") / 1000.0
    kw = int.from_bytes(raw[5:7], "big") / 1000.0
    return volt, amp, kw


def raw_hex(value: str) -> str:
    try:
        return base64.b64decode(value).hex()
    except Exception:
        return "?"


def fault_bits(bitmap: int) -> list[int]:
    return [bit for bit in range(FAULT_BIT_COUNT) if bitmap & (1 << bit)]


def describe_dp(dp: str, value, L) -> str:
    """One-line decoded description for the /raw command (L = translator)."""
    name = DP_NAMES.get(dp, "?")
    if dp in DP_PHASE and isinstance(value, str):
        dec = decode_phase(value)
        if dec:
            return f"{name:<18} {raw_hex(value)} → {dec[0]:.0f} V · {dec[1]:.1f} A · {dec[2]:.3f} kW"
        return f"{name:<18} {raw_hex(value)}"
    if dp == DP_POWER:
        return f"{name:<18} {value} → {int(value) / 1000:.3f} kW"
    if dp == DP_SESSION_ENERGY:
        return f"{name:<18} {value} → {int(value) / 100:.2f} kWh"
    if dp == DP_FAULT:
        bits = fault_bits(int(value)) if value else []
        texts = ", ".join(L(f"fault_{b}") for b in bits)
        return f"{name:<18} {value} → {texts if texts else L('none')}"
    if dp == DP_TIMER and isinstance(value, str):
        return f"{name:<18} {raw_hex(value)}"
    if dp == DP_WORK_STATE:
        return f"{name:<18} {value} ({L('ws_' + str(value))})"
    if dp == DP_WORK_MODE:
        return f"{name:<18} {value} ({L('wm_' + str(value))})"
    if dp == DP_CUR_SET:
        return f"{name:<18} {value} A"
    return f"{name:<18} {value}"
