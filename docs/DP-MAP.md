# Data-point (DP) map — Hici 22 kW / Tuya `qccdz` (protocol 3.4)

Measured on 2026-10-11 with a live cable-in/cable-out/charge/stop/resume/unplug/power-cut test. The raw capture is in
`tests/fixtures/discovery_2026-10-11.jsonl` and drives the regression test `tests/test_replay.py`.
*(Türkçe özet en altta.)*

## Data points

| DP | Code | Meaning | Type / unit / scale | How it arrives | Example |
|---|---|---|---|---|---|
| 3 | `work_state` | Charger state | enum | pushed on change, **but not always** (poll needed) | `charger_free`, `charger_wait`, `charger_charging` |
| 4 | `charge_cur_set` | Current limit | A, 6–48 | in status replies | 32 (briefly 6 right after a reboot) |
| 6 / 7 / 8 | `phase_a` / `phase_b` / `phase_c` | Phase A/B/C | raw, 7 bytes: V (2 B, ×0.1) + A (3 B, ×0.001) + kW (2 B, ×0.001) | pushed every ~6 s | `08e4 001e14 062c` = 228.0 V, 7.7 A, 1.596 kW |
| 9 | `power_total` | Total power | kW, ×0.001 | pushed on change | 4655 = 4.655 kW (= sum of the phases) |
| 10 | `fault` | Fault bitmap (16 bits) | bitmap | in status replies | 0 |
| 14 | `work_mode` | Work mode | enum `charge_now` / `charge_pct` / `charge_energy` / `charge_schedule` / `charge_delay` | pushed periodically (~37 s) | `charge_now` ("Real-time charge" in the app) |
| 18 | `switch` | Charging enabled (the app's start/stop button) | bool | pushed on change and periodically | true |
| 19 | `local_timer` | Local timer | raw, 2 bytes | pushed periodically | `0000` (empty; the format with a timer set was not observed) |
| 23 | `system_version` | Firmware version | string | in status replies | "V1" |
| 25 | `charge_energy_once` | Session energy | kWh, ×0.01 | **only on unplug** or when the charger closes its record; repeated in query replies | 56 = 0.56 kWh |

Enum values defined in the cloud model but **never observed** on this device: `charger_insert`, `charger_pause`, `charger_end`, `charger_fault`, `charger_free_fault`. The bot handles them anyway.

### Fault bits (DP10)

| bit | code | meaning |
|---|---|---|
| 0 | ov_cr | overcurrent |
| 1 | ov2_cr_fault | overcurrent (stage 2) |
| 2 | ov_vol | overvoltage |
| 3 | undervoltage_alarm | undervoltage |
| 4 | contactor_adhesion | contactor welded |
| 5 | contactor_fault | contactor fault |
| 6 | earth_fault | earth fault |
| 7 | meter_hardware_alarm | meter hardware alarm |
| 8 | scram_fault | emergency stop |
| 9 | cp_fault | CP (control pilot) fault |
| 10 | meter_commu_fault | meter communication fault |
| 11 | card_reader_fault | card reader fault |
| 12 | cir_short_fault | short circuit |
| 13 | adhesion_fault | relay welded |
| 14 | self_test_alarm | self-test alarm |
| 15 | leakagecurr_alarm | leakage current alarm |

## Observed behaviour and state signatures

| Event | Signature |
|---|---|
| Car plugged in | `free` → `wait` (never `insert`) |
| Charging started | `wait` → `charging`, **power > 0**; the state can lag the power by ~15 s |
| Stopped from the app | `switch` false, then `charging` → `wait`; the reported power stays stale for ~20 s |
| Car stopped / full | `switch` true, `charging` → `wait`, power 0 |
| Car unlocked (door key) | `charging` with voltage present but **0 A** for ~30 s; the car re-locks and resumes if the cable is not removed |
| Cable unplugged | `wait` → `free`; DP25 arrives in the same second (sometimes 1 s **before** DP3); `switch` flips false for 6 s and back to true |
| Power cut / reboot | silence, then a full dump: `free` + current limit **6 A**, 3 s later `wait` + the previous limit; Wi-Fi is back within ~5 s |
| Charger closes its record | DP25 arrives while still plugged: 12 h after charging started, or 20 h after plugging in without charging (seen in the Smart Life history: 47 % of records are exactly 12 h 00 min) |
| App open at the same time | no effect on the bot's connection (the charger accepts a second local connection) |

### Rules the bot derives from this
- Work-state transitions are accepted only after 5 s (`debounce_s`); "charging started" is decided by power, not by state.
- "Stopped from the app" is decided 10 s after `switch` goes false, unless `free` follows (that was an unplug).
- A charging segment ends after 60 s at 0 W; the end reason is chosen from `switch`, `fault`, online state and the shape of the last 5 minutes (taper → "car full").
- DP25 counts only when its value changes; while plugged it is held for 20 s to see whether an unplug follows.
- Energy is integrated from power readings per tariff band and compared with DP25 in the summary.
- Energy accuracy of the integration vs. the charger counter: within ~5–10 % on short sessions (the counter has 0.01 kWh resolution; power is reported on change only).

## What the charger does **not** provide
Lifetime energy counter · live session energy · temperature · control-pilot voltage · battery state of charge · power factor / frequency / leakage current value · its own "Record" history over LAN. Voltage resolution 1 V, current 0.1 A.

---

## Türkçe özet

Yukarıdaki tablo 11.10.2026'daki canlı testle ölçüldü. Özet: DP3 durumu yalnızca `free` / `wait` / `charging` değerlerini gösterdi; faz verisi 7 baytlık ham kayıt (gerilim ×0,1 V, akım ×0,001 A, güç ×0,001 kW) ve toplamı DP9 ile birebir aynı; DP25 oturum sayacı yalnızca çıkarmada ya da cihazın kendi kaydını kapattığında (şarj başladıktan 12 saat, şarjsız 20 saat sonra) gelir; cihaz yeniden başlarken 3 sn `free` + 6 A gösterir; çıkarmada `switch` 6 sn kapanıp açılır; araç kilidi açılınca 0 A ile `charging` görülür. Cihazın vermedikleri: ömür boyu sayaç, canlı oturum enerjisi, sıcaklık, kontrol pilotu gerilimi, batarya yüzdesi, güç faktörü/frekans/kaçak akım değeri.
