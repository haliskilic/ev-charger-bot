<!-- ev-charger-bot — README (Türkçe). English / varsayılan: README.md -->

**🌐 [English](README.md) · [Türkçe](README.tr.md)**

# ev-charger-bot

[![Lisans: AGPL-3.0](https://img.shields.io/badge/Lisans-AGPL--3.0-blue.svg)](LICENSE) [![Ticari lisans](https://img.shields.io/badge/Ticari-lisans%20mevcut-green.svg)](COMMERCIAL_LICENSE.md) [![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/haliskilic)

**Tuya / Smart Life altyapılı bir elektrikli araç şarj cihazını yerel ağ üzerinden 7/24 izleyen ve şarj oturumlarını, maliyeti, uyarıları ve günlük/haftalık/aylık özetleri Telegram grubunuzdaki bir konuya (topic) Türkçe ya da İngilizce raporlayan, salt okunur bir bot.**

> **Hici 22 kW** üç fazlı duvar tipi şarj cihazı (Tuya kategorisi `qccdz`, protokol 3.4) ve **Seat Leon e-Hybrid** PHEV ile geliştirilip ölçülerek doğrulandı. Diğer Tuya `qccdz` cihazları aynı veri noktalarını kullandığı için çoğunlukla değişiklik gerekmeden çalışır.

- **Yerel, buluttan bağımsız:** cihazla doğrudan LAN üzerinden konuşur (`tinytuya`); Tuya bulutu yalnızca kurulumda, Local Key'i almak için bir kez kullanılır.
- **Tasarım gereği salt okunur:** cihazda hiçbir şeyi başlatmaz, durdurmaz, değiştirmez.
- **Özel:** yalnızca *sizin* Telegram grubunuzda yanıt verir; başka herkesi yok sayar, eklendiği başka sohbetten hemen çıkar.
- **Küçük:** tek bir Python süreci, SQLite, dış servis yok. Windows, Ubuntu, Raspberry Pi ya da Proxmox LXC üzerinde çalışır.

---

## İçindekiler

- [Neler sunar](#neler-sunar)
- [Örnek mesajlar](#örnek-mesajlar)
- [Gereksinimler](#gereksinimler)
- [Kurulum](#kurulum)
- [Komutlar](#komutlar)
- [Yapılandırma](#yapılandırma)
- [Güvenlik modeli](#güvenlik-modeli)
- [Veri, loglar ve saklama süreleri](#veri-loglar-ve-saklama-süreleri)
- [Araçlar](#araçlar)
- [Cihazı nasıl okur](#cihazı-nasıl-okur)
- [Cihazın vermediği veriler](#cihazın-vermediği-veriler)
- [Sorun giderme](#sorun-giderme)
- [Projeye destek](#projeye-destek)
- [Lisans](#lisans)

---

## Neler sunar

**Anlık olaylar**
- Araç takıldı / çıkarıldı
- Şarj başladı / uygulamadan durduruldu / devam etti / tamamlandı (araç doldu ile araç aniden durdurdu ayrımıyla)
- Zamanlanmış ya da gecikmeli şarj bekliyor; "takılı ama şarj başlamadı" bilgisi
- Arıza oluştu / düzeldi, arıza bitlerinin Türkçe açıklamasıyla
- Cihaz çevrimdışı / geri geldi (kesinti süresiyle); cihaz yeniden başladı (kısa elektrik kesintisi)
- Cihazda ayar değişti: akım limiti, çalışma modu, zamanlayıcı
- Uyarılar: gerilim aralık dışı, faz kaybı, faz dengesizliği, beklenmedik güç düşüşü, 0 A ile "şarj"
- Bot yeniden başladı (açık oturum sürdürülür, iki kez sayılmaz)

**Şarj sürerken**
- Yerinde düzenlenen tek bir **canlı durum** mesajı (varsayılan 5 dk): toplam güç, faz başına V/A/kW, aktif faz sayısı, akım limiti, verilen enerji, geçen süre, ortalama güç, o ana kadarki maliyet, tahmini eklenen batarya yüzdesi ve menzil, en geç bitiş saati.
- **Ara rapor** (varsayılan 30 dk).

**Oturum özeti** (araç çıkarılınca)
- Takılma, şarj başlangıcı, şarj bitişi ve çıkarılma saatleri; takılı kalma süresi ile fiilen şarj edilen süre ayrı ayrı
- Enerji: cihazın kendi sayacı **ve** güç ölçümlerinin integrali (fark gösterilir)
- Ortalama / en yüksek güç; faz başına en düşük–en yüksek gerilim ve akım
- Maliyet (tek fiyat ya da üç zamanlı gündüz/puant/gece)
- Tahmini eklenen batarya yüzdesi ve elektrikli menzil (her zaman *tahmin* etiketiyle)
- Bitiş nedeni: araç doldu (kademeli) / araç durdurdu / uygulamadan durduruldu / kablo çıkarıldı / arıza / kesinti
- Oturum sırasındaki uyarılar ve kesintiler

**Dönemsel özetler**
- Günlük, haftalık, aylık: oturum sayısı, kWh, maliyet, şarj süresi, oturum başına ortalama, en yüksek güç, önceki döneme göre değişim, bot kayıtlarına göre toplam.
- Şarj olmayan günlerde tek satırlık "cihaz çevrimiçi, bugün şarj yok" (kapatılabilir).

**Geçmiş aktarımı** — Smart Life "Record" dışa aktarımı (`.xlsx`) içe alınabilir; böylece `/gecmis`, `/ay` ve karşılaştırmalar ilk günden doludur.

---

## Örnek mesajlar

<details open>
<summary><b>Olaylar</b></summary>

```
🔄 Bot yeniden başladı · 11.10.2026 19:31
Cihaz çevrimiçi · boşta, araç takılı değil · açık oturum yok
```
```
🔌 Araç takıldı · 18:13
Akım limiti 32 A · Mod: anında şarj
```
```
⚡ Şarj başladı · 18:13
4,66 kW · 7,7 / 7,6 / 7,6 A · 3 faz
```
```
⏸ Şarj durduruldu (uygulamadan) · 18:17
Bu oturumda şu ana kadar ~0,30 kWh · 4 dk şarj
```
```
▶️ Şarj devam ediyor · 18:19
4,63 kW · 7,7 / 7,6 / 7,6 A · 3 faz
```
```
✅ Şarj tamamlandı · 21:02
Güç kademeli düşerek bitti: araç doldu.
Oturum: ~19,80 kWh · 1 sa 52 dk şarj · ort. 10,60 kW
```
```
⏹ Araç şarjı sonlandırdı · 18:22
Güç aniden kesildi (batarya dolu olabilir).
Oturum: ~0,54 kWh · 7 dk şarj · ort. 4,64 kW
```
```
ℹ️ Şarj başlamadı · 11:26
Araç 3 dk süredir takılı, akım çekmiyor. Batarya dolu ya da aracın zamanlayıcısı bekliyor olabilir.
```
```
🚨 Arıza · 18:40
kaçak akım alarmı (bit 15)
Durum: charger_fault · şarj durdu
```
```
📴 Cihaz çevrimdışı · 18:40
2 dk süredir veri yok (son veri 18:38). Şarj sürüyordu: ~5,20 kWh verilmişti.
```
```
📶 Cihaz geri geldi · 18:47 (kesinti 7 dk)
Durum: araç takılı, bekliyor
```
```
♻️ Cihaz yeniden başladı · 18:07
Kısa elektrik kesintisi olmuş olabilir (bağlantı 10 sn koptu). Araç takılı, bekliyor.
```
```
⚙️ Ayar değişti · 18:50
Akım limiti: 32 A → 16 A
```
```
⚠️ Faz dengesizliği · 19:45
Akımlar: 16,0 / 15,9 / 9,1 A (fark %43)
```
</details>

<details open>
<summary><b>Canlı durum (yerinde düzenlenen tek mesaj) ve ara rapor</b></summary>

```
🔋 CANLI DURUM · 19:25 (5 dk'da bir güncellenir)
Şarj oluyor · 47 dk · ~8,4 kWh

Güç 10,9 kW · 3 faz aktif · limit 32 A
A: 229 V · 15,9 A · 3,64 kW
B: 226 V · 15,8 A · 3,57 kW
C: 227 V · 15,9 A · 3,61 kW
Ortalama güç: 10,7 kW
Maliyet: 32,93 TL
Tahmini eklenen: +%38 (≈ +44 km) — tahmin
En geç bitiş: ~20:45 (boş batarya varsayımıyla)
```
```
📊 Ara rapor · 19:35 · şarj 57 dk süredir sürüyor
Verilen ~10,2 kWh · ort. 10,7 kW · en yüksek 11,0 kW
Maliyet 39,98 TL · tahmini +%47 (≈ +54 km) — tahmin
Gerilim 225–231 V · akım 15,8–16,0 A/faz
Uyarı yok
```
</details>

<details open>
<summary><b>Oturum özeti</b></summary>

```
🔌 Araç çıkarıldı · 18:24

📋 Oturum özeti · 11.10.2026
Takıldı 18:13 · Şarj 18:13–18:22 · Çıkarıldı 18:24
Takılı kaldı 11 dk · fiilen şarj 7 dk

Enerji: 0,56 kWh (cihaz sayacı)
  güç ölçümlerinden: 0,51 kWh (fark %9)
Güç: ort. 4,29 kW · en yüksek 4,67 kW
Faz A: 225–229 V · 7,7 A (ort. 7,7 A)
Faz B: 212–216 V · 7,6–7,7 A (ort. 7,6 A)
Faz C: 219–223 V · 7,5–7,6 A (ort. 7,6 A)
Maliyet: 2,20 TL (3,92 TL/kWh)
Tahmini eklenen: +%3 (≈ +3 km) — tahmin
Bitiş nedeni: araç şarjı sonlandırdı
Oturumda: 1 elle durdurma, 1 devam · uyarı yok
```
</details>

<details>
<summary><b>Dönemsel özetler ve komutlar</b></summary>

```
📅 Günlük özet · 11 Ekim 2026 Pazar
2 oturum · 13,4 kWh · 52,53 TL · 2 sa 10 dk şarj
Oturum başına ort. 6,7 kWh · en yüksek güç 11,0 kW
Düne göre: şarj yok (+13,4 kWh)
Bot kayıtlarına göre toplam: 4.036,4 kWh (cihazda ömür boyu sayaç yok)
```
```
📆 Haftalık özet · 5–11 Ekim 2026
5 oturum · 48,2 kWh · 188,94 TL · 6 sa 40 dk şarj
Oturum başına ort. 9,6 kWh · en yüksek güç 11,0 kW
Önceki haftaya göre: kWh +%12 · maliyet +%12
Bot kayıtlarına göre toplam: 4.036,4 kWh (cihazda ömür boyu sayaç yok)
```
```
📡 Durum · 18:33
Cihaz çevrimiçi · araç takılı, bekliyor
Akım limiti 32 A · Mod: anında şarj · Arıza yok
Gerilim: — (akım yokken faz verisi sıfır geliyor)
Son oturum: 11.10 18:13–18:22 · 0,56 kWh · 2,20 TL · 7 dk şarj · araç şarjı sonlandırdı
Son veri 6 sn önce · bot 2 sa 11 dk süredir çalışıyor
```
```
🕓 Son oturumlar
11.10 18:13–18:22 · 0,56 kWh · 2,20 TL · 7 dk şarj · araç şarjı sonlandırdı
01.10 18:41–06:41 · 15,07 kWh · 59,07 TL · takılı 12 sa · Smart Life kaydı
30.09 18:30–06:31 · 13,94 kWh · 54,64 TL · takılı 12 sa · Smart Life kaydı
```
</details>

---

## Gereksinimler

**Donanım**
- Smart Life (ya da Tuya Smart) uygulamasında kurulu ve Wi-Fi'a bağlı, Tuya altyapılı bir EV şarj cihazı. Doğrulanan: Hici 22 kW (`qccdz`). Tek fazlı cihazlar da çalışır (B/C fazları 0 kalır).
- Cihazla **aynı LAN / VLAN**'da, 7/24 açık bir makine: Raspberry Pi, Ubuntu bilgisayar, Proxmox LXC konteyneri ya da Windows PC. 1 çekirdek, 512 MB RAM ve 4 GB disk fazlasıyla yeter.

**Hesaplar (ücretsiz)**
- Tuya geliştirici hesabı (iot.tuya.com) — cihazın **Local Key**'ini okumak için bir kez kullanılır; ücretsiz "IoT Core" denemesi yeterlidir.
- **@BotFather** ile oluşturulmuş bir Telegram botu ve raporların gideceği bir Telegram grubu (tercihen Konular açık).

**Yazılım**
- Python **3.11 ya da üstü** (3.12/3.13 önerilir). Bağımlılıklar: `tinytuya`, `python-telegram-bot` (Windows'ta ayrıca `tzdata`).

---

## Kurulum

İlk kez kuranlar için adım adım kılavuzlar:

- **[docs/INSTALL.tr.md](docs/INSTALL.tr.md)** — ortak adımlar (Tuya Local Key, BotFather, sohbet kimlikleri) ve ardından **Windows 10/11**, **Ubuntu 22.04/24.04**, **Raspberry Pi OS**, **Proxmox VE (LXC)**.
- İngilizce: **[docs/INSTALL.en.md](docs/INSTALL.en.md)**.

Linux için kısa sürüm:

```bash
sudo apt install -y python3 python3-venv git
sudo useradd --system --home-dir /opt/ev-charger-bot --shell /usr/sbin/nologin evsarj
sudo git clone https://github.com/haliskilic/ev-charger-bot /opt/ev-charger-bot
cd /opt/ev-charger-bot && sudo cp .env.example .env && sudo nano .env      # gizli bilgileri girin
sudo chown -R evsarj:evsarj /opt/ev-charger-bot && sudo chmod 600 .env
sudo -u evsarj python3 -m venv venv && sudo -u evsarj venv/bin/pip install -r requirements.txt
sudo cp ev-charger-bot.service /etc/systemd/system/ && sudo systemctl enable --now ev-charger-bot
journalctl -u ev-charger-bot -f
```

---

## Komutlar

| Türkçe | İngilizce karşılığı | Ne yapar |
|---|---|---|
| `/durum` | `/status` | Cihazın anlık durumu, ayarları, son oturum, botun sağlığı |
| `/oturum` | `/session` | Açık şarj oturumu (ya da sonuncusu) |
| `/bugun` `/hafta` `/ay` | `/today` `/week` `/month` | Şu ana kadarki özetler |
| `/gecmis [n]` | `/history` | Son 10 (ya da n) oturum |
| `/tarife` | `/tariff` | Fiyat ve araç parametreleri; sahibi: `/tarife tek 3.92`, `/tarife uc 3.20 5.10 2.10` |
| `/ayar` | `/settings` | Aralıklar/eşikler; sahibi: `/ayar canli 5`, `/ayar ara 30`, `/ayar sessiz 23-07`, `/ayar bosgun kapali` |
| `/dil tr\|en` | `/language` | Mesaj dili (sahibi) |
| `/ham` | `/raw` | Ham DP dökümü, çözülmüş değer ve yaşıyla |
| `/disaaktar` | `/export` | Tüm oturumların CSV'si; `/disaaktar ham 7` = son 7 günün ham örnekleri |
| `/yardim` | `/help` | Komut listesi |

Her iki komut kümesi de etkin dilden bağımsız çalışır. Yanıtlar, komutun yazıldığı konuya gider.

---

## Yapılandırma

- **`.env`** — gizli bilgiler ve kimlikler (bot token'ı, grup/konu/sahip kimlikleri, Device ID, Local Key, IP, protokol sürümü, isteğe bağlı Tuya bulut anahtarları). Yalnızca servis kullanıcısı okuyabilmeli (`chmod 600`). Şablon: [`.env.example`](.env.example).
- **`config.toml`** — geri kalan her şey, açıklamalarıyla: dil, aralıklar, sessiz saatler, tarife (tek fiyat ya da üç zamanlı: gündüz 06–17 / puant 17–22 / gece 22–06), araç parametreleri (batarya kWh, şarj verimi, tüketim kWh/100 km), uyarı eşikleri (tek fazlı cihazlar için `phases = 1` dahil), rapor saatleri, saklama süreleri. Bkz. [`config.toml`](config.toml).
- Telegram'dan değiştirilen değerler (`/ayar`, `/tarife`, `/dil`) veritabanında tutulur ve `config.toml`'u ezer.

Varsayılan dil **İngilizce**'dir; Türkçe için `language = "tr"` yazın ya da `/dil tr` gönderin.

---

## Güvenlik modeli

- Bot **yalnızca** `.env`'deki grup kimliğinden (`TELEGRAM_CHAT_ID`) gelen güncellemeleri işler. Özel mesajlar, başka gruplar ve kanallar yanıtsız yok sayılır.
- Birisi botu başka bir sohbete eklerse bot **hemen çıkar** (`my_chat_member` işleyicisi).
- Ayar değiştiren komutlar (`/ayar`, `/tarife`, `/dil`) yalnızca `TELEGRAM_OWNER_ID`'den kabul edilir; grup üyeleri geri kalan her şeyi okuyabilir.
- Bot cihaza karşı **salt okunur**dur: `switch`, `charge_cur_set`, `work_mode` ya da başka bir komut gönderen hiçbir kod yolu yoktur.
- Gizli bilgiler loglara düşmez; kütüphanelerin ayrıntılı logları kapalıdır.
- Dışarıya açık port yok: Telegram'a uzun yoklamayla (long polling), cihaza giden yönde LAN bağlantısıyla ulaşılır; modemde ya da güvenlik duvarında hiçbir şey açmanız gerekmez.
- Linux'ta servis yetkisiz bir kullanıcıyla ve systemd sertleştirmesiyle çalışır (`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`); yalnızca `data/` yazılabilir.
- Bağımlılıklar `requirements.txt`'te sabitlenmiştir.
- [`tests/test_security.py`](tests/test_security.py) yukarıdaki erişim kurallarını doğrular.

Bot token'ını gizli tutun. Sızarsa @BotFather'da `/revoke` ile yenileyip `.env`'i güncelleyin.

---

## Veri, loglar ve saklama süreleri

Her şey tek bir SQLite dosyasında (`data/evsarj.db`, WAL modu):

| Tablo | İçerik | Saklama |
|---|---|---|
| `samples` | her çözülmüş örnek (değişince, en az dakikada bir) | `retention.samples_days` (varsayılan 90 gün) |
| `transitions` | durum/ayar geçişleri | `retention.transitions_months` (12) |
| `events` | gönderilen olay metinleri | `retention.events_months` (24) |
| `sessions`, `segments` | şarj oturumları ve içlerindeki şarj parçaları | süresiz (her biri birkaç yüz bayt) |
| `outbox` | mesaj kuyruğu (yeniden deneme, hız sınırı, gecikmeli teslim) | gönderilenler 30 gün |

Temizlik her gün 03:30'da çalışır (ayda bir `VACUUM`); veritabanı boyutu sınırlı kalır, disk dolmaz. Servis logları **journald**'dedir; referans kurulumda journald 100 MB / 12 ay ile sınırlandırılmıştır (kurulum kılavuzuna bakın). Yedek için `data/evsarj.db`'yi kopyalayın (çalışırken tutarlı kopya: `sqlite3 data/evsarj.db ".backup yedek.db"`).

---

## Araçlar

Proje dizininden, venv'in Python'uyla çalıştırın, örn. `venv/bin/python -m tools.find_device`.

| Araç | Amaç |
|---|---|
| `tools.telegram_ids` | Konuya `/start@bot` yazdıktan sonra grup, konu ve kullanıcı kimliklerini yazdırır |
| `tools.find_device` | Cihazı ağda Device ID ile bulur (anahtar gerekmez) |
| `tools.dump_dps` | Cihazdan tek seferlik çözülmüş DP dökümü |
| `tools.renew_local_key` | Local Key'i Tuya bulutundan yeniden alıp `.env`'i günceller |
| `tools.import_smartlife` | Smart Life "Record" dışa aktarımını (`.xlsx`) oturum tablosuna aktarır |
| `tools.replay` | Bir keşif kaydını durum makinesinden geçirir (testler de bunu kullanır) |

---

## Cihazı nasıl okur

Ölçülerek çıkarılmış tam veri noktası haritası (numara, kod, ölçek, gözlenen değerler ve durum imzaları) **[docs/DP-MAP.md](docs/DP-MAP.md)** dosyasındadır. Öne çıkanlar:

- `work_state` (DP3) referans cihazda yalnızca `charger_free` / `charger_wait` / `charger_charging` gösterdi; bot diğer enum değerlerini de tanır.
- Faz başına gerilim/akım/güç 7 baytlık ham kayıtlarla (DP6/7/8) yaklaşık 6 sn'de bir gelir; toplamı `power_total` (DP9) ile birebir eşleşir.
- Oturum sayacı (DP25) yalnızca çıkarmada ya da cihaz kendi kaydını kapattığında gelir (şarj başladıktan **12 saat** sonra ya da şarjsız 20 saat takılı kalınca). Bot bu yüzden güç ölçümlerini de entegre eder ve iki değeri birlikte gösterir.
- Cihaz çoğu değişikliği kendiliğinden gönderir ama hepsini değil (örn. `charging` bazen güçten geç gelir); bot hem dinler **hem** sorgular (şarjda 20 sn / boşta 60 sn). Smart Life uygulamasının ikinci bağlantısı botu etkilemez.
- Titreme filtreleri gerçek kayıtlardan türetildi: yeniden başlatmada 3 sn `free` + 6 A, çıkarmada 6 sn `switch` titremesi, araç kilidi açılınca 0 A ile "charging". `tests/test_replay.py` bu kaydı regresyon testi olarak kullanır.

---

## Cihazın vermediği veriler

Tahmin yerine dürüstçe belirtilir:

1. **Ömür boyu enerji sayacı yok** — bot oturumlardan (ve içe aktarılan geçmişten) kendi toplamını tutar.
2. **Canlı oturum enerjisi yok** — şarj sırasında enerji güçten hesaplanır; kesin sayaç çıkarmada gelir.
3. **Sıcaklık yok** — sıcaklık uyarısı ve "en yüksek sıcaklık" raporlanamaz.
4. **Kontrol pilotu gerilimi yok** — takılı/çıkarıldı bilgisi `work_state`'ten türetilir.
5. **Batarya yüzdesi yok** — yalnızca verilen enerjiden tahmin, her zaman *tahmin* etiketiyle.
6. **Güç faktörü, frekans ve kaçak akım değeri yok** (kaçak akım yalnızca alarm biti olarak var).
7. Gerilim çözünürlüğü 1 V, akım 0,1 A.

---

## Sorun giderme

| Belirti | Bakılacaklar |
|---|---|
| "🛑 kimlik doğrulama hatası" mesajı | Local Key değişti (cihaz Smart Life'tan silinip yeniden eklendi). `tools.renew_local_key` çalıştırın (Tuya bulut anahtarları ve aktif IoT Core denemesi gerekir), servisi yeniden başlatın. |
| Kurulumdan hemen sonra "📴 Cihaz çevrimdışı" | IP yanlış ya da farklı VLAN. `tools.find_device` cihazı görmeli; UDP 6666/6667/7000 yayınları botun ağına ulaşmalı. |
| Hiç Telegram mesajı gelmiyor | `journalctl -u ev-charger-bot` bakın; token'ı, botun grupta olduğunu ve grup/konu kimliklerini (`tools.telegram_ids`) doğrulayın. |
| Komutlar yanıtlanmıyor | Bot yalnızca yapılandırılan grupta yanıt verir. @BotFather'da gizlilik modu *kapalı* olmalı (`/setprivacy`). |
| Cihazın IP'si değişiyor | Bot Device ID ile yeniden tarar ve çalışmaya devam eder; yine de modemde DHCP rezervasyonu yapın. |
| Enerji değerleri farklı | Cihaz sayacı (DP25) esastır; entegre edilen değer farkıyla birlikte gösterilir. |

Daha fazlası kurulum kılavuzunun sorun giderme bölümünde.

---

## Projeye destek

ev-charger-bot işine yarıyorsa **[GitHub Sponsors üzerinden destek olmayı ❤️](https://github.com/sponsors/haliskilic)** düşünebilirsin — sponsorluklar test donanımını ve projenin bakımına ayrılan zamanı karşılıyor.

GitHub hesabın yoksa **[bir kahve ısmarlayabilirsin ☕](https://buymeacoffee.com/haliskilic)**.

---

## Lisans

ev-charger-bot **çift lisanslıdır**:

- **Açık kaynak — [GNU AGPL-3.0](LICENSE):** kullanmak, incelemek, değiştirmek ve paylaşmak serbesttir. Dağıtırsan ya da değiştirilmiş bir sürümü ağ servisi olarak çalıştırırsan, tüm kaynak kodunu AGPL-3.0 ile sunman gerekir.
- **Ticari lisans:** AGPL-3.0 yükümlülükleri olmadan kapalı kaynak ürün, cihaz ya da SaaS için — bkz. [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) veya **mail@haliskilic.com.tr**.

Kullanılan açık kaynak kütüphaneler kendi lisanslarını korur — bkz. [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

Katkılar memnuniyetle karşılanır! İlk pull request'inde tek seferlik bir [Katkıcı Lisans Sözleşmesi (CLA)](https://gist.github.com/haliskilic/7a7fdcd355f54d1db6943959d7b76823) imzalaman istenir; katkının telif hakkı sende kalır.

Telif © 2026 Halis KILIÇ.
