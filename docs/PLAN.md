# SkyTrace — Drone Uçuş Logu Analiz Ajanı

> Çalışma adı: **SkyTrace** (istersen değiştir; GitHub/PyPI'da isim müsait mi kontrol et)
> Hedef: Ocak 2027 sonuna kadar canlıda, gerçek kullanıcıların kullandığı açık kaynak bir araç.

---

## 1. Problem ve Değer Önerisi

PX4 / ArduPilot uçuş logları onlarca topic ve binlerce satırdan oluşur. Bir çökme ya da tuhaf davranıştan sonra geliştiriciler logu saatlerce grafik grafik inceler; hangi eşiğin "normal" olduğunu bilmek deneyim ister.

**SkyTrace**, logu yükleyen kullanıcıya:
1. Otomatik **arıza / anomali teşhisi** (ne oldu, ne zaman, ne kadar ciddi),
2. Kanıt grafikleriyle **HTML rapor**,
3. Log hakkında **doğal dilde soru-cevap** (sayılar her zaman logdan, uydurma yok),
4. İnternet olmayan ortamda **tamamen yerel çalışma** (offline mod)

sunar.

**Kullanıcılar:** üniversite İHA takımları, Teknofest ekipleri, PX4/ArduPilot geliştiricileri, hobi pilotları, test mühendisleri.

---

## 2. Kapsam

### MVP (Kasım sonuna kadar) — "olmazsa olmaz"
- [ ] PX4 `.ulg` ayrıştırma (öncelik), ArduPilot `.bin` ayrıştırma (ikinci)
- [ ] İki formatı tek bir **ortak şemaya** çeviren katman
- [ ] 5 kural tabanlı dedektör:
  1. **Yüksek titreşim / IMU clipping**
  2. **GPS sorunları** (fix kaybı, düşük uydu sayısı, yüksek EPH/HDOP)
  3. **Batarya** (yük altında voltaj çökmesi, kritik seviye)
  4. **Attitude takip hatası** (setpoint vs gerçekleşen roll/pitch farkı)
  5. **Motor doygunluğu / dengesizliği** (çıkışların max'a yapışması, tek motorun sürekli yüksek kalması)
- [ ] Olay çıkarımı: mod değişimleri, failsafe, arm/disarm, hata mesajları
- [ ] CLI: `skytrace analyze flight.ulg --out report.html`
- [ ] Etiketli küçük değerlendirme seti (en az 30 log)

### v1 (Ocak sonu) — "canlı ürün"
- [ ] İstatistiksel / ML anomali tespiti (kural dışı bilinmeyen anomaliler)
- [ ] LangGraph soru-cevap ajanı (tool-calling, zaman damgalı cevaplar)
- [ ] PX4 + ArduPilot dokümantasyonu üzerinde RAG (açıklamalara kaynak)
- [ ] Web arayüzü (yükle → rapor → sohbet)
- [ ] **Offline mod**: Ollama ile yerel LLM + yerel embedding + yerel vektör DB
- [ ] PyPI paketi, Docker imajı, canlı demo
- [ ] Değerlendirme raporu (precision/recall, gecikme, yerel vs bulut model karşılaştırması)

### Kapsam dışı (şimdilik)
- Gerçek zamanlı / uçuş sırasında analiz (Teknofest + C++ fazı, Ocak sonrası)
- Kullanıcı hesapları, ödeme
- Sabit kanat ve VTOL'a özel dedektörler (multikopter öncelikli)

---

## 3. Mimari

```
            ┌─────────────┐
 .ulg/.bin ─▶│  Parsers    │  pyulog / pymavlink
            └──────┬──────┘
                   ▼
            ┌─────────────┐
            │ Unified     │  FlightLog: standart DataFrame'ler
            │ Schema      │  (attitude, gps, battery, motors,
            └──────┬──────┘   vibration, events, modes)
                   ▼
     ┌─────────────┴──────────────┐
     ▼                            ▼
┌──────────┐               ┌──────────────┐
│ Rule     │               │ ML Anomaly   │  rolling z-score,
│ Detectors│               │ Detection    │  Isolation Forest
└────┬─────┘               └──────┬───────┘
     └──────────┬─────────────────┘
                ▼
         ┌─────────────┐
         │  Findings   │  severity, t_start, t_end,
         └──────┬──────┘  metrik, değer, eşik, kanıt
        ┌───────┴────────┐
        ▼                ▼
 ┌────────────┐   ┌──────────────────┐
 │ HTML Report│   │ LangGraph Agent  │◀── RAG (PX4/ArduPilot docs)
 │ (Plotly)   │   │ tools: findings, │
 └────────────┘   │ query_series,    │
                  │ plot, search_docs│
                  └────────┬─────────┘
                           ▼
                 FastAPI  ◀──▶  Web UI
```

**Temel kural:** LLM hiçbir sayıyı kendisi üretmez. Tüm sayılar ve zaman damgaları tool çıktısından gelir; cevaplar zaman damgası ve bulgu ID'si ile atıf verir.

### Ortak şema (taslak)
| Tablo | Kolonlar |
|---|---|
| `attitude` | t, roll, pitch, yaw, roll_sp, pitch_sp, yaw_sp |
| `gps` | t, fix_type, satellites, eph, hdop, lat, lon, alt |
| `battery` | t, voltage, current, remaining |
| `motors` | t, m1…mN (normalize 0–1) |
| `vibration` | t, vib_x, vib_y, vib_z, clip_count |
| `position` | t, x, y, z, vx, vy, vz, z_sp |
| `events` | t, kind (mode/failsafe/arm/error), message |

`Finding`: `id, detector, severity (info/warn/critical), t_start, t_end, metric, value, threshold, summary, evidence_plot`

---

## 4. Tech Stack

| Katman | Seçim | Not |
|---|---|---|
| Dil / ortam | Python 3.11, **uv** | hızlı bağımlılık yönetimi |
| Log ayrıştırma | **pyulog** (PX4), **pymavlink** (ArduPilot) | |
| Veri işleme | pandas (+ gerekirse polars), numpy, scipy | |
| ML anomali | scikit-learn (Isolation Forest), rolling z-score | ileride LSTM autoencoder opsiyonel |
| Grafik / rapor | Plotly + Jinja2 → tek dosya HTML | |
| CLI | Typer + Rich | |
| Ajan | **LangGraph** | tool-calling, durum yönetimi |
| LLM (bulut) | LiteLLM üzerinden sağlayıcıdan bağımsız | |
| LLM (offline) | **Ollama** (Qwen2.5 7B / Llama 3.1 8B) | |
| Embedding | bge-m3 veya nomic-embed-text (yerel) | |
| Vektör DB | Qdrant (yerel mod) veya Chroma | |
| Backend | FastAPI | |
| Frontend | MVP: Streamlit → v1: istersen Next.js | hız için Streamlit ile başla |
| Test | pytest, etiketli log seti | |
| Paketleme | PyPI, Docker | |
| Deploy | Hugging Face Spaces (ücretsiz demo) + AWS (Lightsail/EC2 t4g, düşük maliyet) | |
| CI | GitHub Actions (lint, test, release) | ruff, mypy |

---

## 5. Veri

- **PX4 Flight Review** (review.px4.io): binlerce herkese açık gerçek uçuş logu. `flight_review` reposunda toplu indirme scripti var; indirmeden önce kullanım koşullarını kontrol et.
- **ArduPilot**: forumda paylaşılan `.bin` logları, SITL simülasyonuyla kendi üreteceğin loglar.
- **Simülasyon (SITL)**: PX4/ArduPilot SITL + Gazebo ile bilerek arıza enjekte et (GPS kapatma, motor arızası, batarya düşüşü). Etiketli veri için en temiz kaynak.
- **Etiketleme**: her log için `labels.yaml` → hangi arıza, hangi zaman aralığı.

---

## 6. Yol Haritası

| Tarih | Odak | Çıktı |
|---|---|---|
| **19–26 Eki** | Repo kurulumu, PX4 parser, ortak şema | `FlightLog.from_file()` çalışıyor |
| **27 Eki – 2 Kas** | Log indirme scripti, 5 kural dedektörü | Dedektörler + birim testler |
| **3–9 Kas** | HTML rapor, CLI, ArduPilot parser | `skytrace analyze` uçtan uca |
| **10–29 Kas** | ⚠️ ALES dönemi — hafif tempo | Etiketli değerlendirme seti, küçük düzeltmeler |
| **30 Kas – 3 Ara** | ML anomali tespiti | Kural + ML birleşik bulgular |
| **4–6 Ara** | ⚠️ Hackathon | — |
| **7–20 Ara** | LangGraph ajanı + doküman RAG | CLI'da `skytrace chat flight.ulg` |
| **21 Ara – 3 Oca** | FastAPI + web arayüzü, offline mod (Ollama) | Yerel ve bulut modda çalışan uygulama |
| **4–20 Oca** | Değerlendirme raporu, Docker, PyPI, canlı demo | v1.0 yayında |
| **21–31 Oca** | Demo videosu, README, topluluk paylaşımı (PX4/ArduPilot forum, Teknofest ekipleri, LinkedIn) | İlk kullanıcılar |

---

## 7. Başarı Ölçütleri

- Etiketli sette dedektör başına **precision ≥ 0.85, recall ≥ 0.80**
- 50 MB'lık bir log için analiz **< 30 sn**
- Ajan cevaplarında **%100 atıf** (her sayı bir tool çıktısına dayanıyor)
- Offline modda internet bağlantısı olmadan uçtan uca çalışma
- Ocak sonu: canlı demo + PyPI + en az birkaç gerçek dış kullanıcı / issue

---

## 8. Riskler

| Risk | Önlem |
|---|---|
| Etiketli arıza verisi az | SITL ile arıza enjeksiyonu |
| PX4 topic isimleri sürüme göre değişiyor | Parser'da topic eşleme tablosu + fallback |
| Eşikler araca göre değişir | Eşikleri config'den oku, varsayılanları dokümante et |
| LLM halüsinasyonu | Sayılar sadece tool'dan; cevap doğrulama adımı |
| ALES + hackathon zamanı yer | MVP Kasım başına kadar bitmiş olsun |

---

## 9. Repo Yapısı

```
skytrace/
├── src/skytrace/
│   ├── parsers/        # ulog.py, dataflash.py, schema.py
│   ├── detectors/      # vibration.py, gps.py, battery.py, attitude.py, motors.py
│   ├── anomaly/        # ml.py
│   ├── report/         # html.py, templates/
│   ├── agent/          # graph.py, tools.py, rag.py
│   ├── api/            # FastAPI
│   └── cli.py
├── app/                # Streamlit / web UI
├── data/               # (gitignore) raw logs, labels
├── eval/               # değerlendirme scriptleri + sonuçlar
├── tests/
├── docs/PLAN.md
├── Dockerfile
└── pyproject.toml
```
