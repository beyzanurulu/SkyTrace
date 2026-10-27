# Offline mode, end to end

2026-10-27, `SKYTRACE_MODE=offline`, model `ollama_chat/qwen2.5:7b`, embeddings `ollama/bge-m3`, network: **none**, Linux x86_64, GPU: no (CPU). **7 / 7 passed.**

| Step | Result | Time (s) | Notes |
|---|---|---:|---|
| analyze + HTML report | PASS | 0.6 | 2 findings (F001, F002), report 4780 kB |
| documentation search | PASS | 13.5 | top hit https://docs.px4.io/main/en/assembly/vibration_isolation.html (score 0.72) |
| agent (log question) | PASS | 159.1 | verified; tools: get_flight_summary, list_findings |
| agent (docs question) | PASS | 132.9 | verified; tools: get_flight_summary, list_findings, search_docs |
| web API (in process) | PASS | 1.2 | status ok, upload -> 2 findings, UI self-contained |
| internet probe refused | PASS | 0.0 | pypi.org:443 refused by the network guard |
| no other outgoing connection | PASS | 0.0 | nothing else tried to connect |

## Answers

**Bu uçuşta hangi sorunlar tespit edildi?**

Bu uçuşta iki tür uyarı sorunu tespit edildi:

1. F001 (0.162566 - 1.74867 s): GPS horizontal hata yüksek: EPH 3.26 m (limit 3.00) için 1.6 s süre.

2. F002 (3.32192 - 4.81765 s): Yatay açı hata: hedeften 19.9° kadar sapma (limit 10.0°) için 1.5 s süre.

Bu sorunlar, GPS performansı ve uçuş kontrol sisteminin hedefe uyma yetisi hakkında bilgi sağlıyor.

**Titreşimi nasıl azaltırım?**

Titreşimi azaltmak için aşağıdaki adımları izleyebilirsiniz:

1. **Harmonik Kesme Filtresi Kullanma**: Dokümantasyonda belirtilen gibi, harmanik kesme filtresini kullanarak kontrol sinyallerindeki gürültüyü azaltabilirsiniz. Bu, "Preparing for Tuning > Reduce Noisy Control Signals" başlıklı belgede açıklanmaktadır: [Link](https://ardupilot.org/copter/docs/traditional-helicopter-tuning-preparing.html#reduce-noisy-control-signals)

2. **Basit Vibration Fixes**: Dokümantasyonda belirtilen basit adımları uygulayabilirsiniz. Bu adımlar, "Vibration Isolation > Basic Vibration Fixes" başlıklı belgede açıklanmaktadır: [Link](https://docs.px4.io/main/en/assembly/vibration_isolation.html#basic-vibration-fixes)

3. **Motorlarla Vibration Damping**: Dokümantasyonda belirtilen gibi, motorlara küçük bir damper ekleyerek titreşimi azaltabilirsiniz. Bu, "Vibration Damping > Bulb Damper + Ear Plug Vibration Mount > Additional Vibration Reduction Considerations" başlıklı belgede açıklanmaktadır: [Link](https://ardupilot.org/copter/docs/common-vibration-damping.html#additional-vibration-reduction-considerations)

4. **Manuel Tuning**: Dokümantasyonda belirtilen gibi, ATC_RAT_RLL_P ve ATC_RAT_PIT_P katsayısını ayarlayarak titreşimi kontrol edebilirsiniz. Bu, "Manual Tuning Instructions > Pitch and Roll Axes > Tuning the ``ATC_RAT_xxx_D`` and ``ATC_RAT_xxx_P`` gain" başlıklı belgede açıklanmaktadır: [Link](https://ardupilot.org/copter/docs/traditional-helicopter-manual-tuning.html#tuning-the-atc-rat-xxx-d-and-atc-rat-xxx-p-gain)

Bu adımları takip ederek, titreşimi azaltabilir ve daha istikrarlı bir titreşim elde edebilirsiniz.
