# SITL ile etiketli arıza logu üretme (PX4 + Gazebo)

Amaç: arızayı bilerek enjekte edip **zamanını bildiğimiz** loglar üretmek, sonra
`data/labels/<log_id>.yaml` yazıp `eval/run_eval.py` ile dedektörleri ölçmek.

> Komutlar PX4 v1.14+ ve yeni Gazebo (`gz_*` hedefleri) içindir. PX4 sürümleri
> arasında parametre ve komut adları değişebiliyor; bir komut çalışmazsa
> `failure help` ve [System Failure Injection](https://docs.px4.io/main/en/debug/failure_injection.html)
> sayfasıyla kendi sürümünü kontrol et.

## 1. Kurulum (Ubuntu 22.04)

```bash
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
bash ./PX4-Autopilot/Tools/setup/ubuntu.sh   # bitince oturumu kapatıp aç
cd PX4-Autopilot
make px4_sitl gz_x500                         # quadrotor, Gazebo penceresi açılır
```

Komutlar Gazebo'yu başlatan terminaldeki `pxh>` kabuğuna yazılır.

## 2. Her uçuş için ortak adımlar

```text
pxh> param set SYS_FAILURE_EN 1     # failure komutlarını aç (her açılışta kontrol et)
pxh> commander takeoff
# ~10 s hover (temiz referans), sonra senaryodaki arızayı enjekte et
# ... arızayı ~20-30 s sürdür, sonra geri al (varsa)
pxh> commander land
```

- Log kaydı varsayılan olarak arm'dan disarm'a kadar sürer (`SDLOG_MODE=0`).
- Loglar: `build/px4_sitl_default/rootfs/log/<tarih>/<saat>.ulg`. Dosyayı
  `data/raw/<log_id>.ulg` olarak kopyala (anlamlı bir `log_id` seç, ör. `sitl_gps_01`).
- Her senaryo için **en az bir de temiz uçuş** (arıza yok, `faults: []`) kaydet;
  yanlış alarm (precision) ancak böyle ölçülür.
- Uzun bir görev uçurmak istersen QGroundControl ile basit bir mission yükleyip
  `commander mode auto:mission` kullanabilirsin.

## 3. Senaryolar

| Senaryo | Etiket `type` | Enjeksiyon | Geri alma | Not |
|---|---|---|---|---|
| GPS kaybı | `gps` | `failure gps off` | `failure gps ok` | En güvenilir SITL senaryosu. Araç failsafe'e geçebilir (`COM_POS_FS_*`). |
| Motor arızası | `motors` (ve muhtemelen `attitude`) | `failure motor off -i 1` | – | Quad'da tek motor kaybı genelde düşüş demektir; sürümünde varsa hexa/octa bir SITL modeli daha anlamlı veri verir. Bazı sürümlerde `CA_FAILURE_MODE` gerekir. |
| Batarya düşüşü | `battery` | `param set SIM_BAT_DRAIN 60` (kalkıştan önce) ve `param set SIM_BAT_MIN_PCT 5` | – | Batarya ~60 s'de boşalır; `BAT_LOW_THR`/`BAT_CRIT_THR` geçişleri failsafe üretir. Etiket aralığı: voltajın / `remaining`'in eşik altına indiği andan uçuş sonuna kadar. |
| Yüksek titreşim | `vibration` | `failure accel intermittent` veya `failure accel garbage` | `failure accel ok` | **Gerçek titreşimi temsil etmez**: SITL'de mekanik titreşim yok, bu komutlar sensörü bozar ve EKF'yi düşürebilir. PX4 titreşim eşikleri zaten gerçek loglarla kalibre ediliyor (`eval/calibrate_vibration.py`); titreşim için gerçek uçuş loglarını tercih et. |

Bir uçuşta tek arıza enjekte et; aynı uçuşta birden fazlası etiketlemeyi zorlaştırır.

## 4. Etiket zamanlarını logdan bul

Etiket zamanları **dedektör çıktısından değil**, enjeksiyon komutundan alınmalı;
yoksa dedektörü kendi çıktısıyla ölçmüş oluruz. `failure` komutu logda
`vehicle_command` (komut 420, `VEHICLE_CMD_INJECT_FAILURE`) olarak görünür.
Parametre değişiklikleri (`SIM_BAT_*`) bu yolla görünmez; onlar için arızanın
başladığı anı ilgili sinyalden oku.

```bash
uv run python - data/raw/sitl_gps_01.ulg <<'PY'
import sys
from pyulog import ULog

ulog = ULog(sys.argv[1], ["vehicle_command"])
t0 = ulog.start_timestamp
for d in ulog.data_list:
    for i, cmd in enumerate(d.data["command"]):
        if cmd == 420:  # VEHICLE_CMD_INJECT_FAILURE
            t = (d.data["timestamp"][i] - t0) / 1e6
            unit, kind = d.data["param1"][i], d.data["param2"][i]
            print(f"t={t:.1f} s  unit={unit:g}  type={kind:g}")
PY
```

`param1` arıza birimi (MAVLink `FAILURE_UNIT`: 1 accel, 4 GPS, 100 batarya,
101 motor, ...), `param2` tipi (`FAILURE_TYPE`: 0 ok, 1 off, 3 garbage,
7 intermittent, ...). Çıkan zamanlar SkyTrace'in kullandığı
zaman tabanıyla aynıdır (log başlangıcından itibaren saniye).

- `t_start`: enjeksiyon zamanı.
- `t_end`: geri alma (`failure ... ok`) zamanı; geri alma yoksa iniş / disarm
  zamanı (`skytrace analyze <log> --format json` çıktısındaki events'ten veya
  rapordaki zaman çizelgesinden okunabilir).

Örnek `data/labels/sitl_gps_01.yaml`:

```yaml
source: sitl
faults:
  - type: gps
    t_start: 62.4
    t_end: 92.4
    note: "failure gps off / ok"
```

Şablon: `eval/labels.example.yaml`.

## 5. Değerlendirme

```bash
uv run python eval/run_eval.py                    # data/labels + data/raw
uv run python eval/run_eval.py --iou 0.5          # daha sıkı eşleşme
uv run python eval/run_eval.py --config my.yaml   # farklı eşiklerle
```

Sonuç `eval/results/detector_eval.md`: dedektör başına precision / recall / F1,
kaçırılan arızalar ve yanlış alarmlar. Eşleşme kuralı: aynı dedektör ve
IoU ≥ 0.3; recall etiket başına, precision bulgu başına sayılır.

Hedef (`docs/PLAN.md`): dedektör başına precision ≥ 0.85, recall ≥ 0.80, en az 30 log.
