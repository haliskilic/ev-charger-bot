# Installation guide (English)

**🌐 [English](INSTALL.en.md) · [Türkçe](INSTALL.tr.md)**

This guide assumes no prior experience. Follow it top to bottom: **Part A** (charger keys) and **Part B** (Telegram) are the same for every platform; then do **one** of the platform sections in **Part C**; finish with **Part D** (first-run checks).

Time needed: about 45–60 minutes the first time.

---

## What you will end up with

```
┌──────────────┐   Wi-Fi/LAN (local, port 6668)   ┌──────────────────────┐   HTTPS   ┌──────────┐
│  EV charger  │ ◄──────────────────────────────► │  ev-charger-bot      │ ────────► │ Telegram │
│ (Tuya/Smart  │   read-only: status + heartbeat   │  Python + SQLite     │           │  group   │
│   Life app)  │                                   │  Windows/Linux/Pi/LXC│           │  topic   │
└──────────────┘                                   └──────────────────────┘           └──────────┘
```

You need four pieces of information for the `.env` file:

| Value | Where it comes from |
|---|---|
| `TUYA_DEVICE_ID`, `TUYA_DEVICE_IP`, `TUYA_VERSION` | LAN scan (`python -m tinytuya scan`) — Part A |
| `TUYA_LOCAL_KEY` | Tuya developer platform (once) — Part A |
| `TELEGRAM_BOT_TOKEN` | @BotFather — Part B |
| `TELEGRAM_CHAT_ID`, `TELEGRAM_THREAD_ID`, `TELEGRAM_OWNER_ID` | `tools.telegram_ids` — Part B |

---

## Part A — Charger: Device ID, IP, protocol version and Local Key

### A1. Prerequisites
1. The charger is already added to the **Smart Life** (or **Tuya Smart**) app on your phone and shows as *online*.
2. The computer that will run the bot is on the **same Wi-Fi/LAN** as the charger (same router, same VLAN). Guest networks usually block device-to-device traffic — do not use one.
3. Reserve a fixed IP for the charger in your router (DHCP reservation / "static lease"). The bot can find the charger if its IP changes, but a fixed IP avoids a few minutes of "offline" each time.

### A2. Find Device ID, IP and version (no account needed)
After Part C has installed Python and the project (you can come back here), run in the project folder:

```
venv/bin/python -m tinytuya scan          # Windows: venv\Scripts\python -m tinytuya scan
```

After ~20 s it prints every Tuya device on your LAN, e.g.:

```
Unknown v3.4 Device   Product ID = bkxxxxxxxxxxxxxx  [Valid Broadcast]:
    Address = 192.168.1.129   Device ID = bfd8xxxxxxxxxxxxxxxxxx   Version = 3.4
```

Write down **Device ID**, **Address (IP)** and **Version** (3.3, 3.4 or 3.5). If nothing is found, see Troubleshooting.

> Alternative for the Device ID: Smart Life app → open the charger → pencil icon (top right) → **Device Information** → *Device ID*.

### A3. Tuya developer account (for the Local Key)
The Local Key is the encryption key the app uses to talk to the charger locally. Tuya hands it out only through its developer platform.

1. Open **https://iot.tuya.com** → **Sign Up**. Use the same e-mail as your Smart Life account if possible (not required). Choose your country.
2. Log in. If a questionnaire appears, you can skip it.
3. Left menu **Cloud → Development** → top right **Create Cloud Project**:
   - *Project Name*: `ev-charger-bot`
   - *Industry*: **Smart Home** · *Development Method*: **Smart Home**
   - *Data Center*: the one for your region — **Central Europe** for Europe/Türkiye, **Western America** for the Americas, **India**, **China** … (if your device later does not show up, switch the data center under *Project → Overview → Data Center*).
   - **Create**.
4. In the *Configuration Wizard* that follows, keep **IoT Core** and **Authorization Token Management** selected and click **Authorize**.
5. If you get the error *"IoT Core service subscription has expired"* later, go to **Cloud → Cloud Services → IoT Core → Free Trial** (or *My Services → IoT Core → Extend Trial Period*), fill in the short form ("Personal home automation, local control of my own device") and submit. The trial is free; it must be re-extended every few months **only if** you need the cloud again (e.g. to renew the Local Key). The bot itself never uses the cloud.

### A4. Link your Smart Life app account
1. Open the project → tab **Devices** → **Link App Account** (older UI: *Link Tuya App Account*) → **Add App Account**.
2. A QR code appears. On your phone: Smart Life → **Me** → the **scan icon** (top right, ⊡) → scan the QR → **Confirm login**.
3. The charger now appears under *Devices → All Devices*. If the list is empty, the data center is wrong (step A3, point 3).

### A5. Access ID / Access Secret
Project → **Overview** tab → **Authorization Key**: copy **Access ID/Client ID** and **Access Secret/Client Secret**. Treat them like passwords.

### A6. Get the Local Key
Put these into `.env` (Part C explains where the file is): `TUYA_ACCESS_ID`, `TUYA_ACCESS_SECRET`, `TUYA_REGION` (`eu` for Central Europe, `us`, `in`, `cn`) and `TUYA_DEVICE_ID`. Then run:

```
venv/bin/python -m tools.renew_local_key      # Windows: venv\Scripts\python -m tools.renew_local_key
```

It writes `TUYA_LOCAL_KEY=...` into `.env`. (Equivalent alternative: `python -m tinytuya wizard`, which also saves a `devices.json` with all your devices and their keys.)

> **The Local Key changes** whenever you delete the charger from the app and add it again. Then just run `tools.renew_local_key` again and restart the bot. The bot tells you in Telegram when this is needed ("authentication error").

---

## Part B — Telegram bot, group and ids

### B1. Create the bot
1. In Telegram open **@BotFather** → `/newbot`.
2. *Name*: e.g. `EV Charger Bot` (any text). *Username*: must end in `bot`, e.g. `my_ev_charger_bot`.
3. BotFather replies with the **token** (`123456789:AAE…`). Copy it into `.env` as `TELEGRAM_BOT_TOKEN`. Never share it.
4. Still in BotFather: `/setprivacy` → choose your bot → **Disable**. (Otherwise the bot cannot see all messages in groups with Topics.)

### B2. Group and topic
1. Create a Telegram **group** (or use an existing private one). Recommended: group settings → **Topics** on, then create a topic such as *EV Charger*. (A plain group without topics works too.)
2. Group → **Add members** → add your bot. If replies do not arrive later, also make it an **administrator** (needed in some topic groups).
3. Open the target topic and send: `/start@my_ev_charger_bot` (your bot's username).

### B3. Read the ids
With the bot service **not** running yet (only one process may poll Telegram):

```
venv/bin/python -m tools.telegram_ids          # Windows: venv\Scripts\python -m tools.telegram_ids
```

Output example:
```
chat: -1001234567890  type=supergroup  title='My bots'  forum=True
  thread (topic) id: 1234
  from user id: 123456789 (Your Name)  text='/start@my_ev_charger_bot'
```

Put them into `.env`: `TELEGRAM_CHAT_ID=-1001234567890`, `TELEGRAM_THREAD_ID=1234` (leave empty for the *General* topic or a group without topics), `TELEGRAM_OWNER_ID=123456789` (your own id — only this user may change settings).

---

## Part C — Install on your platform

Pick one: [Windows](#c1-windows-10--11) · [Ubuntu](#c2-ubuntu-2204--2404-desktop-or-server) · [Raspberry Pi](#c3-raspberry-pi-os) · [Proxmox LXC](#c4-proxmox-ve-lxc-container)

### Common `.env` reference
```
TUYA_ACCESS_ID=          # Part A5 (only needed to fetch/renew the Local Key)
TUYA_ACCESS_SECRET=
TUYA_REGION=eu
TUYA_DEVICE_ID=          # Part A2
TUYA_DEVICE_IP=192.168.1.129
TUYA_VERSION=3.4
TUYA_LOCAL_KEY=          # Part A6 (written by tools.renew_local_key)
TELEGRAM_BOT_TOKEN=      # Part B1
TELEGRAM_CHAT_ID=-100…   # Part B3
TELEGRAM_THREAD_ID=      # Part B3 (empty = General)
TELEGRAM_OWNER_ID=       # Part B3
```
`config.toml` holds language, prices, car data and intervals — open it in any editor; every line is commented. Set `language = "tr"` for Turkish messages.

---

### C1. Windows 10 / 11

1. **Install Python**: open https://www.python.org/downloads/windows/ → *Download Python 3.12.x* (64-bit installer). Run it and **tick "Add python.exe to PATH"** before clicking *Install Now*.
2. **Get the project**: open https://github.com/haliskilic/ev-charger-bot → green **Code** button → **Download ZIP**. Extract it to `C:\ev-charger-bot` (so that `C:\ev-charger-bot\requirements.txt` exists). (If you have Git: `git clone https://github.com/haliskilic/ev-charger-bot C:\ev-charger-bot`.)
3. **Open a terminal in the folder**: in File Explorer, go to `C:\ev-charger-bot`, click the address bar, type `powershell`, press Enter.
4. **Create the virtual environment and install dependencies** (copy each line, press Enter, wait):
   ```powershell
   py -3 -m venv venv
   venv\Scripts\pip install -r requirements.txt tzdata
   ```
5. **Create `.env`**: `copy .env.example .env` then `notepad .env`. Fill in the values from Parts A and B (you can do A2/A6/B3 now — the commands above work from this PowerShell window with `venv\Scripts\python`). Save and close Notepad.
6. **Windows Firewall**: the first LAN scan (`venv\Scripts\python -m tinytuya scan`) shows a firewall prompt — allow **Private networks**. If it was blocked, open *Windows Security → Firewall → Allow an app* and allow `python.exe` on private networks.
7. **Test run**:
   ```powershell
   venv\Scripts\python -m evsarj.main
   ```
   Within ~10 s your Telegram topic receives *"🔄 Bot restarted"*. Send `/status` in the topic. Stop the test with **Ctrl+C**.
8. **Start automatically at boot (Task Scheduler)**:
   1. Press *Win*, type **Task Scheduler**, open it → right pane **Create Task…** (not *Basic Task*).
   2. *General*: Name `ev-charger-bot`; select **Run whether user is logged on or not**; tick **Run with highest privileges** is *not* needed.
   3. *Triggers* → **New…** → *Begin the task*: **At startup** → OK.
   4. *Actions* → **New…** → *Program/script*: `C:\ev-charger-bot\venv\Scripts\python.exe` · *Add arguments*: `-m evsarj.main` · *Start in*: `C:\ev-charger-bot` → OK.
   5. *Conditions*: untick **Start the task only if the computer is on AC power**.
   6. *Settings*: tick **If the task fails, restart every: 1 minute**, *Attempt to restart up to* **999** times; untick *Stop the task if it runs longer than*; *If the task is already running*: **Do not start a new instance**.
   7. OK → enter your Windows password. Right-click the task → **Run** to start it now. Logs: the bot prints to its console, which is hidden for scheduled tasks; to keep a log file instead, set *Program/script* to `C:\ev-charger-bot\scripts\run.bat` (it appends to `data\bot.log`, 10 MB rotation).
9. The PC must not go to sleep: *Settings → System → Power → Sleep: Never* (on AC).

### C2. Ubuntu 22.04 / 24.04 (desktop or server)

Open a terminal (Ctrl+Alt+T) and run the commands one by one.

1. **System packages**
   ```bash
   sudo apt update && sudo apt install -y python3 python3-venv python3-pip git sqlite3
   python3 --version        # must be 3.11 or newer (22.04 ships 3.10 → use the deadsnakes PPA, see note)
   ```
   > Ubuntu 22.04 ships Python 3.10, which is too old. Either use 24.04, or: `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install -y python3.12 python3.12-venv` and use `python3.12` instead of `python3` below.
2. **Service user and project folder**
   ```bash
   sudo useradd --system --home-dir /opt/ev-charger-bot --shell /usr/sbin/nologin evsarj
   sudo git clone https://github.com/haliskilic/ev-charger-bot /opt/ev-charger-bot
   cd /opt/ev-charger-bot
   sudo cp .env.example .env
   sudo chown -R evsarj:evsarj /opt/ev-charger-bot && sudo chmod 750 /opt/ev-charger-bot && sudo chmod 600 .env
   ```
3. **Virtual environment and dependencies**
   ```bash
   sudo -u evsarj python3 -m venv venv
   sudo -u evsarj venv/bin/pip install -r requirements.txt
   ```
4. **Fill in `.env`**: `sudo nano .env` (Parts A and B; run the helper tools as `sudo -u evsarj venv/bin/python -m tinytuya scan`, `… -m tools.renew_local_key`, `… -m tools.telegram_ids`). Save with Ctrl+O, Enter, exit with Ctrl+X.
5. **Test run** (as the service user):
   ```bash
   sudo -u evsarj venv/bin/python -m evsarj.main
   ```
   Wait for *"🔄 Bot restarted"* in Telegram, try `/status`, then stop with Ctrl+C.
6. **systemd service** (starts at boot, restarts on crash, logs to journald):
   ```bash
   sudo cp ev-charger-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now ev-charger-bot
   systemctl status ev-charger-bot          # should say "active (running)"
   journalctl -u ev-charger-bot -f          # live log, Ctrl+C to leave
   ```
   If you installed somewhere other than `/opt/ev-charger-bot`, edit the paths in the unit file first (`WorkingDirectory`, `Environment=EVSARJ_HOME`, `ExecStart`, `ReadWritePaths`).
7. **Bounded logs** (recommended so the disk can never fill):
   ```bash
   sudo mkdir -p /etc/systemd/journald.conf.d
   printf "[Journal]\nSystemMaxUse=100M\nSystemMaxFileSize=10M\nMaxRetentionSec=12month\n" | sudo tee /etc/systemd/journald.conf.d/retention.conf
   sudo systemctl restart systemd-journald
   ```

### C3. Raspberry Pi OS

Tested approach: Raspberry Pi 3/4/5 or Zero 2 W with **Raspberry Pi OS (64-bit) Lite, Bookworm** or newer (Python 3.11+). Flash with *Raspberry Pi Imager*, enable SSH and Wi-Fi in the imager's settings, boot, then SSH in (`ssh pi@raspberrypi.local`).

1. Follow **C2 (Ubuntu)** steps 1–7 exactly as written — Raspberry Pi OS is Debian, so the commands are identical (`python3` is already 3.11+; no PPA needed).
2. Pi-specific tips:
   - Use a decent SD card (A1/A2 class) or a USB SSD; the database writes a few KB per minute, which is fine for SD cards, but journald logs are bounded in step 7 for the same reason.
   - If the Pi is on Wi-Fi, disable Wi-Fi power saving so the connection to the charger does not drop: `sudo iw dev wlan0 set power_save off` (persist via `/etc/rc.local` or a NetworkManager setting `wifi.powersave 2`).
   - Set the time zone: `sudo raspi-config` → *Localisation Options → Timezone* (and the same value in `config.toml`).

### C4. Proxmox VE (LXC container)

Creates a tiny unprivileged Debian container (1 core, 512 MB RAM, 4 GB disk) — the reference installation runs exactly like this.

1. **Template**: Proxmox web UI → your node → *local* storage → **CT Templates** → **Templates** → download **debian-13-standard** (or debian-12). (Shell alternative: `pveam update && pveam download local debian-13-standard_13.6-1_amd64.tar.zst`.)
2. **Create CT** (top right button) with these values:
   - *General*: CT ID (next free), Hostname `ev-charger-bot`, **Unprivileged container ✓**, password for root.
   - *Template*: the Debian template from step 1.
   - *Disks*: 4 GB on `local-lvm` (or any rootdir storage).
   - *CPU*: 1 core · *Memory*: 512 MB, swap 512 MB.
   - *Network*: bridge `vmbr0` (the bridge your LAN is on), IPv4 **DHCP** (then reserve the IP in your router) or a static IP in your LAN.
   - *DNS*: use host settings. Tick **Start after created**.
   Shell alternative (one line):
   ```bash
   pct create 103 local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst --hostname ev-charger-bot --unprivileged 1 --cores 1 --memory 512 --swap 512 --rootfs local-lvm:4 --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1 --timezone Europe/Istanbul --start 1
   ```
3. **Enter the container**: node → container → **Console**, log in as root (or from the host shell: `pct enter 103`). Then:
   ```bash
   apt update && apt -y full-upgrade
   apt -y install python3 python3-venv python3-pip git sqlite3 curl
   timedatectl set-timezone Europe/Istanbul      # your time zone
   ```
4. **Checks**: `curl -sI https://api.telegram.org | head -1` (Telegram reachable) and `ping -c2 <charger IP>` (same LAN). The charger's UDP broadcasts must reach the container: `python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('',6667));s.settimeout(30);print(s.recvfrom(1024)[1])"` prints the charger's IP within 30 s if everything is on the same network.
5. Now follow **C2 (Ubuntu)** steps 2–7 inside the container (you are root, so drop the `sudo`). Debian 13 ships Python 3.13; Debian 12 ships 3.11 — both are fine.
6. The container has **Start at boot** set (`--onboot 1` / Options → Start at boot), so the bot comes back after a host reboot.

---

## Part D — First-run checks

1. **Restart message**: after `systemctl restart ev-charger-bot` (or restarting the task on Windows) a *"🔄 Bot restarted"* message arrives in the topic within ~10 s. The message states whether the charger is online.
2. **Commands**: send `/status`, `/raw`, `/help` in the topic. `/raw` must list DP 3, 4, 9, 10, 14, 18, 23 (and 6/7/8/25 after the first charging session).
3. **Outage test**: switch the charger's breaker off for 3 minutes. Expect *"📴 Charger offline"* after ~90 s and *"📶 Charger back online"* plus possibly *"♻️ Charger rebooted"* afterwards.
4. **Real session**: plug the car in and charge. Expect *plugged in → charging started → live status (edited every 5 min) → interim report (30 min) → complete → unplugged + session summary*.
5. **Import history** (optional): in Smart Life open the charger → **Record** → export (share) the `.xlsx`, copy it to the bot machine and run `venv/bin/python -m tools.import_smartlife export.xlsx`.
6. **Language**: send `/language tr` (or `en`) to switch; or set `language` in `config.toml`.

---

## Part E — Operating

| Task | How |
|---|---|
| Live log | Linux: `journalctl -u ev-charger-bot -f` · Windows: `data\bot.log` (when started via `scripts\run.bat`) |
| Restart | Linux: `sudo systemctl restart ev-charger-bot` · Windows: Task Scheduler → right-click → End, then Run |
| Update | `cd /opt/ev-charger-bot && sudo -u evsarj git pull && sudo -u evsarj venv/bin/pip install -r requirements.txt && sudo systemctl restart ev-charger-bot` (Windows: download the new ZIP over the folder, keep `.env`, `config.toml`, `data\`) |
| Backup | copy `data/evsarj.db` (consistent copy while running: `sqlite3 data/evsarj.db ".backup backup.db"`) plus `.env` and `config.toml` |
| Renew Local Key | `venv/bin/python -m tools.renew_local_key` then restart |
| Change prices / intervals | edit `config.toml` and restart, or use `/tariff`, `/settings` in Telegram (owner only) |
| Uninstall | `sudo systemctl disable --now ev-charger-bot && sudo rm /etc/systemd/system/ev-charger-bot.service && sudo rm -rf /opt/ev-charger-bot && sudo userdel evsarj` |

---

## Troubleshooting

**`tinytuya scan` finds nothing**
- The bot machine and the charger must be on the same LAN/VLAN; guest Wi-Fi and "AP isolation" block the broadcasts. A wired connection on the same router is the simplest test.
- Windows: allow `python.exe` through the firewall on *private* networks.
- Docker/VM networks that use NAT do not receive broadcasts; use a bridged network (LXC on `vmbr0` works).

**"authentication error" / `Err 914` / "Check device key or version"**
- Wrong `TUYA_LOCAL_KEY` or `TUYA_VERSION`. Fetch the key again (`tools.renew_local_key`) and use the version printed by the scan.

**IoT Core "subscription has expired"**
- Extend the free trial under *Cloud → Cloud Services → IoT Core* (see A3, point 5). Only needed when you fetch the Local Key.

**Bot does not answer commands**
- Check `TELEGRAM_CHAT_ID` (negative, starts with `-100` for supergroups) and that the command was sent in that group. Privacy mode must be *disabled* in BotFather. Look at the log for `Forbidden`/`Unauthorized` (wrong token or bot removed from the group).

**Messages arrive in the wrong topic**
- `TELEGRAM_THREAD_ID` must be the topic id from `tools.telegram_ids`; leave it empty for the *General* topic.

**"Charger offline" although the app works**
- The app may be going through the cloud while LAN access is blocked. Check the IP (`tools.find_device`) and that nothing (firewall, VLAN rule) blocks TCP port **6668** to the charger.

**Time or dates are wrong**
- Set `timezone` in `config.toml` (e.g. `Europe/Berlin`) and the OS time zone; on Windows `tzdata` must be installed in the venv.
