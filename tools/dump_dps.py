"""Query the charger once and print the decoded DP dump (no Telegram needed).

Usage:  python -m tools.dump_dps   (works while the service is running; the charger accepts a second connection)
"""

from __future__ import annotations

import time

import tinytuya

from evsarj import config
from evsarj import dp as DP
from evsarj.i18n import Lang


def main() -> None:
    settings, secrets = config.load()
    dev = tinytuya.Device(secrets.tuya_device_id, secrets.tuya_ip, secrets.tuya_local_key, version=secrets.tuya_version, persist=True)
    dev.set_socketTimeout(3)
    status = dev.status()
    if not status or "dps" not in status:
        raise SystemExit(f"no status: {status}")
    dps = dict(status["dps"])
    dev.updatedps([6, 7, 8, 9, 25])
    end = time.time() + 4
    while time.time() < end:
        r = dev.receive()
        if r and r.get("dps"):
            dps.update(r["dps"])
    dev.close()
    L = Lang(settings.language)
    for key in sorted(dps, key=lambda k: int(k)):
        print(f"{key:>2} {DP.describe_dp(key, dps[key], L)}")


if __name__ == "__main__":
    main()
