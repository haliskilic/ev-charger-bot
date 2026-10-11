"""Local (cloud-free) connection to the charger: a persistent tinytuya session in its own thread.

Read-only: the only things ever sent to the charger are status queries, DP queries (updatedps) and heartbeats.
Pushed updates are received continuously; a full status is requested every 20 s while charging and every
60 s when idle. On connection loss it reconnects with exponential back-off, rescans the LAN by Device ID if the
IP changed, and raises a clear "authentication" event when the Local Key is no longer valid.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import tinytuya

from .config import Secrets, Settings

log = logging.getLogger("evsarj.tuya")

QUERY_DPS = [6, 7, 8, 9, 25]
HEARTBEAT_S = 10
AUTH_RETRY_S = 15 * 60
SCAN_MIN_INTERVAL_S = 120


class AuthError(Exception):
    pass


class ConnError(Exception):
    pass


class TuyaClient(threading.Thread):
    def __init__(self, secrets: Secrets, settings: Settings, post: Callable[[dict[str, Any]], None], ip_override: str | None = None):
        super().__init__(name="tuya", daemon=True)
        self.secrets = secrets
        self.settings = settings
        self.post = post
        self.ip = ip_override or secrets.tuya_ip
        self._stop = threading.Event()
        self._fast = False
        self.online = False
        self.last_rx: float = 0.0
        self.offline_since: float | None = None
        self._dev: tinytuya.Device | None = None
        self._last_scan = 0.0
        self._auth_notified = 0.0

    # ---- public ----
    def stop(self) -> None:
        self._stop.set()

    def set_fast(self, fast: bool) -> None:
        self._fast = fast

    # ---- internals ----
    def _poll_interval(self) -> int:
        return self.settings.poll_charging_s if self._fast else self.settings.poll_idle_s

    def _connect(self) -> tinytuya.Device:
        dev = tinytuya.Device(self.secrets.tuya_device_id, self.ip, self.secrets.tuya_local_key, version=self.secrets.tuya_version, persist=True)
        dev.set_socketTimeout(3)
        dev.set_socketRetryLimit(1)
        dev.set_socketRetryDelay(1)
        return dev

    @staticmethod
    def _classify(result: dict | None) -> None:
        """Turn a tinytuya error dict into an exception (returns quietly when there is no error)."""
        if not result or "Error" not in result:
            return
        code = str(result.get("Err", ""))
        if code == "914":
            raise AuthError(result.get("Error"))
        if code == "904":  # timeout / nothing to read: normal
            return
        raise ConnError(f"{result.get('Error')} ({code})")

    def _scan_for_device(self) -> None:
        """If the charger cannot be reached, look for it by Device ID (UDP broadcasts) in case its IP changed."""
        now = time.time()
        if now - self._last_scan < SCAN_MIN_INTERVAL_S:
            return
        self._last_scan = now
        log.info("scanning the LAN for the charger (by Device ID)")
        try:
            found = tinytuya.find_device(dev_id=self.secrets.tuya_device_id)
        except Exception as e:
            log.warning("scan failed: %s", e)
            return
        ip = (found or {}).get("ip")
        if ip and ip != self.ip:
            log.warning("charger found at a new IP: %s -> %s", self.ip, ip)
            old, self.ip = self.ip, ip
            self.post({"kind": "conn", "ts": now, "state": "ip_changed", "info": {"old": old, "new": ip, "version": found.get("version")}})
        elif ip:
            log.info("charger seen at the same IP: %s", ip)
        else:
            log.info("charger not found by the scan")

    def _set_online(self, ts: float) -> None:
        if not self.online:
            outage = (ts - self.offline_since) if self.offline_since else 0.0
            self.online = True
            self.post({"kind": "conn", "ts": ts, "state": "online", "info": {"outage_s": outage, "ip": self.ip}})
            self.offline_since = None

    def _set_offline(self, ts: float, reason: str) -> None:
        if self.online:
            self.online = False
            self.offline_since = self.last_rx or ts
            self.post({"kind": "conn", "ts": ts, "state": "offline", "info": {"reason": reason, "since": self.offline_since}})

    def _handle_dps(self, result: dict | None, snapshot: bool = False) -> bool:
        if not result:
            return False
        self._classify(result)
        dps = result.get("dps")
        if not dps:
            return False
        ts = time.time()
        self.last_rx = ts
        self.post({"kind": "dps", "ts": ts, "dps": dict(dps), "snapshot": snapshot})
        return True

    def run(self) -> None:
        backoff = 1
        failures = 0
        while not self._stop.is_set():
            try:
                self._session()
                backoff = 1
                failures = 0
            except AuthError as e:
                now = time.time()
                self._set_offline(now, "auth")
                if now - self._auth_notified > AUTH_RETRY_S:
                    self._auth_notified = now
                    self.post({"kind": "conn", "ts": now, "state": "auth_error", "info": {"error": str(e)}})
                log.error("authentication failed (Local Key?): %s; retrying in %d s", e, AUTH_RETRY_S)
                self._stop.wait(AUTH_RETRY_S)
            except Exception as e:
                now = time.time()
                failures += 1
                log.warning("connection error: %s (attempt %d, waiting %d s)", e, failures, backoff)
                self._set_offline(now, str(e))
                if failures >= 3:
                    self._scan_for_device()
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                if self._dev is not None:
                    try:
                        self._dev.close()
                    except Exception:
                        pass
                    self._dev = None

    def _session(self) -> None:
        dev = self._connect()
        self._dev = dev
        first = dev.status()
        self._classify(first)
        if not first or "dps" not in first:
            raise ConnError("no status received")
        now = time.time()
        self.last_rx = now
        self._set_online(now)
        self._handle_dps(first, snapshot=True)
        dev.updatedps(QUERY_DPS)
        last_poll = now
        last_hb = now
        while not self._stop.is_set():
            now = time.time()
            if now - last_poll >= self._poll_interval():
                last_poll = now
                r = dev.status()
                self._classify(r)
                if r and "dps" in r:
                    self.last_rx = time.time()
                    self._handle_dps(r)
                dev.updatedps(QUERY_DPS)
            elif now - last_hb >= HEARTBEAT_S:
                last_hb = now
                dev.heartbeat(nowait=True)
            r = dev.receive()
            if r:
                if "Error" in r:
                    self._classify(r)
                else:
                    if r.get("dps"):
                        self._handle_dps(r)
                    self.last_rx = time.time()
            if time.time() - self.last_rx > self.settings.offline_after_s:
                raise ConnError(f"no data for {self.settings.offline_after_s} s")
