<!-- ev-charger-bot — README (English / default). Türkçe: README.tr.md -->

**🌐 [English](README.md) · [Türkçe](README.tr.md)**

# ev-charger-bot

**A read-only Telegram bot that watches a Tuya / Smart Life based EV charger over your local network 24/7 and reports charging sessions, costs, warnings and daily/weekly/monthly summaries to a Telegram group topic — in English or Turkish.**

> Built and verified on a **Hici 22 kW** three-phase wall box (Tuya category `qccdz`, protocol 3.4) charging a **Seat Leon e-Hybrid** PHEV. Other Tuya `qccdz` chargers use the same data points and should work with little or no change.

- **Local, cloud-free:** talks to the charger directly over LAN (`tinytuya`); the Tuya cloud is used once, during setup, to obtain the Local Key.
- **Read-only by design:** it never starts, stops or changes anything on the charger.
- **Private:** answers only inside *your* Telegram group; ignores everyone else and leaves any other chat it is added to.
- **Small:** one Python process, SQLite, no external services. Runs on Windows, Ubuntu, Raspberry Pi or a Proxmox LXC.

---

## Contents

- [What you get](#what-you-get)
- [Example messages](#example-messages)
- [Requirements](#requirements)
- [Installation](#installation)
- [Commands](#commands)
- [Configuration](#configuration)
- [Security model](#security-model)
- [Data, logs and retention](#data-logs-and-retention)
- [Tools](#tools)
- [How it reads the charger](#how-it-reads-the-charger)
- [What the charger does not provide](#what-the-charger-does-not-provide)
- [Troubleshooting](#troubleshooting)
- [Support the project](#support-the-project)
- [License](#license)

---

## What you get

**Instant events**
- Car plugged in / unplugged
- Charging started / stopped from the app / resumed / finished (car full vs. car stopped abruptly)
- Waiting for a scheduled or delayed charge; "plugged in but not charging" hint
- Fault raised / cleared, with the fault bits explained in words
- Charger offline / back online (with outage duration); charger rebooted (short power cut)
- Settings changed on the charger: current limit, work mode, timer
- Warnings: voltage out of range, phase loss, phase imbalance, unexpected power drop, "charging" with 0 A
- Bot restarted (and the open session is resumed, not duplicated)

**While charging**
- One **live status** message edited in place (default every 5 min): total power, per-phase V/A/kW, active phases, current limit, energy so far, elapsed time, average power, cost so far, estimated battery % and range added, latest finish time.
- An **interim report** (default every 30 min).

**Session summary** when the car is unplugged
- Plug-in, charge start, charge end and unplug times; time plugged in vs. time actually charging
- Energy from the charger's own counter **and** from integrating the power readings (differences shown)
- Average / peak power, per-phase min–max voltage and current
- Cost (single price or time-of-use day/peak/night bands)
- Estimated battery % and electric range added (always labelled *estimate*)
- End reason: car full (tapered) / car stopped / stopped from the app / cable unplugged / fault / outage
- Warnings and outages that happened during the session

**Periodic summaries**
- Daily, weekly and monthly: sessions, kWh, cost, charging time, average per session, peak power, change vs. the previous period, lifetime total.
- On days without charging a single line "charger online, no charging today" (can be switched off).

**History import** — the Smart Life "Record" export (`.xlsx`) can be imported so `/history`, `/month` and the comparisons are populated from day one.

---

## Example messages

<details open>
<summary><b>Events</b></summary>

```
🔄 Bot restarted · 2026-10-11 19:31
Charger online · idle, no car plugged in · no open session
```
```
🔌 Car plugged in · 18:13
Current limit 32 A · Mode: charge now
```
```
⚡ Charging started · 18:13
4.66 kW · 7.7 / 7.6 / 7.6 A · 3 phase(s)
```
```
⏸ Charging stopped (from the app) · 18:17
This session so far ~0.30 kWh · 4 min charging
```
```
▶️ Charging resumed · 18:19
4.63 kW · 7.7 / 7.6 / 7.6 A · 3 phase(s)
```
```
✅ Charging complete · 21:02
Power tapered off: the car is full.
Session: ~19.80 kWh · 1 h 52 min charging · avg 10.60 kW
```
```
⏹ Car ended charging · 18:22
Power cut off abruptly (the battery may be full).
Session: ~0.54 kWh · 7 min charging · avg 4.64 kW
```
```
ℹ️ Charging did not start · 11:26
The car has been plugged in for 3 min without drawing current. The battery may be full, or the car's own timer may be waiting.
```
```
🚨 Fault · 18:40
leakage current alarm (bit 15)
State: charger_fault · charging stopped
```
```
📴 Charger offline · 18:40
No data for 2 min (last data 18:38). Charging was in progress: ~5.20 kWh delivered.
```
```
📶 Charger back online · 18:47 (outage 7 min)
State: car plugged in, waiting
```
```
♻️ Charger rebooted · 18:07
Possibly a brief power cut (connection lost for 10 s). Car plugged in, waiting.
```
```
⚙️ Setting changed · 18:50
Current limit: 32 A → 16 A
```
```
⚠️ Phase imbalance · 19:45
Currents: 16.0 / 15.9 / 9.1 A (difference 43%)
```
</details>

<details open>
<summary><b>Live status (one message, edited in place) and interim report</b></summary>

```
🔋 LIVE STATUS · 19:25 (updated every 5 min)
Charging · 47 min · ~8.4 kWh

Power 10.9 kW · 3 phase(s) active · limit 32 A
A: 229 V · 15.9 A · 3.64 kW
B: 226 V · 15.8 A · 3.57 kW
C: 227 V · 15.9 A · 3.61 kW
Average power: 10.7 kW
Cost: 2.52 €
Estimated added: +38% (≈ +44 km) — estimate
Latest finish: ~20:45 (assuming an empty battery)
```
```
📊 Interim report · 19:35 · charging for 57 min
Delivered ~10.2 kWh · avg 10.7 kW · peak 11.0 kW
Cost 3.06 € · estimated +47% (≈ +54 km) — estimate
Voltage 225–231 V · current 15.8–16.0 A/phase
No warnings
```
</details>

<details open>
<summary><b>Session summary</b></summary>

```
🔌 Car unplugged · 18:24

📋 Session summary · 2026-10-11
Plugged in 18:13 · Charging 18:13–18:22 · Unplugged 18:24
Plugged in for 11 min · actual charging 7 min

Energy: 0.56 kWh (charger counter)
  from power readings: 0.51 kWh (difference 9%)
Power: avg 4.29 kW · peak 4.67 kW
Phase A: 225–229 V · 7.7 A (avg 7.7 A)
Phase B: 212–216 V · 7.6–7.7 A (avg 7.6 A)
Phase C: 219–223 V · 7.5–7.6 A (avg 7.6 A)
Cost: 0.17 € (0.30 €/kWh)
Estimated added: +3% (≈ +3 km) — estimate
End reason: car ended charging
During the session: 1 manual stop(s), 1 resume(s) · no warnings
```
</details>

<details>
<summary><b>Periodic summaries and commands</b></summary>

```
📅 Daily summary · Sunday, 11 October 2026
2 session(s) · 13.4 kWh · 4.02 € · 2 h 10 min charging
Average per session 6.7 kWh · peak power 11.0 kW
vs. yesterday: no charging (+13.4 kWh)
Total according to bot records: 4,036.4 kWh (the charger has no lifetime counter)
```
```
📆 Weekly summary · 5–11 October 2026
5 session(s) · 48.2 kWh · 14.46 € · 6 h 40 min charging
Average per session 9.6 kWh · peak power 11.0 kW
vs. previous week: kWh +12% · cost +12%
Total according to bot records: 4,036.4 kWh (the charger has no lifetime counter)
```
```
📡 Status · 18:33
Charger online · car plugged in, waiting
Current limit 32 A · Mode: charge now · No fault
Voltage: — (phase data is zero while no current flows)
Last session: 11 Oct 18:13–18:22 · 0.56 kWh · 0.17 € · 7 min charging · car ended charging
Last data 6 s ago · bot running for 2 h 11 min
```
```
🕓 Recent sessions
11 Oct 18:13–18:22 · 0.56 kWh · 0.17 € · 7 min charging · car ended charging
01 Oct 18:41–06:41 · 15.07 kWh · 4.52 € · plugged 12 h · Smart Life record
30 Sep 18:30–06:31 · 13.94 kWh · 4.18 € · plugged 12 h · Smart Life record
```
</details>

The same messages in Turkish are shown in [README.tr.md](README.tr.md#örnek-mesajlar).

---

## Requirements

**Hardware**
- A Tuya / Smart Life based EV charger that is set up in the Smart Life (or Tuya Smart) app and connected to your Wi-Fi. Verified: Hici 22 kW (`qccdz`). Single-phase chargers work too (phases B/C simply stay at 0).
- A machine on the **same LAN / VLAN** as the charger, running 24/7: a Raspberry Pi, an Ubuntu box, a Proxmox LXC container or a Windows PC. 1 CPU core, 512 MB RAM and 4 GB disk are plenty.

**Accounts (free)**
- A Tuya developer account (iot.tuya.com) — used once to read the charger's **Local Key**. The free "IoT Core" trial is enough.
- A Telegram bot created with **@BotFather**, and a Telegram group (ideally with Topics enabled) where reports go.

**Software**
- Python **3.11 or newer** (3.12/3.13 recommended). Dependencies: `tinytuya`, `python-telegram-bot` (and `tzdata` on Windows).

---

## Installation

Step-by-step guides for every platform, written for first-time users:

- **[docs/INSTALL.en.md](docs/INSTALL.en.md)** — common steps (Tuya Local Key, BotFather, chat ids) and then **Windows 10/11**, **Ubuntu 22.04/24.04**, **Raspberry Pi OS**, **Proxmox VE (LXC)**.
- Turkish: **[docs/INSTALL.tr.md](docs/INSTALL.tr.md)**.

The short version for Linux:

```bash
sudo apt install -y python3 python3-venv git
sudo useradd --system --home-dir /opt/ev-charger-bot --shell /usr/sbin/nologin evsarj
sudo git clone https://github.com/haliskilic/ev-charger-bot /opt/ev-charger-bot
cd /opt/ev-charger-bot && sudo cp .env.example .env && sudo nano .env      # fill in the secrets
sudo chown -R evsarj:evsarj /opt/ev-charger-bot && sudo chmod 600 .env
sudo -u evsarj python3 -m venv venv && sudo -u evsarj venv/bin/pip install -r requirements.txt
sudo cp ev-charger-bot.service /etc/systemd/system/ && sudo systemctl enable --now ev-charger-bot
journalctl -u ev-charger-bot -f
```

---

## Commands

| English | Turkish alias | What it does |
|---|---|---|
| `/status` | `/durum` | Current charger state, settings, last session, bot health |
| `/session` | `/oturum` | The open charging session (or the last one) |
| `/today` `/week` `/month` | `/bugun` `/hafta` `/ay` | Summaries so far |
| `/history [n]` | `/gecmis` | Last 10 (or n) sessions |
| `/tariff` | `/tarife` | Show prices and car parameters; owner: `/tariff single 0.30`, `/tariff tou 0.25 0.40 0.15` |
| `/settings` | `/ayar` | Show intervals/thresholds; owner: `/settings live 5`, `/settings interim 30`, `/settings quiet 23-07`, `/settings nochargeday off` |
| `/language en\|tr` | `/dil` | Message language (owner) |
| `/raw` | `/ham` | Raw DP dump with decoded values and age |
| `/export` | `/disaaktar` | CSV of all sessions; `/export raw 7` = raw samples of the last 7 days |
| `/help` | `/yardim` | Command list |

Both command sets work regardless of the active language. Replies go to the topic the command was sent in.

---

## Configuration

- **`.env`** — secrets and ids (bot token, chat/topic/owner ids, device id, Local Key, IP, protocol version, optional Tuya cloud keys). Readable only by the service user (`chmod 600`). Template: [`.env.example`](.env.example).
- **`config.toml`** — everything else, with comments: language, intervals, quiet hours, tariff (single or time-of-use with day 06–17 / peak 17–22 / night 22–06 bands), car parameters (battery kWh, charging efficiency, consumption kWh/100 km), warning thresholds (including `phases = 1` for single-phase chargers), report times, retention. See [`config.toml`](config.toml).
- Values changed from Telegram (`/settings`, `/tariff`, `/language`) are stored in the database and override `config.toml`.

Default language is **English**; set `language = "tr"` or send `/language tr` for Turkish.

---

## Security model

- The bot processes **only** updates coming from the group id in `.env` (`TELEGRAM_CHAT_ID`). Private messages, other groups and channels are ignored without any reply.
- If someone adds the bot to another chat, it **leaves immediately** (`my_chat_member` handler).
- Commands that change settings (`/settings`, `/tariff`, `/language`) are accepted only from `TELEGRAM_OWNER_ID`; group members can read everything else.
- The bot is **read-only** towards the charger: there is no code path that sends `switch`, `charge_cur_set`, `work_mode` or any other command.
- Secrets never appear in logs; library debug logging is disabled.
- No inbound ports: Telegram is reached by long polling and the charger by an outgoing LAN connection, so nothing needs to be exposed on your router or firewall.
- On Linux the service runs as an unprivileged user with systemd hardening (`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`); only `data/` is writable.
- Dependencies are pinned in `requirements.txt`.
- Tests in [`tests/test_security.py`](tests/test_security.py) assert the access rules above.

Keep the bot token secret (anyone with the token can read your group's commands). If it leaks, revoke it in @BotFather (`/revoke`) and update `.env`.

---

## Data, logs and retention

Everything is in one SQLite file (`data/evsarj.db`, WAL mode):

| Table | Content | Kept for |
|---|---|---|
| `samples` | every decoded reading (on change, at least once a minute) | `retention.samples_days` (default 90 days) |
| `transitions` | state/setting changes | `retention.transitions_months` (12) |
| `events` | sent event texts | `retention.events_months` (24) |
| `sessions`, `segments` | charging sessions and the charging segments inside them | forever (a few hundred bytes each) |
| `outbox` | message queue (retries, rate limiting, delayed delivery) | sent rows 30 days |

A cleanup runs daily at 03:30 (and `VACUUM` monthly), so the database size stays bounded. Service logs go to **journald**; on the reference installation journald is limited to 100 MB / 12 months (see the install guide). Back up the database by copying `data/evsarj.db` (`sqlite3 data/evsarj.db ".backup backup.db"` for a consistent copy while running).

---

## Tools

Run from the project directory with the venv's Python, e.g. `venv/bin/python -m tools.find_device`.

| Tool | Purpose |
|---|---|
| `tools.telegram_ids` | Prints chat id, topic id and your user id after you send `/start@bot` in the topic |
| `tools.find_device` | Finds the charger on the LAN by Device ID (no key needed) |
| `tools.dump_dps` | One-shot decoded DP dump from the charger |
| `tools.renew_local_key` | Fetches the Local Key from the Tuya cloud again and updates `.env` |
| `tools.import_smartlife` | Imports the Smart Life "Record" export (`.xlsx`) into the sessions table |
| `tools.replay` | Replays a discovery log through the state machine (used by the tests) |

---

## How it reads the charger

The full, measured data-point map (numbers, codes, scaling, observed values and state signatures) is in **[docs/DP-MAP.md](docs/DP-MAP.md)**. Highlights:

- `work_state` (DP3) only ever showed `charger_free` / `charger_wait` / `charger_charging` on the reference device; the bot still handles the other enum values.
- Per-phase voltage/current/power arrive as 7-byte raw records (DP6/7/8) roughly every 6 s; the sum matches `power_total` (DP9) exactly.
- The session counter (DP25) is sent only on unplug or when the charger closes its own record (it does that after **12 hours** of charging, or after 20 hours plugged in without charging). The bot therefore also integrates power readings and shows both numbers.
- The charger pushes most changes on its own, but not all (e.g. `charging` sometimes lags power), so the bot listens **and** polls (20 s charging / 60 s idle). A second connection from the Smart Life app does not disturb it.
- Debouncing rules were derived from real captures: 3-second `free` + 6 A after a reboot, 6-second `switch` flicker on unplug, 0 A "charging" after the car unlocks. See the fixture-based regression test in `tests/test_replay.py`.

---

## What the charger does not provide

Reported honestly instead of guessed:

1. **No lifetime energy counter** — the bot keeps its own total from sessions (plus the imported history).
2. **No live session energy** — during charging the energy is computed from power; the exact counter arrives at unplug.
3. **No temperature** — temperature warnings and "peak temperature" cannot be reported.
4. **No control-pilot voltage** — plugged/unplugged is derived from `work_state`.
5. **No battery percentage** — only estimates from delivered energy, always labelled *estimate*.
6. **No power factor, frequency or leakage-current value** (leakage exists only as an alarm bit).
7. Voltage resolution 1 V, current 0.1 A.

---

## Troubleshooting

| Symptom | What to check |
|---|---|
| "🛑 authentication error" message | The Local Key changed (device removed/re-added in Smart Life). Run `tools.renew_local_key` (needs the Tuya cloud keys and an active IoT Core trial), restart. |
| "📴 Charger offline" right after install | Wrong IP or different VLAN. `tools.find_device` must see the charger; UDP 6666/6667/7000 broadcasts must reach the bot's network. |
| No Telegram messages at all | Check `journalctl -u ev-charger-bot`; verify the token, that the bot is in the group, and the chat/topic ids (`tools.telegram_ids`). |
| Commands not answered | The bot answers only in the configured group. In groups with Topics the message must come from that group; privacy mode should be *disabled* in @BotFather (`/setprivacy`). |
| IP of the charger changes | The bot rescans by Device ID and keeps working; still, reserve the IP in your router (DHCP reservation). |
| Energy numbers differ | The charger counter (DP25) is authoritative; the integrated value is shown with its difference. |

More in the install guide's troubleshooting section.

---

## Support the project

ev-charger-bot is free for personal, non-commercial use. If it saves you time or electricity money, a donation is appreciated — see the **Donate** link in the repository description or contact the author at haliskilic90@gmail.com. Commercial use (companies, fleets, charging sites, resale) requires a commercial license — see below.

---

## License

Copyright © 2026 Halis KILIÇ. Source-available under a **non-commercial license**: free for personal and non-commercial use (donations welcome), commercial use only with a written license from the author. See [LICENSE](LICENSE) for the full terms and [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for the open-source libraries used.
