# Agent evaluation: `gemini/gemini-3.5-flash`

2026-10-27, log `sample_log_small.ulg`, 11 questions (replay-only ones skipped). Pass = expected tools called, nothing unbacked and the key facts present (skytrace.evaluation.agent_questions). **6 / 11 passed**, median latency 12.2 s.

| Question | Result | Latency (s) | Tools called | Problems |
|---|---|---:|---|---|
| findings_overview | PASS | 21.7 | get_events |  |
| duration | PASS | 5.1 | get_flight_summary |  |
| gps_problem | PASS | 42.8 | list_findings, query_series |  |
| pitch_error_window | PASS | 34.2 | query_series |  |
| battery_min | PASS | 9.1 | query_series, query_series |  |
| flight_modes | PASS | 12.8 | get_events |  |
| takeoff_landing | FAIL | 12.2 |  | RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 9h1m0.189476197s.",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.Help",
        "links": [
          {
            "description": "Learn more about Gemini API quotas",
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
          {
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            "quotaDimensions": {
              "location": "global",
              "model": "gemini-3.6-flash"
            },
            "quotaValue": "20"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.RetryInfo",
        "retryDelay": "32460s"
      }
    ]
  }
}
 |
| vibration_not_checked | FAIL | 2.9 |  | RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h56m34.141895198s.",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.Help",
        "links": [
          {
            "description": "Learn more about Gemini API quotas",
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
          {
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            "quotaDimensions": {
              "model": "gemini-3.6-flash",
              "location": "global"
            },
            "quotaValue": "20"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.RetryInfo",
        "retryDelay": "32194s"
      }
    ]
  }
}
 |
| docs_reduce_vibration | FAIL | 16.4 |  | RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h52m6.069044305s.",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.Help",
        "links": [
          {
            "description": "Learn more about Gemini API quotas",
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
          {
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            "quotaDimensions": {
              "location": "global",
              "model": "gemini-3.6-flash"
            },
            "quotaValue": "20"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.RetryInfo",
        "retryDelay": "31926s"
      }
    ]
  }
}
 |
| docs_fix_gps | FAIL | 6.1 |  | RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h47m39.84487519s.",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.Help",
        "links": [
          {
            "description": "Learn more about Gemini API quotas",
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
          {
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            "quotaDimensions": {
              "location": "global",
              "model": "gemini-3.6-flash"
            },
            "quotaValue": "20"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.RetryInfo",
        "retryDelay": "31659s"
      }
    ]
  }
}
 |
| out_of_scope | FAIL | 10.4 |  | RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h43m9.88373378s.",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.Help",
        "links": [
          {
            "description": "Learn more about Gemini API quotas",
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
          {
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            "quotaDimensions": {
              "location": "global",
              "model": "gemini-3.6-flash"
            },
            "quotaValue": "20"
          }
        ]
      },
      {
        "@type": "type.googleapis.com/google.rpc.RetryInfo",
        "retryDelay": "31389s"
      }
    ]
  }
}
 |

## Answers

**Bu uçuşta hangi sorunlar tespit edildi?**

Bu uçuşta 2 adet uyarı (warn) seviyesinde sorun tespit edilmiştir:  
  
1. **F001 (0.2-1.7 s)**: Yüksek GPS yatay hatası (EPH). EPH değeri 3.26 m'ye ulaşarak 3.00 m eşik değerini aşmış ve 1.6 s sürmüştür.  
2. **F002 (3.3-4.8 s)**: Pitch (yunusma) seti takip edilemedi. Pitch hatası 19.9343° seviyesine ulaşarak 10.0° eşik değerini aşmış ve 1.5 s sürmüştür.  
  
**Kontrol Edilmeyen / Atlanan Testler:**  
- **Titreşim:** `px4_imu_status` için kalibre edilmiş eşik değerleri olmadığından titreşim testi atlanmıştır.  
- **Motorlar:** Motor sayısı kesin olarak bilinmediğinden motor dengesizliği testi atlanmıştır.

**Uçuş ne kadar sürdü?**

Uçuş toplam 6.51379 saniye sürmüştür.

**GPS'te bir sorun var mı?**

Evet, GPS'te bir uyarı (warn) tespiti bulunmaktadır:  
  
* **F001 (0.162566-1.74867 s)**: GPS yatay konum hatası (EPH) 3.26 m değerine ulaşarak 3.0 m eşik değerini aşmış ve 1.5861 s (yaklaşık 1.6 s) sürmüştür.

**3 ile 5. saniyeler arasında en büyük pitch takip hatası ne kadardı ve ne zaman?**

3 ile 5. saniyeler arasında en büyük pitch takip hatası **19.9343°** olarak **3.43924** saniyede gerçekleşmiştir.  
  
Bu durum, F002 (3.3-4.8 s) uyarısı ile tespit edilmiştir.

**Batarya voltajı en düşük kaç volta indi, kalan kapasite ne kadardı?**

Batarya voltajı en düşük **23.3362 V** seviyesine 1.22115. saniyede (t = 1.22115 s) inmiştir.   
  
* En düşük voltajın görüldüğü andaki (t = 1.22115 s) kalan kapasite oranı **0.740081** (%74.0081) seviyesindedir.  
* Tüm uçuş boyunca kalan kapasitenin düştüğü en düşük değer ise 6.32122. saniyede **0.739503** (%73.9503) olarak kaydedilmiştir.

**Drone hangi modda uçtu?**

Drone, -0.088409 s anında geçen **MANUAL** modunda uçmuştur. Uçuş boyunca başka bir mod değişimi olmamıştır.

**Ne zaman kalktı ve ne zaman indi?**

(error) RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {  
  "error": {  
    "code": 429,  
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 9h1m0.189476197s.",  
    "status": "RESOURCE_EXHAUSTED",  
    "details": [  
      {  
        "@type": "type.googleapis.com/google.rpc.Help",  
        "links": [  
          {  
            "description": "Learn more about Gemini API quotas",  
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",  
        "violations": [  
          {  
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",  
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",  
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",  
            "quotaDimensions": {  
              "location": "global",  
              "model": "gemini-3.6-flash"  
            },  
            "quotaValue": "20"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.RetryInfo",  
        "retryDelay": "32460s"  
      }  
    ]  
  }  
}  


**Titreşim seviyesi normal mi?**

(error) RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {  
  "error": {  
    "code": 429,  
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h56m34.141895198s.",  
    "status": "RESOURCE_EXHAUSTED",  
    "details": [  
      {  
        "@type": "type.googleapis.com/google.rpc.Help",  
        "links": [  
          {  
            "description": "Learn more about Gemini API quotas",  
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",  
        "violations": [  
          {  
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",  
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",  
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",  
            "quotaDimensions": {  
              "model": "gemini-3.6-flash",  
              "location": "global"  
            },  
            "quotaValue": "20"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.RetryInfo",  
        "retryDelay": "32194s"  
      }  
    ]  
  }  
}  


**Titreşimi nasıl azaltırım?**

(error) RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {  
  "error": {  
    "code": 429,  
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h52m6.069044305s.",  
    "status": "RESOURCE_EXHAUSTED",  
    "details": [  
      {  
        "@type": "type.googleapis.com/google.rpc.Help",  
        "links": [  
          {  
            "description": "Learn more about Gemini API quotas",  
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",  
        "violations": [  
          {  
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",  
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",  
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",  
            "quotaDimensions": {  
              "location": "global",  
              "model": "gemini-3.6-flash"  
            },  
            "quotaValue": "20"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.RetryInfo",  
        "retryDelay": "31926s"  
      }  
    ]  
  }  
}  


**F001 GPS uyarısı neden olur, nasıl düzeltirim?**

(error) RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {  
  "error": {  
    "code": 429,  
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h47m39.84487519s.",  
    "status": "RESOURCE_EXHAUSTED",  
    "details": [  
      {  
        "@type": "type.googleapis.com/google.rpc.Help",  
        "links": [  
          {  
            "description": "Learn more about Gemini API quotas",  
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",  
        "violations": [  
          {  
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",  
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",  
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",  
            "quotaDimensions": {  
              "location": "global",  
              "model": "gemini-3.6-flash"  
            },  
            "quotaValue": "20"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.RetryInfo",  
        "retryDelay": "31659s"  
      }  
    ]  
  }  
}  


**Yarın İstanbul'da hava nasıl olacak?**

(error) RateLimitError: litellm.RateLimitError: litellm.RateLimitError: geminiException - {  
  "error": {  
    "code": 429,  
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash, description: Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.\nPlease retry in 8h43m9.88373378s.",  
    "status": "RESOURCE_EXHAUSTED",  
    "details": [  
      {  
        "@type": "type.googleapis.com/google.rpc.Help",  
        "links": [  
          {  
            "description": "Learn more about Gemini API quotas",  
            "url": "https://ai.google.dev/gemini-api/docs/rate-limits"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",  
        "violations": [  
          {  
            "description": "Generate content requests per day limit exceeded on Free Tier. See https://ai.google.dev/gemini-api/docs/rate-limits.",  
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",  
            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",  
            "quotaDimensions": {  
              "location": "global",  
              "model": "gemini-3.6-flash"  
            },  
            "quotaValue": "20"  
          }  
        ]  
      },  
      {  
        "@type": "type.googleapis.com/google.rpc.RetryInfo",  
        "retryDelay": "31389s"  
      }  
    ]  
  }  
}  


