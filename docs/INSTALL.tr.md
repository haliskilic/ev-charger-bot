# Kurulum kılavuzu (Türkçe)

**🌐 [English](INSTALL.en.md) · [Türkçe](INSTALL.tr.md)**

Bu kılavuz hiç deneyimi olmayanlar için yazıldı. Baştan sona sırayla izleyin: **Bölüm A** (cihaz anahtarları) ve **Bölüm B** (Telegram) her platformda aynıdır; sonra **Bölüm C**'deki platformlardan **yalnızca birini** yapın; **Bölüm D** ile ilk çalıştırma kontrollerini bitirin.

Süre: ilk seferde yaklaşık 45–60 dakika.

---

## Sonunda elinizde ne olacak

```
┌──────────────┐   Wi-Fi/LAN (yerel, port 6668)   ┌──────────────────────┐   HTTPS   ┌──────────┐
│ Şarj cihazı  │ ◄──────────────────────────────► │  ev-charger-bot      │ ────────► │ Telegram │
│ (Tuya/Smart  │   salt okunur: durum + heartbeat  │  Python + SQLite     │           │  grup    │
│   Life)      │                                   │  Windows/Linux/Pi/LXC│           │  konusu  │
└──────────────┘                                   └──────────────────────┘           └──────────┘
```

`.env` dosyası için dört bilgi gerekir:

| Değer | Nereden gelir |
|---|---|
| `TUYA_DEVICE_ID`, `TUYA_DEVICE_IP`, `TUYA_VERSION` | Ağ taraması (`python -m tinytuya scan`) — Bölüm A |
| `TUYA_LOCAL_KEY` | Tuya geliştirici platformu (bir kez) — Bölüm A |
| `TELEGRAM_BOT_TOKEN` | @BotFather — Bölüm B |
| `TELEGRAM_CHAT_ID`, `TELEGRAM_THREAD_ID`, `TELEGRAM_OWNER_ID` | `tools.telegram_ids` — Bölüm B |

---

## Bölüm A — Cihaz: Device ID, IP, protokol sürümü ve Local Key

### A1. Ön koşullar
1. Şarj cihazı telefonunuzdaki **Smart Life** (ya da **Tuya Smart**) uygulamasına eklenmiş ve *çevrimiçi* görünüyor.
2. Botun çalışacağı bilgisayar, cihazla **aynı Wi-Fi/LAN**'da (aynı modem, aynı VLAN). Misafir ağları cihazlar arası trafiği genellikle engeller; kullanmayın.
3. Modemde şarj cihazına sabit IP ayırın (DHCP rezervasyonu / "static lease"). Bot IP değişirse cihazı yeniden bulur ama sabit IP her seferinde birkaç dakikalık "çevrimdışı" yaşanmasını önler.

### A2. Device ID, IP ve sürümü bulma (hesap gerekmez)
Bölüm C'de Python ve proje kurulduktan sonra (buraya geri dönebilirsiniz) proje klasöründe:

```
venv/bin/python -m tinytuya scan          # Windows: venv\Scripts\python -m tinytuya scan
```

~20 sn sonra ağdaki tüm Tuya cihazlarını listeler, örn.:

```
Unknown v3.4 Device   Product ID = bkxxxxxxxxxxxxxx  [Valid Broadcast]:
    Address = 192.168.1.129   Device ID = bfd8xxxxxxxxxxxxxxxxxx   Version = 3.4
```

**Device ID**, **Address (IP)** ve **Version** (3.3, 3.4 ya da 3.5) değerlerini not edin. Hiçbir şey bulunmazsa Sorun giderme'ye bakın.

> Device ID için alternatif: Smart Life → cihazı açın → sağ üstteki kalem → **Cihaz Bilgisi** → *Device ID*.

### A3. Tuya geliştirici hesabı (Local Key için)
Local Key, uygulamanın cihazla yerel ağda konuşurken kullandığı şifreleme anahtarıdır; Tuya bunu yalnızca geliştirici platformu üzerinden verir.

1. **https://iot.tuya.com** → **Sign Up**. Mümkünse Smart Life hesabınızla aynı e-postayı kullanın (zorunlu değil). Ülkenizi seçin.
2. Giriş yapın; anket çıkarsa geçebilirsiniz.
3. Sol menü **Cloud → Development** → sağ üst **Create Cloud Project**:
   - *Project Name*: `ev-charger-bot`
   - *Industry*: **Smart Home** · *Development Method*: **Smart Home**
   - *Data Center*: bölgenize uygun olan — Avrupa/Türkiye için **Central Europe**, Amerika için **Western America**, **India**, **China** … (cihaz sonra listede görünmezse *Project → Overview → Data Center* altından değiştirin).
   - **Create**.
4. Açılan *Configuration Wizard*'da **IoT Core** ve **Authorization Token Management** seçili kalsın; **Authorize**.
5. İleride *"IoT Core service subscription has expired"* hatası alırsanız **Cloud → Cloud Services → IoT Core → Free Trial** (ya da *My Services → IoT Core → Extend Trial Period*) yolunu izleyin, kısa formu ("Personal home automation, local control of my own device") doldurup gönderin. Deneme ücretsizdir; yalnızca buluta yeniden ihtiyaç duyduğunuzda (örn. Local Key yenileme) uzatmanız gerekir. Bot kendisi bulutu hiç kullanmaz.

### A4. Smart Life hesabını bağlama
1. Projeyi açın → **Devices** sekmesi → **Link App Account** (eski arayüzde *Link Tuya App Account*) → **Add App Account**.
2. Bir QR kodu çıkar. Telefonda: Smart Life → **Ben** → sağ üstteki **tarama simgesi** (⊡) → QR'ı okutun → **Girişi onayla**.
3. Cihaz artık *Devices → All Devices* altında görünür. Liste boşsa veri merkezi yanlıştır (A3, 3. madde).

### A5. Access ID / Access Secret
Proje → **Overview** sekmesi → **Authorization Key**: **Access ID/Client ID** ve **Access Secret/Client Secret** değerlerini kopyalayın. Şifre gibi saklayın.

### A6. Local Key'i alma
Şunları `.env`'e yazın (dosyanın yeri Bölüm C'de): `TUYA_ACCESS_ID`, `TUYA_ACCESS_SECRET`, `TUYA_REGION` (Central Europe için `eu`; `us`, `in`, `cn`) ve `TUYA_DEVICE_ID`. Sonra:

```
venv/bin/python -m tools.renew_local_key      # Windows: venv\Scripts\python -m tools.renew_local_key
```

`TUYA_LOCAL_KEY=...` satırını `.env`'e yazar. (Eşdeğer alternatif: `python -m tinytuya wizard`; tüm cihazlarınızı ve anahtarlarını `devices.json`'a da kaydeder.)

> **Local Key değişir**: cihazı uygulamadan silip yeniden eklerseniz anahtar değişir. O zaman `tools.renew_local_key`'i yeniden çalıştırıp botu yeniden başlatmanız yeter. Bot bunun gerektiğini Telegram'dan bildirir ("kimlik doğrulama hatası").

---

## Bölüm B — Telegram botu, grup ve kimlikler

### B1. Botu oluşturma
1. Telegram'da **@BotFather** → `/newbot`.
2. *Name*: örn. `EV Şarj Botu` (serbest metin). *Username*: `bot` ile bitmeli, örn. `leon_ev_sarj_bot`.
3. BotFather **token**'ı verir (`123456789:AAE…`). `.env`'e `TELEGRAM_BOT_TOKEN` olarak yazın. Kimseyle paylaşmayın.
4. Yine BotFather'da: `/setprivacy` → botunuzu seçin → **Disable**. (Aksi halde bot konulu gruplarda tüm mesajları göremez.)

### B2. Grup ve konu
1. Bir Telegram **grubu** oluşturun (ya da mevcut özel bir grubu kullanın). Önerilen: grup ayarları → **Konular** açık, sonra *EV-Charger* gibi bir konu açın. (Konusuz düz grup da çalışır.)
2. Grup → **Üye ekle** → botunuzu ekleyin. Yanıtlar gelmezse botu **yönetici** de yapın (bazı konulu gruplarda gerekir).
3. Hedef konuyu açıp şunu gönderin: `/start@leon_ev_sarj_bot` (kendi botunuzun adı).

### B3. Kimlikleri okuma
Bot servisi **henüz çalışmıyorken** (Telegram'ı aynı anda tek süreç dinleyebilir):

```
venv/bin/python -m tools.telegram_ids          # Windows: venv\Scripts\python -m tools.telegram_ids
```

Örnek çıktı:
```
chat: -1001234567890  type=supergroup  title='Botlarım'  forum=True
  thread (topic) id: 1234
  from user id: 123456789 (Your Name)  text='/start@leon_ev_sarj_bot'
```

`.env`'e yazın: `TELEGRAM_CHAT_ID=-1001234567890`, `TELEGRAM_THREAD_ID=1234` (*General* konusu ya da konusuz grup için boş bırakın), `TELEGRAM_OWNER_ID=123456789` (kendi kimliğiniz; ayarları yalnızca bu kullanıcı değiştirebilir).

---

## Bölüm C — Platformunuza kurulum

Birini seçin: [Windows](#c1-windows-10--11) · [Ubuntu](#c2-ubuntu-2204--2404-masaüstü-ya-da-sunucu) · [Raspberry Pi](#c3-raspberry-pi-os) · [Proxmox LXC](#c4-proxmox-ve-lxc-konteyneri)

### Ortak `.env` başvurusu
```
TUYA_ACCESS_ID=          # Bölüm A5 (yalnızca Local Key almak/yenilemek için)
TUYA_ACCESS_SECRET=
TUYA_REGION=eu
TUYA_DEVICE_ID=          # Bölüm A2
TUYA_DEVICE_IP=192.168.1.129
TUYA_VERSION=3.4
TUYA_LOCAL_KEY=          # Bölüm A6 (tools.renew_local_key yazar)
TELEGRAM_BOT_TOKEN=      # Bölüm B1
TELEGRAM_CHAT_ID=-100…   # Bölüm B3
TELEGRAM_THREAD_ID=      # Bölüm B3 (boş = General)
TELEGRAM_OWNER_ID=       # Bölüm B3
```
`config.toml` dil, fiyat, araç verileri ve aralıkları tutar; herhangi bir düzenleyiciyle açın, her satır açıklamalıdır. Türkçe mesajlar için `language = "tr"` yazın.

---

### C1. Windows 10 / 11

1. **Python kurun**: https://www.python.org/downloads/windows/ → *Download Python 3.12.x* (64-bit). Kurulumda *Install Now*'dan önce **"Add python.exe to PATH" kutusunu işaretleyin**.
2. **Projeyi indirin**: https://github.com/haliskilic/ev-charger-bot → yeşil **Code** → **Download ZIP**. `C:\ev-charger-bot` klasörüne çıkarın (`C:\ev-charger-bot\requirements.txt` olacak şekilde). (Git varsa: `git clone https://github.com/haliskilic/ev-charger-bot C:\ev-charger-bot`.)
3. **Klasörde terminal açın**: Dosya Gezgini'nde `C:\ev-charger-bot`'a gidin, adres çubuğuna tıklayıp `powershell` yazın, Enter.
4. **Sanal ortam ve bağımlılıklar** (her satırı kopyalayıp Enter'a basın, bitmesini bekleyin):
   ```powershell
   py -3 -m venv venv
   venv\Scripts\pip install -r requirements.txt tzdata
   ```
5. **`.env` oluşturun**: `copy .env.example .env` sonra `notepad .env`. Bölüm A ve B'deki değerleri girin (A2/A6/B3'ü şimdi yapabilirsiniz; komutlar bu PowerShell penceresinde `venv\Scripts\python` ile çalışır). Kaydedip Not Defteri'ni kapatın.
6. **Windows Güvenlik Duvarı**: ilk ağ taramasında (`venv\Scripts\python -m tinytuya scan`) güvenlik duvarı sorusu çıkar; **Özel ağlar** için izin verin. Engellendiyse *Windows Güvenliği → Güvenlik Duvarı → Bir uygulamaya izin ver* → `python.exe` için özel ağlarda izin verin.
7. **Deneme çalıştırması**:
   ```powershell
   venv\Scripts\python -m evsarj.main
   ```
   ~10 sn içinde Telegram konusuna *"🔄 Bot yeniden başladı"* gelir. Konuya `/durum` yazın. **Ctrl+C** ile durdurun.
8. **Açılışta otomatik başlatma (Görev Zamanlayıcı)**:
   1. *Win* tuşuna basıp **Görev Zamanlayıcı** yazın, açın → sağ panel **Görev Oluştur…** (*Temel Görev* değil).
   2. *Genel*: Ad `ev-charger-bot`; **Kullanıcı oturum açmış olsa da olmasa da çalıştır** seçin.
   3. *Tetikleyiciler* → **Yeni…** → *Görevi başlat*: **Başlangıçta** → Tamam.
   4. *Eylemler* → **Yeni…** → *Program/betik*: `C:\ev-charger-bot\venv\Scripts\python.exe` · *Bağımsız değişkenler*: `-m evsarj.main` · *Başlangıç yeri*: `C:\ev-charger-bot` → Tamam.
   5. *Koşullar*: **Görevi yalnızca bilgisayar AC gücündeyse başlat** işaretini kaldırın.
   6. *Ayarlar*: **Görev başarısız olursa yeniden başlat: 1 dakika**, *En fazla* **999** deneme; *Görev şu süreden uzun çalışırsa durdur* işaretini kaldırın; *Görev zaten çalışıyorsa*: **Yeni örnek başlatma**.
   7. Tamam → Windows parolanızı girin. Göreve sağ tıklayıp **Çalıştır** ile hemen başlatın. Loglar: zamanlanmış görevin konsolu gizlidir; dosyaya log istiyorsanız *Program/betik* olarak `C:\ev-charger-bot\scripts\run.bat` kullanın (`data\bot.log`'a yazar, 10 MB'ta döndürür).
9. Bilgisayar uyku moduna girmemeli: *Ayarlar → Sistem → Güç → Uyku: Hiçbir zaman* (prize takılıyken).

### C2. Ubuntu 22.04 / 24.04 (masaüstü ya da sunucu)

Terminal açın (Ctrl+Alt+T) ve komutları tek tek çalıştırın.

1. **Sistem paketleri**
   ```bash
   sudo apt update && sudo apt install -y python3 python3-venv python3-pip git sqlite3
   python3 --version        # 3.11 ya da üstü olmalı (22.04'te 3.10 gelir → nota bakın)
   ```
   > Ubuntu 22.04'teki Python 3.10 eskidir. Ya 24.04 kullanın ya da: `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install -y python3.12 python3.12-venv` yapıp aşağıda `python3` yerine `python3.12` yazın.
2. **Servis kullanıcısı ve proje klasörü**
   ```bash
   sudo useradd --system --home-dir /opt/ev-charger-bot --shell /usr/sbin/nologin evsarj
   sudo git clone https://github.com/haliskilic/ev-charger-bot /opt/ev-charger-bot
   cd /opt/ev-charger-bot
   sudo cp .env.example .env
   sudo chown -R evsarj:evsarj /opt/ev-charger-bot && sudo chmod 750 /opt/ev-charger-bot && sudo chmod 600 .env
   ```
3. **Sanal ortam ve bağımlılıklar**
   ```bash
   sudo -u evsarj python3 -m venv venv
   sudo -u evsarj venv/bin/pip install -r requirements.txt
   ```
4. **`.env`'i doldurun**: `sudo nano .env` (Bölüm A ve B; yardımcı araçları `sudo -u evsarj venv/bin/python -m tinytuya scan`, `… -m tools.renew_local_key`, `… -m tools.telegram_ids` şeklinde çalıştırın). Ctrl+O, Enter ile kaydedin, Ctrl+X ile çıkın.
5. **Deneme çalıştırması** (servis kullanıcısıyla):
   ```bash
   sudo -u evsarj venv/bin/python -m evsarj.main
   ```
   Telegram'da *"🔄 Bot yeniden başladı"* gelsin, `/durum` deneyin, sonra Ctrl+C.
6. **systemd servisi** (açılışta başlar, çökünce yeniden başlar, loglar journald'de):
   ```bash
   sudo cp ev-charger-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now ev-charger-bot
   systemctl status ev-charger-bot          # "active (running)" demeli
   journalctl -u ev-charger-bot -f          # canlı log, Ctrl+C ile çıkın
   ```
   `/opt/ev-charger-bot` dışında bir yere kurduysanız önce birim dosyasındaki yolları düzenleyin (`WorkingDirectory`, `Environment=EVSARJ_HOME`, `ExecStart`, `ReadWritePaths`).
7. **Sınırlı loglar** (disk hiç dolmasın diye önerilir):
   ```bash
   sudo mkdir -p /etc/systemd/journald.conf.d
   printf "[Journal]\nSystemMaxUse=100M\nSystemMaxFileSize=10M\nMaxRetentionSec=12month\n" | sudo tee /etc/systemd/journald.conf.d/retention.conf
   sudo systemctl restart systemd-journald
   ```

### C3. Raspberry Pi OS

Denenen yol: Raspberry Pi 3/4/5 ya da Zero 2 W, **Raspberry Pi OS (64-bit) Lite, Bookworm** ya da üstü (Python 3.11+). *Raspberry Pi Imager* ile yazın, imager ayarlarından SSH ve Wi-Fi'ı açın, başlatın, SSH ile bağlanın (`ssh pi@raspberrypi.local`).

1. **C2 (Ubuntu)** adımları 1–7'yi aynen uygulayın; Raspberry Pi OS Debian tabanlıdır, komutlar birebir aynıdır (`python3` zaten 3.11+; PPA gerekmez).
2. Pi'ye özel ipuçları:
   - İyi bir SD kart (A1/A2 sınıfı) ya da USB SSD kullanın; veritabanı dakikada birkaç KB yazar (SD kart için sorun değil), journald logları da 7. adımda aynı nedenle sınırlandırılır.
   - Pi Wi-Fi'daysa güç tasarrufunu kapatın ki cihaza bağlantı düşmesin: `sudo iw dev wlan0 set power_save off` (kalıcı olması için `/etc/rc.local` ya da NetworkManager ayarı `wifi.powersave 2`).
   - Saat dilimi: `sudo raspi-config` → *Localisation Options → Timezone* (ve `config.toml`'da aynı değer).

### C4. Proxmox VE (LXC konteyneri)

Küçük, yetkisiz bir Debian konteyneri oluşturur (1 çekirdek, 512 MB RAM, 4 GB disk); referans kurulum tam olarak böyle çalışır.

1. **Şablon**: Proxmox web arayüzü → node → *local* depolama → **CT Templates** → **Templates** → **debian-13-standard** (ya da debian-12) indirin. (Kabuk: `pveam update && pveam download local debian-13-standard_13.6-1_amd64.tar.zst`.)
2. **Create CT** (sağ üst) şu değerlerle:
   - *General*: CT ID (sıradaki boş), Hostname `ev-charger-bot`, **Unprivileged container ✓**, root şifresi.
   - *Template*: 1. adımdaki Debian şablonu.
   - *Disks*: `local-lvm` (ya da rootdir destekleyen bir depolama) üzerinde 4 GB.
   - *CPU*: 1 çekirdek · *Memory*: 512 MB, swap 512 MB.
   - *Network*: köprü `vmbr0` (LAN'ınızın bağlı olduğu köprü), IPv4 **DHCP** (sonra modemde rezervasyon) ya da LAN'ınızda statik IP.
   - *DNS*: host ayarları. **Start after created** işaretli.
   Kabuk alternatifi (tek satır):
   ```bash
   pct create 103 local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst --hostname ev-charger-bot --unprivileged 1 --cores 1 --memory 512 --swap 512 --rootfs local-lvm:4 --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1 --timezone Europe/Istanbul --start 1
   ```
3. **Konteynere girin**: node → konteyner → **Console**, root ile giriş (ya da host kabuğundan `pct enter 103`). Sonra:
   ```bash
   apt update && apt -y full-upgrade
   apt -y install python3 python3-venv python3-pip git sqlite3 curl
   timedatectl set-timezone Europe/Istanbul
   ```
4. **Kontroller**: `curl -sI https://api.telegram.org | head -1` (Telegram erişilebilir) ve `ping -c2 <cihaz IP>` (aynı LAN). Cihazın UDP yayınları konteynere ulaşmalı: `python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('',6667));s.settimeout(30);print(s.recvfrom(1024)[1])"` her şey aynı ağdaysa 30 sn içinde cihazın IP'sini yazar.
5. Şimdi konteyner içinde **C2 (Ubuntu)** adımları 2–7'yi uygulayın (root olduğunuz için `sudo`'ları atın). Debian 13'te Python 3.13, Debian 12'de 3.11 gelir; ikisi de uygundur.
6. Konteynerde **Start at boot** açık olduğundan (`--onboot 1` / Options → Start at boot) host yeniden başlasa da bot geri gelir.

---

## Bölüm D — İlk çalıştırma kontrolleri

1. **Yeniden başlatma mesajı**: `systemctl restart ev-charger-bot` (Windows'ta görevi yeniden başlatma) sonrası ~10 sn içinde konuya *"🔄 Bot yeniden başladı"* gelir; mesaj cihazın çevrimiçi olup olmadığını söyler.
2. **Komutlar**: konuya `/durum`, `/ham`, `/yardim` yazın. `/ham` DP 3, 4, 9, 10, 14, 18, 23'ü listelemeli (ilk şarjdan sonra 6/7/8/25 de gelir).
3. **Kesinti testi**: şarj cihazının sigortasını 3 dakika kapatın. ~90 sn sonra *"📴 Cihaz çevrimdışı"*, güç gelince *"📶 Cihaz geri geldi"* ve muhtemelen *"♻️ Cihaz yeniden başladı"* beklenir.
4. **Gerçek oturum**: aracı takıp şarj edin. *takıldı → şarj başladı → canlı durum (5 dk'da bir düzenlenir) → ara rapor (30 dk) → tamamlandı → çıkarıldı + oturum özeti* zinciri gelmeli.
5. **Geçmişi içe aktarma** (isteğe bağlı): Smart Life'ta cihazı açın → **Record** → dışa aktarın (paylaşın), `.xlsx`'i bot makinesine kopyalayıp `venv/bin/python -m tools.import_smartlife disaaktarim.xlsx` çalıştırın.
6. **Dil**: `/dil tr` (ya da `en`) ile değiştirin; ya da `config.toml`'da `language`.

---

## Bölüm E — İşletme

| İş | Nasıl |
|---|---|
| Canlı log | Linux: `journalctl -u ev-charger-bot -f` · Windows: `data\bot.log` (`scripts\run.bat` ile başlatıldıysa) |
| Yeniden başlatma | Linux: `sudo systemctl restart ev-charger-bot` · Windows: Görev Zamanlayıcı → sağ tık → Sonlandır, sonra Çalıştır |
| Güncelleme | `cd /opt/ev-charger-bot && sudo -u evsarj git pull && sudo -u evsarj venv/bin/pip install -r requirements.txt && sudo systemctl restart ev-charger-bot` (Windows: yeni ZIP'i klasörün üstüne açın; `.env`, `config.toml`, `data\` korunur) |
| Yedek | `data/evsarj.db`'yi kopyalayın (çalışırken tutarlı kopya: `sqlite3 data/evsarj.db ".backup yedek.db"`), ayrıca `.env` ve `config.toml` |
| Local Key yenileme | `venv/bin/python -m tools.renew_local_key`, sonra yeniden başlatın |
| Fiyat / aralık değiştirme | `config.toml`'u düzenleyip yeniden başlatın ya da Telegram'da `/tarife`, `/ayar` (yalnızca sahibi) |
| Kaldırma | `sudo systemctl disable --now ev-charger-bot && sudo rm /etc/systemd/system/ev-charger-bot.service && sudo rm -rf /opt/ev-charger-bot && sudo userdel evsarj` |

---

## Sorun giderme

**`tinytuya scan` hiçbir şey bulmuyor**
- Bot makinesi ile cihaz aynı LAN/VLAN'da olmalı; misafir Wi-Fi ve "AP izolasyonu" yayınları engeller. Aynı modeme kablolu bağlanmak en basit testtir.
- Windows: `python.exe` için güvenlik duvarında *özel* ağlarda izin verin.
- NAT kullanan Docker/VM ağları yayın almaz; köprülü ağ kullanın (`vmbr0` üzerindeki LXC çalışır).

**"kimlik doğrulama hatası" / `Err 914` / "Check device key or version"**
- `TUYA_LOCAL_KEY` ya da `TUYA_VERSION` yanlış. Anahtarı yeniden alın (`tools.renew_local_key`) ve taramanın yazdığı sürümü kullanın.

**IoT Core "subscription has expired"**
- *Cloud → Cloud Services → IoT Core* altından ücretsiz denemeyi uzatın (A3, 5. madde). Yalnızca Local Key alırken gerekir.

**Bot komutlara yanıt vermiyor**
- `TELEGRAM_CHAT_ID`'yi (negatif; süper gruplarda `-100` ile başlar) ve komutun o grupta yazıldığını kontrol edin. BotFather'da gizlilik modu *kapalı* olmalı. Logda `Forbidden`/`Unauthorized` varsa token yanlış ya da bot gruptan çıkarılmış demektir.

**Mesajlar yanlış konuya düşüyor**
- `TELEGRAM_THREAD_ID`, `tools.telegram_ids`'in verdiği konu kimliği olmalı; *General* için boş bırakın.

**Uygulama çalışıyor ama "Cihaz çevrimdışı"**
- Uygulama buluttan gidiyor olabilir, yerel erişim engelli olabilir. IP'yi (`tools.find_device`) ve cihaza giden TCP **6668** portunu engelleyen bir şey (güvenlik duvarı, VLAN kuralı) olmadığını kontrol edin.

**Saat ya da tarihler yanlış**
- `config.toml`'da `timezone` (örn. `Europe/Istanbul`) ve işletim sistemi saat dilimini ayarlayın; Windows'ta venv'de `tzdata` kurulu olmalı.
