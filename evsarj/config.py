"""Configuration: `.env` (secrets) + `config.toml` (settings) + runtime overrides stored in the database.

`EVSARJ_HOME` selects the installation directory; by default it is the project folder
(the parent of this package), which works unchanged on Windows, Raspberry Pi, Ubuntu and Proxmox.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(os.environ.get("EVSARJ_HOME") or Path(__file__).resolve().parent.parent)


def load_env(path: Path) -> None:
    """Load KEY=VALUE lines into the environment (existing variables win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@dataclass
class Secrets:
    tuya_device_id: str
    tuya_local_key: str
    tuya_ip: str
    tuya_version: float
    tuya_region: str | None
    tuya_access_id: str | None
    tuya_access_secret: str | None
    tg_token: str
    tg_chat_id: int
    tg_thread_id: int | None
    tg_owner_id: int

    @classmethod
    def from_env(cls) -> "Secrets":
        def need(key: str) -> str:
            value = os.environ.get(key)
            if not value:
                raise SystemExit(f"{key} is missing from .env")
            return value

        thread = os.environ.get("TELEGRAM_THREAD_ID", "").strip()
        return cls(
            tuya_device_id=need("TUYA_DEVICE_ID"),
            tuya_local_key=need("TUYA_LOCAL_KEY"),
            tuya_ip=os.environ.get("TUYA_DEVICE_IP", "Auto"),
            tuya_version=float(os.environ.get("TUYA_VERSION", "3.4")),
            tuya_region=os.environ.get("TUYA_REGION") or None,
            tuya_access_id=os.environ.get("TUYA_ACCESS_ID") or None,
            tuya_access_secret=os.environ.get("TUYA_ACCESS_SECRET") or None,
            tg_token=need("TELEGRAM_BOT_TOKEN"),
            tg_chat_id=int(need("TELEGRAM_CHAT_ID")),
            tg_thread_id=int(thread) if thread and thread != "0" else None,
            tg_owner_id=int(need("TELEGRAM_OWNER_ID")),
        )


@dataclass
class Tariff:
    type: str = "single"  # "single" | "tou" (time-of-use: day 06–17, peak 17–22, night 22–06)
    currency: str = "€"
    single: float = 0.30
    day: float = 0.30
    peak: float = 0.30
    night: float = 0.30

    def price_for_band(self, band: str) -> float:
        if self.type != "tou":
            return self.single
        return {"day": self.day, "peak": self.peak, "night": self.night}[band]


@dataclass
class Settings:
    language: str = "en"
    db_path: str = "data/evsarj.db"
    timezone: str = "Europe/Istanbul"
    # intervals
    live_status_min: int = 5
    interim_report_min: int = 30
    poll_charging_s: int = 20
    poll_idle_s: int = 60
    offline_after_s: int = 90
    # quiet hours (notifications are sent silently)
    quiet_start: str = "23:00"
    quiet_end: str = "07:00"
    # car
    battery_kwh: float = 19.7
    charge_efficiency: float = 0.90
    consumption_kwh_100km: float = 17.0
    max_ac_kw: float = 11.0
    # thresholds
    voltage_min: float = 207.0
    voltage_max: float = 253.0
    imbalance_pct: float = 30.0
    phase_loss_min_a: float = 1.0
    power_drop_pct: float = 50.0
    no_current_s: int = 90
    debounce_s: int = 5
    # reports
    daily_time: str = "23:55"
    weekly_time: str = "09:00"
    monthly_time: str = "09:00"
    no_charge_day_message: bool = True
    # retention
    samples_days: int = 90
    transitions_months: int = 12
    events_months: int = 24
    tariff: Tariff = field(default_factory=Tariff)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @classmethod
    def from_toml(cls, path: Path) -> "Settings":
        s = cls()
        if not path.exists():
            return s
        with path.open("rb") as f:
            data = tomllib.load(f)

        def section(name: str) -> dict:
            return data.get(name, {}) or {}

        bot = section("bot")
        s.language = str(bot.get("language", s.language)).lower()
        s.db_path = bot.get("db_path", s.db_path)
        s.timezone = bot.get("timezone", s.timezone)
        i = section("intervals")
        s.live_status_min = int(i.get("live_status_min", s.live_status_min))
        s.interim_report_min = int(i.get("interim_report_min", s.interim_report_min))
        s.poll_charging_s = int(i.get("poll_charging_s", s.poll_charging_s))
        s.poll_idle_s = int(i.get("poll_idle_s", s.poll_idle_s))
        s.offline_after_s = int(i.get("offline_after_s", s.offline_after_s))
        q = section("quiet_hours")
        s.quiet_start = q.get("start", s.quiet_start)
        s.quiet_end = q.get("end", s.quiet_end)
        car = section("car")
        s.battery_kwh = float(car.get("battery_kwh", s.battery_kwh))
        s.charge_efficiency = float(car.get("charge_efficiency", s.charge_efficiency))
        s.consumption_kwh_100km = float(car.get("consumption_kwh_100km", s.consumption_kwh_100km))
        s.max_ac_kw = float(car.get("max_ac_kw", s.max_ac_kw))
        t = section("thresholds")
        s.voltage_min = float(t.get("voltage_min", s.voltage_min))
        s.voltage_max = float(t.get("voltage_max", s.voltage_max))
        s.imbalance_pct = float(t.get("imbalance_pct", s.imbalance_pct))
        s.phase_loss_min_a = float(t.get("phase_loss_min_a", s.phase_loss_min_a))
        s.power_drop_pct = float(t.get("power_drop_pct", s.power_drop_pct))
        s.no_current_s = int(t.get("no_current_s", s.no_current_s))
        s.debounce_s = int(t.get("debounce_s", s.debounce_s))
        r = section("reports")
        s.daily_time = r.get("daily_time", s.daily_time)
        s.weekly_time = r.get("weekly_time", s.weekly_time)
        s.monthly_time = r.get("monthly_time", s.monthly_time)
        s.no_charge_day_message = bool(r.get("no_charge_day_message", s.no_charge_day_message))
        k = section("retention")
        s.samples_days = int(k.get("samples_days", s.samples_days))
        s.transitions_months = int(k.get("transitions_months", s.transitions_months))
        s.events_months = int(k.get("events_months", s.events_months))
        tf = section("tariff")
        single = float(tf.get("single_price", 0.30))
        s.tariff = Tariff(
            type=str(tf.get("type", "single")),
            currency=str(tf.get("currency", "€")),
            single=single,
            day=float(tf.get("day", single)),
            peak=float(tf.get("peak", single)),
            night=float(tf.get("night", single)),
        )
        return s

    def apply_overrides(self, overrides: dict[str, str]) -> None:
        """Values changed from Telegram (/settings, /tariff, /language) are stored in the DB and win over config.toml."""
        for key, value in overrides.items():
            try:
                if key == "language":
                    self.language = value
                elif key == "live_status_min":
                    self.live_status_min = max(1, int(value))
                elif key == "interim_report_min":
                    self.interim_report_min = max(5, int(value))
                elif key == "quiet_hours":
                    start, _, end = value.partition("-")
                    self.quiet_start, self.quiet_end = start, end
                elif key == "no_charge_day_message":
                    self.no_charge_day_message = value == "1"
                elif key == "tariff_type":
                    self.tariff.type = value
                elif key == "tariff_single":
                    self.tariff.single = float(value)
                elif key == "tariff_day":
                    self.tariff.day = float(value)
                elif key == "tariff_peak":
                    self.tariff.peak = float(value)
                elif key == "tariff_night":
                    self.tariff.night = float(value)
            except ValueError:
                continue


def load(base: Path = BASE_DIR) -> tuple[Settings, Secrets]:
    load_env(base / ".env")
    settings = Settings.from_toml(base / "config.toml")
    secrets = Secrets.from_env()
    return settings, secrets
