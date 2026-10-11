# Third-party notices

ev-charger-bot uses the following open-source components. They are **not** covered by the project's own license; each remains under its own terms.

| Component | License | Use |
|---|---|---|
| [tinytuya](https://github.com/jasonacox/tinytuya) | MIT | Local (LAN) communication with the Tuya-based charger; optional cloud access during setup |
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | LGPL-3.0 | Telegram Bot API client (used as an unmodified library) |
| [tzdata](https://pypi.org/project/tzdata/) (Windows only) | Apache-2.0 | IANA time-zone database for Python's `zoneinfo` |
| Python standard library | PSF License | sqlite3, asyncio, tomllib, zoneinfo, … |

The charger protocol knowledge (data points, their scaling and the behaviour of the Hici / Tuya `qccdz` charger) was obtained by measuring a device the author owns; no manufacturer code is included.
