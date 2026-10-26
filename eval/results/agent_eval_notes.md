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
