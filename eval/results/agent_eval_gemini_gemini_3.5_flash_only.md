# Agent evaluation: `gemini/gemini-3.5-flash`

2026-10-27, log `sample_log_small.ulg`, 5 questions (replay-only ones skipped). Pass = expected tools called, nothing unbacked and the key facts present (skytrace.evaluation.agent_questions). **5 / 5 passed**, median latency 14.6 s.

| Question | Result | Latency (s) | Tools called | Problems |
|---|---|---:|---|---|
| takeoff_landing | PASS | 14.4 | get_events |  |
| vibration_not_checked | PASS | 43.3 | query_series, search_docs, search_docs |  |
| docs_reduce_vibration | PASS | 15.9 |  |  |
| docs_fix_gps | PASS | 14.6 | search_docs, query_series |  |
| out_of_scope | PASS | 6.0 |  |  |

## Answers

**Ne zaman kalktı ve ne zaman indi?**

Uçuş günlüğündeki olay verilerine göre:  
  
* **Kalkış (Takeoff):** Log başlangıcından **2.36469. saniyede** gerçekleşmiştir.  
* **İniş (Landing):** Log başlangıcından **3.51336. saniyede** gerçekleşmiştir.  
  
*(Ek bilgi: Araç -0.088409 s anında motorlarını çalıştırmış (armed) ve 5.52065 s anında motorlarını kapatmıştır (disarmed).)*

**Titreşim seviyesi normal mi?**

`px4_imu_status` kaynağı için kalibre edilmiş eşik değerleri bulunmadığından otomatik titreşim seviyesi kontrolü **atlanmıştır (skipped check)**. Bu durum titreşim seviyesinin "normal" veya "sorunsuz" olduğu anlamına gelmez, yalnızca otomatik eşik kontrolünün yapılmadığını gösterir.  
  
Logtaki titreşim verilerinin istatistikleri şu şekildedir:  
  
- **accel_vib_metric**: Ortalama 0.000680383, min 0.000609591, maks 0.000738357 (t = 4.96429 s)  
- **vib_x**: Ortalama 0.0239896 m/s², min 0.0075707 m/s², maks 0.0320932 m/s² (t = 5.21358 s)  
- **vib_y**: Ortalama 0.0280055 m/s², min 0.0153475 m/s², maks 0.036854 m/s² (t = 5.11582 s)  
- **vib_z**: Ortalama 0.0408031 m/s², min 0.00223412 m/s², maks 0.0583105 m/s² (t = 0.335353 s)  
  
Titreşim analizi ve düzeltme yöntemleri hakkında detaylı kılavuz için [PX4 Vibration Isolation Documentation](https://docs.px4.io/main/en/assembly/vibration_isolation.html#vibration-analysis) sayfasını inceleyebilirsiniz.

**Titreşimi nasıl azaltırım?**

Bu logda `px4_imu_status` için kalibre edilmiş eşik değerleri bulunmadığından titreşim seviyesi kontrolü atlanmıştır (*vibration: no calibrated thresholds for px4_imu_status*).  
  
Dokümantasyon önerilerine göre titreşimi azaltmak için izlenebilecek adımlar şunlardır:  
  
### 1. Mekanik Önlemler (Öncelikli)  
* **Parçaları Sabitleyin:** İniş takımı, GPS direği ve gövde üzerindeki tüm bileşenlerin sıkıca sabitlendiğinden emin olun (https://docs.px4.io/main/en/assembly/vibration_isolation.html#basic-vibration-fixes).  
* **Pervane ve Motor Balansı:** Dengelenmiş pervaneler ve kaliteli motor/ESC bileşenleri kullanın (https://docs.px4.io/main/en/assembly/vibration_isolation.html#basic-vibration-fixes). Gerekirse motor gövdesine kelepçe/bant veya sıcak silikon ekleyerek motor balansını ayarlayın (https://ardupilot.org/copter/docs/common-vibration-damping.html#additional-vibration-reduction-considerations).  
* **Titreşim Sönümleyici Montaj:** Otopilot montajında titreşim izolasyon süngerleri veya sönümleme mekanizmaları kullanın (https://docs.px4.io/main/en/assembly/vibration_isolation.html#basic-vibration-fixes).  
  
### 2. Yazılımsal Önlemler  
* Kaynakta mekanik çözümler uygulandıktan sonra, kontrol sinyallerindeki gürültüyü engellemek için dinamik çentik filtresi (harmonic notch filter) veya yazılımsal filtre ayarlarını yapılandırın (https://ardupilot.org/copter/docs/traditional-helicopter-tuning-preparing.html#reduce-noisy-control-signals, https://docs.px4.io/main/en/assembly/vibration_isolation.html#basic-vibration-fixes).

**F001 GPS uyarısı neden olur, nasıl düzeltirim?**

**F001** uyarısı (0.16 - 1.75 s aralığında), GPS yatay konum hatası tahmini olan EPH değerinin **3.26 m** ile kabul edilebilir üst eşik olan **3.00 m** değerini aşması nedeniyle tetiklenmiştir.  
  
### Neden Olur?  
Dokümanlara göre zayıf GPS hassasiyetinin ve yüksek EPH/HDOP değerlerinin temel nedenleri şunlardır:  
* **Sinyal Engelleri ve Yansımalar:** Binalar, ağaçlar veya kapalı/yarı kapalı alanlarda uçuş yapılması GPS uydu sinyallerinin engellenmesine veya yansımasına (multipath) neden olur.  
* **RF / Elektronik Parazit:** Araç üzerindeki telemetri, kamera, ESC veya kablolardan kaynaklanan radyo frekansı parazitleri GPS alıcısını olumsuz etkiler.  
* **Yetersiz Donanım Ayrımı:** GPS anteninin diğer elektronik bileşenlere çok yakın olması veya ekranlamasının yetersiz olması.  
  
### Nasıl Düzeltilir?  
* **Açık Alanda Test Edin:** Uçuş alanında GPS sinyalini engelleyecek yapıların bulunmadığından ve kapalı alanda olmadığınızdan emin olun.  
* **RF Parazitlerini ve Yerleşimi Kontrol Edin:** GPS antenini diğer yüksek akım geçen kablo ve telsiz/telemetri vericilerinden olabildiğince uzağa yerleştirin; shielding (ekranlama) önlemlerini artırın.  
* **GPS Reception/İzolasyon:** GPS modülünün görüş açısını yükseltmek için bir GPS stant/direği kullanın.  
  
**Referans Dokümanlar:**  
* PX4 EKF2 Konum Diverjansı Rehberi: https://docs.px4.io/main/en/advanced_config/tuning_the_ecl_ekf.html#what-should-i-do-if-the-position-estimate-is-diverging  
* ArduPilot GPS Kontrolleri Rehberi: https://ardupilot.org/copter/docs/common-prearm-safety-checks.html#recognising-which-pre-arm-check-has-failed-using-the-gcs

**Yarın İstanbul'da hava nasıl olacak?**

Sadece bu uçuş günlüğüne (log) ilişkin soruları yanıtlayabilirim. Weather/hava durumu gibi günlük dışındaki konular hakkında bilgi veremiyorum.

