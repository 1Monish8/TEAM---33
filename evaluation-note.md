# Evaluation note: what our agent gets right and wrong, and why

All numbers come from our own practice sweeps (`run_all.py`): inject a fault, wait 120 s, run the agent (diagnosis only), score its answer against the expected service, reset. Each agent run's raw output is in `reports/sweep-*/<incident>/` (`diagnosis.json`, `report.md`, `transcript.jsonl`, and from Day 2 `verdict.json`).

A run is **correct** only if the agent names an acceptable root-cause service **and** does not escalate. An escalation is counted separately: it isn't wrong, but it isn't a diagnosis either. The number we care about most is **confidently wrong** (high confidence and wrong), because the brief says that's the worst outcome.

> The practice set is our stand-in (`practice/incidents.json`, 12 incidents mirroring the brief's examples), not the organisers' official 10.

## 1. Before: the Day 1 agent

**Sweep `sweep-20261023-1635`** (Day 1 code, 7 of 12 incidents before it was stopped):

| Incident | Expected | Agent said | Confidence | Verdict |
|---|---|---|---|---|
| payment-failure | payment | payment | high 0.85 | ✅ |
| cart-failure | cart | cart | medium 0.62 | ✅ |
| product-catalog-failure | product-catalog | product-catalog | medium 0.60 | ✅ |
| recommendation-cache-leak | recommendation | **cart** | **high 0.85** | ❌ confidently wrong |
| ad-high-cpu | ad | **accounting** | **high 0.85** | ❌ confidently wrong |
| homepage-flood | frontend | **accounting** | **high 0.85** | ❌ confidently wrong |
| payment-unreachable | payment | crash | — | 💥 Groq 429 (rate limit) |

**3 of 7 correct, 3 confidently wrong, 1 crash.** Calibration at that point: when the agent said *high*, it was right **50%** of the time.

**Sweep `sweep-20261023-2309`** (code as of 17:21 Day 1, stopped after 2 to free the stack): payment ✅ high, cart ✅ high. Both were right, but cart took **12 tool calls and 748 s** because every step waited a minute for the rate limit.

### Why it failed: one cause behind all three wrong answers
Every correct answer came from the **error branch**: a fault that throws exceptions, found by the *deepest failing span* rule, which is computed in code. Every wrong answer came from the **no-error branch**: a memory leak, a CPU spike, a traffic flood. Those had no equivalent rule. Reading the transcripts showed:

1. **A false lead from our own tool.** `get_service_health` labelled `accounting` "SLOW" with a citable reference on every run.
   - Accounting is a Kafka batch consumer, and its p95 is *always* about 15 s.
   - The baseline check *failed open*: with no baseline, it called the service slow.
   - The model took the lead in 2 of the 3 failures.
2. **The right answer was there but buried.**
   - In `ad-high-cpu`, `ad` was running at many times its normal CPU, but it sat in a `busiest_cpu` footnote under `containers_with_problems: []`, which reads as "all clear".
   - In `recommendation-cache-leak`, the tool flagged `recommendation` JUST_RESTARTED (an OOM kill), yet the agent cited **stale cart evidence from the previous incident**.
3. **The 429 crash:** each step resends the whole history, and the key allows 8,000 tokens per minute.

## 2. What we changed on Day 2

| Problem | Fix | Where |
|---|---|---|
| Missing baseline counted as "slow" | **Fail closed:** no baseline is *not* evidence; labelled `unknown (no baseline)` | `tools._is_slower_than_baseline` |
| The no-error branch had no rule | **The twin rule:** rank every service by `deviation_score`, how far it moved from its *own* baseline. The top row is the strongest candidate. Fast services get `SLOWER (Nx its own normal)`. | `tools._deviation_score`, prompt |
| Baselines polluted by the incident itself | Baselines are the median of the last **2 h, excluding the last 10 min** | `tools.get_service_health`, `get_container_health` |
| CPU and memory judged against fixed thresholds | `CPU_SPIKE` / `CPU_ABOVE_BASELINE`, `MEMORY_HIGH` / `MEMORY_CLIMBING` against each container's own normal. **Never** an empty problems list next to a 3× outlier. | `tools.get_container_health` |
| Stale evidence from a previous incident | Evidence older than 10 min doesn't count toward confidence and can't support "diagnosed" (also in the late Day 1 code) | `agent.build_diagnosis` |
| Confidently wrong | High confidence also requires the named service to be among the **most-changed** services. A **reviewer** model tries to disprove each diagnosis; a dispute caps confidence at 0.60. | `agent.build_diagnosis`, `agent.review_diagnosis` |
| 429 crash and 12-minute runs | Pacing to the token budget with realistic reservations; old tool results compacted (refs kept); fallback model on a daily cap | `llm.py`, `agent.compact_history` |
| Span metrics froze after ~3 h (a collector export failure) | The tool says so (`pipeline_warning`) instead of looking healthy; pre-flight `--fix` restarts the collector | `tools.py`, `check_stack.py` |
| A fault outlived its reset (adHighCpu threads kept burning CPU for hours) | The practice reset restarts services whose flag faults leave residue | `practice/faultctl.py` |

## 3. After: the Day 2 agent

AFTER_PLACEHOLDER

## 4. Calibration: does our stated confidence match how often we're right?

`python calibration.py` (every sweep, before and after):

CALIBRATION_PLACEHOLDER

## 5. The action loop (Checkpoint 3), tested live

LOOP_PLACEHOLDER

## 6. What still doesn't work, and why
- **Kafka incidents** (`kafka-queue-problems`): consumer lag isn't a metric our tools read, so the agent depends on fraud-detection and accounting traces. This is our weakest class.
- **No allowlisted fix for some faults:** CPU starvation by an external limit, a restart loop driven from outside, and flag-driven faults that return after a restart. Verification honestly reports *not recovered* and the agent escalates.
- **Flag fixes can't be rolled back automatically**, because restoring the previous variant would require reading flag state, which we never do.
- **Baselines can be fooled by a fault that has run for hours** (it becomes "normal"). We saw this when adHighCpu's threads survived their flag.
- **The schema, faultctl and deploy history are stand-ins** until the organisers' versions are known.
