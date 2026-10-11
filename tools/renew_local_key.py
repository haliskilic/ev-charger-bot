"""Fetch the Local Key from the Tuya cloud again and write it into .env (needed after the device was removed and re-added in Smart Life).

Requires TUYA_ACCESS_ID / TUYA_ACCESS_SECRET / TUYA_REGION in .env and an active IoT Core subscription (trial) on iot.tuya.com.
Usage:  python -m tools.renew_local_key
"""

from __future__ import annotations

import os
import re
import sys

import tinytuya

from evsarj import config


def main() -> None:
    _, secrets = config.load()
    if not (secrets.tuya_access_id and secrets.tuya_access_secret and secrets.tuya_region):
        sys.exit("TUYA_ACCESS_ID / TUYA_ACCESS_SECRET / TUYA_REGION are required in .env")
    cloud = tinytuya.Cloud(apiRegion=secrets.tuya_region, apiKey=secrets.tuya_access_id, apiSecret=secrets.tuya_access_secret)
    if cloud.error:
        sys.exit(f"cloud login failed: {cloud.error}")
    r = cloud.cloudrequest(f"/v1.0/devices/{secrets.tuya_device_id}")
    if not r.get("success"):
        sys.exit(f"device query failed: {r.get('code')} {r.get('msg')} (the IoT Core subscription may have expired)")
    key = r["result"].get("local_key")
    if not key:
        sys.exit("no local_key in the response")
    env_path = config.BASE_DIR / ".env"
    text = env_path.read_text(encoding="utf-8")
    if "TUYA_LOCAL_KEY=" in text:
        text = re.sub(r"^TUYA_LOCAL_KEY=.*$", f"TUYA_LOCAL_KEY={key}", text, flags=re.M)
    else:
        text += f"\nTUYA_LOCAL_KEY={key}\n"
    env_path.write_text(text, encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
    changed = key != secrets.tuya_local_key
    print("Local Key " + ("updated" if changed else "was already the same") + f"; device online: {r['result'].get('online')}")
    print("Restart the bot (systemctl restart ev-charger-bot, or restart the scheduled task on Windows).")


if __name__ == "__main__":
    main()
