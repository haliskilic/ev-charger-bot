"""Find the charger on the LAN by Device ID (UDP 6666/6667/7000 broadcasts). No Local Key needed.

Usage:  python -m tools.find_device
"""

from __future__ import annotations

import tinytuya

from evsarj import config


def main() -> None:
    _, secrets = config.load()
    print("scanning (about 20 s)…")
    found = tinytuya.find_device(dev_id=secrets.tuya_device_id)
    if found and found.get("ip"):
        print(f"found: ip={found['ip']} version={found.get('version')}")
        if found["ip"] != secrets.tuya_ip:
            print(f"TUYA_DEVICE_IP in .env ({secrets.tuya_ip}) differs; update it, or let the bot find the device automatically.")
    else:
        print("not found: the charger is off, not on Wi-Fi, or on a different network/VLAN.")


if __name__ == "__main__":
    main()
