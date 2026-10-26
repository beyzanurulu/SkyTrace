# Q&A agent on local models: notes on `agent_eval_*.md`

Setup: `eval/agent_eval.py`, 9 live questions of `eval/agent_questions.yaml`
(the scripted hallucination case is replay-only) on the fixture log, Ollama on a
laptop (RTX 3050, 4 GB VRAM), temperature 0. Scoring:
`skytrace.evaluation.agent_questions.check_reply` (expected tools called or
prefetched, nothing unbacked, key numbers / ids / terms present).

| Model | Passed | Median latency | Default |
|---|---:|---:|---|
| `ollama_chat/qwen2.5:7b` | **7 / 9** | ~16 s | yes (`agent.model`) |
| `ollama_chat/qwen2.5:3b` | 4 / 9 | ~1.5 s | |

7B (4.7 GB) does not fit the 4 GB GPU completely, hence the latency.

## What changed the result

| Step | 3B | 7B |
|---|---:|---:|
| First run, loose scoring (an empty "no data found" answer passed) | 5 / 9 | 5 / 9 |
| Stricter scoring (key facts required); prompt: always call a tool, retry on errors, answer in the question's language | 3 / 9 | 4 / 9 |
| Summary and findings prefetched into the system message (`agent.prefetch`) | 4 / 9 | **7 / 9** |

## Remaining failures (7B)

- `gps_problem`: drew a plot instead of naming finding F001.
- `battery_min`: invented a remaining capacity of 25 % (the log says 74 %); the
  verification node flagged it, so the user sees the warning.

The verification node caught every invented number seen in these runs (e.g. a
30.5 s duration and a finding F003 that does not exist, from earlier runs).

## Not covered

- One short fixture log only; long logs with many findings are only covered by
  the `prefetch_max_findings` cap, not by a live run.
- No cloud model measured (the local model was chosen for privacy).

## Step 10: documentation search (11 questions)

Index: `skytrace docs build`, 3369 chunks (PX4 1945, ArduPilot 1424), bge-m3,
about 3 min including the clone. Two documentation questions added
(`docs_reduce_vibration`, `docs_fix_gps`). 7B: **8 / 11** in two runs.

- `docs_fix_gps`: passed in both runs; called `search_docs` and cited the
  returned PX4 / ArduPilot pages.
- `docs_reduce_vibration`: failed in both runs; the model answered from its
  own knowledge without calling `search_docs`. In the first run it also wrote
  seven PX4 links that do not exist (e.g. `troubleshooting/motor_balance.html`).
  Since then the verification node checks urls too: a url that no tool
  returned is flagged like an invented number, and the prompt says so.
- `gps_problem`, `battery_min`: the same failures as in step 9, alternating with
  `vibration_not_checked` between runs (model variance, not the index).

Fix (`agent.docs_prefetch_terms`, `agent.docs_prefetch_min_score`): for
how / why / fix questions `search_docs` runs with the question before the model
is asked, if the best passage scores at least 0.5; if the answer then cites none
of the returned pages, the agent appends them. Plain substring matching first
fired on "sa**niye**ler" (pitch question) and on the weather question ("nasıl"),
hence word-start matching and the score gate.

| Run | Result | Failures |
|---|---:|---|
| Prefetch, substring terms, no score gate | 7 / 11 | `gps_problem`, `pitch_error_window` (docs prefetched by mistake), `battery_min`, `docs_reduce_vibration` (used the passages, named the sections, no url) |
| + word-start terms, score gate, appended sources | **9 / 11** | `gps_problem`, `battery_min` (as in step 9) |

The two remaining failures are left as they are: `battery_min`'s invented value
is flagged by the verification node, and `gps_problem` is a missing finding id
in an otherwise correct answer. Both need a stronger model rather than more
prompt tuning on this question set.
