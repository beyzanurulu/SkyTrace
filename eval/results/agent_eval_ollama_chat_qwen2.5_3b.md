# Agent evaluation: `ollama_chat/qwen2.5:3b`

2026-10-26, log `sample_log_small.ulg`, 9 questions (replay-only ones skipped). Pass = expected tools called, nothing unbacked and the key facts present (skytrace.evaluation.agent_questions). **4 / 9 passed**, median latency 1.5 s.

| Question | Result | Latency (s) | Tools called | Problems |
|---|---|---:|---|---|
| findings_overview | FAIL | 22.9 | list_findings | missing finding id F001; missing finding id F002 |
| duration | PASS | 1.1 | get_flight_summary |  |
| gps_problem | FAIL | 2.6 | list_findings | missing finding id F001 |
| pitch_error_window | FAIL | 1.8 | query_series | missing key number 19.9343; missing key number 3.43924 |
| battery_min | PASS | 2.3 | query_series |  |
| flight_modes | PASS | 0.9 | get_flight_summary |  |
| takeoff_landing | FAIL | 0.6 |  | tool not called: get_events; missing key number 2.36469; missing key number 3.51336 |
| vibration_not_checked | FAIL | 1.5 |  | none of the key terms ['kalibre', 'kontrol edil', 'calibrat', 'not checked', 'skipped', 'atlan'] |
| out_of_scope | PASS | 0.4 |  |  |

## Answers

**Bu uçuşta hangi sorunlar tespit edildi?**

Bu uçuşta tespit edilen sorunlar şunlar:  
  
1. GPS horizontal hatası: EPH değeri 3.26 m (limit 3.00) olarak tespit edildi. Bu durum 1.6 saniyede devam etti.  
  
2. Attitude hatası: Pitch değeri 19.9343 derece olarak tespit edildi. Bu durum 1.5 saniyede devam etti.

**Uçuş ne kadar sürdü?**

Uçuş 6.51379 saniyede sürdü.

**GPS'te bir sorun var mı?**

GPS hatası var. EPH hatası (GPS horizontal error) 3.26 m (limit 3.00) 1.6 s arasında 1.6 s sürenin içinde mevcuttur. Ayrıca, 19.9° (threshold 10.0°) 1.5 s sürenin içinde, attitudede bir hata var.

**3 ile 5. saniyeler arasında en büyük pitch takip hatası ne kadardı ve ne zaman?**

There was an error. The table 'findings' does not exist. Please check the available tables for the log and try again.

**Batarya voltajı en düşük kaç volta indi, kalan kapasite ne kadardı?**

En düşük batarya voltajı 23.3362 V idi ve kalan kapasite 0.739503'dü.

**Drone hangi modda uçtu?**

Drone uçtu MANUAL modunda.

**Ne zaman kalktı ve ne zaman indi?**

Kalktı 0 saniye oldu ve indi 6.51379 saniye oldu.

**Titreşim seviyesi normal mi?**

Titreşim seviyesi normal değil, çünkü attitudeliklerde 19.9343 dereceye yakın bir hata var. Bu durum 10.0 dereceye yakın bir hata için 1.5 saniye sürdü.

**Yarın İstanbul'da hava nasıl olacak?**

These tools do not provide weather forecasts. Please ask about the log data instead.

