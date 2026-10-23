# TEAM-33 · Incident Zero · Day 2 report

**Goal (Checkpoint 3 "Hands" plus the deliverables):** a full loop on at least one incident (diagnose, approve, act, verify, report), a kill switch that works, and all five deliverables in the repository. The Day 2 plan's top priority came first: **fix the three confidently-wrong answers**, because the 30-point hidden test is scored on the same engine.

## 1. Results in one table

| Day 2 requirement | Status | Evidence |
|---|---|---|
| Allowlisted action proposed | ✅ | `actions.py`: restart, flag write, throttle; scale refused on Compose |
| Human approval gate | ✅ | `y/N` prompt. "No" and "no terminal" both mean no. The approver is logged. |
| Dry run | ✅ | Shown before every approval; `--dry-run` never acts |
| Execute, then verify recovery | ✅ live | `currency-stopped` restart and `payment-failure` flag fix both **recovered and verified** (`reports/checkpoint3/`) |
| Roll back and escalate on failure | ✅ tested | Inverse map, plus an offline test of a failed recovery being rolled back |
| Kill switch | ✅ live | Mid-run `touch KILL_SWITCH` stopped the run with 0 actions |
| Incident report | ✅ | `report.md`: diagnosis, evidence, reviewer, action loop, verification, timeline, prevention |
| Action log | ✅ | `action_log.jsonl`: every attempt, refusal and dry run |
| Fewer confidently-wrong answers | ✅ measured | **3 → 0**; *high* band accuracy **50% → 100%** (small sample, `evaluation-note.md`) |
| Five deliverables | ✅ | README, `docs/architecture.png`, `reports/`, `evaluation-note.md`, `team-form.md` |
| Stretch goals | ✅ 4 of 5 | Reviewer agent, calibration table, prevention field, live hallucination demo. Not done: a chat UI (explicitly optional) and incident memory. |

## 2. The fix worth more than every feature

Day 1 got every error-producing fault right and every no-error fault wrong, three times confidently. The causes, and the changes:

- **Fail closed:** a missing baseline is "unknown", never "slow". On Day 1, `accounting` at its normal 15 s was the false lead three times.
- **The twin rule:** with no errors, the root cause is the service that moved most from **its own** normal. Every service is ranked by `deviation_score`.
- **Baselines that survive incidents:** the median of the last 2 h, excluding the last 10 min.
- **Containers judged against their own normal:** CPU spike, memory high or climbing, crashed and restarted, windowed restart loop.
- **Calibration tightened:**
  - high confidence needs two evidence kinds **and** a service among the most-changed;
  - stale evidence doesn't count;
  - a **grounded** reviewer dispute caps confidence at 0.60.
- **An infrastructure consistency check:** a stopped, crashed or looping container seen in the run challenges a diagnosis that names a different service.

## 3. The four safety gates (`docs/architecture.png`)

| Gate | What it does |
|---|---|
| 1 · Reviewer | A second LLM call tries to disprove the diagnosis. Only a dispute naming a better-supported service lowers confidence; speculation is recorded only. |
| 2 · Human approval | Dry run first, then `y/N`; `approved=True` is set in one place only |
| 3 · Allowlist | `actions.py`. Protected: jaeger, prometheus, opensearch, otel-collector, grafana, flagd, flagd-ui, load-generator, and anything outside the demo project. Every call is logged. |
| 4 · Kill switch | Checked every investigation step, before acting, in every execute, and every second of verification |

**The flag statement:** the diagnosis path cannot read feature flags; the action path can only write one, named by the human; no code reads a flag to decide anything.

## 4. Live tests (`reports/checkpoint3/`, `reports/demo/`)

1. **Approve:** currency down, restart, "currency was not reporting; now reporting with error ratio 0.0000". **Recovered and verified.**
2. **Hallucination guard and flag fix:** `trace-9999` rejected live. The human named `paymentFailure`. Deviation 20 → 0, error ratio 1.0 → 0.0. **Recovered and verified.**
3. **Reject:** "rejected by the human: no change was made".
4. **Kill switch:** investigation stopped, **0 actions**.

## 5. Problems found and fixed on Day 2 (in order)

1. **Span metrics froze** after about 3 h, because the collector's Prometheus export failed. The tool now reports `pipeline_warning`, and the pre-flight `--fix` restarts the collector.
2. **`ad`'s CPU-burning threads outlived the `adHighCpu` flag** for hours. The practice reset now restarts services whose faults leave residue behind.
3. **Baselines polluted** by earlier incidents. They now exclude the incident window; a 24 h low-percentile variant was tried and rejected.
4. **`accounting` false lead.** Fixed by failing closed and ranking by deviation.
5. **Victims ranked as "down".** Docker now separates **DOWN** (stopped) from **IDLE** (silent because nothing calls it).
6. **A rounding bug** (0.04 req/s → 0.0) hid a failing service. Rates now keep 4 decimals.
7. **Sparse-traffic latency noise** (a "499×" slowdown). Latency needs ≥ 0.1 req/s and is capped.
8. **Groq HTTP 400 "tool call validation failed"** (a tool named `json`) crashed a run. It's now fed back with the list of real tools.
9. **The reviewer disputed every correct answer** with speculation. Only grounded disputes now count.
10. **The fallback switched on a per-minute burst.** It now switches only on a daily cap, and switches back after the cool-down.
11. **`docker update --cpus 0` doesn't remove a limit** on Docker 29. Reset now uses `--cpus <all VM cores>`.
12. **Kafka showed RESTART_LOOP from its lifetime restart count.** The check is now windowed.
13. **About 3.4k tokens of fixed overhead per call.** The system prompt was condensed by about 40% (every rule kept).
14. **The daily token caps:** 200k per model per day, and an investigation costs 20–35k. Documented as the biggest operational risk.

## 6. What is still open (stated plainly)
- **Measurement:** the final fixes (consistency check, windowed restart loop, condensed prompt) haven't been measured, because both models' daily caps ran out. Run `python run_all.py` once quota allows.
- **The fallback model:** most of the after-sweep ran on `gpt-oss-20b`. With `gpt-oss-120b` the results are expected to be stronger, but that's not yet measured.
- **Kafka incidents:** not measured on Day 2.
- **Rollback limits:** flag fixes can't roll back automatically, and `scale_service` isn't supported on Compose.
- **Stand-ins:** the schema, faultctl and deploy history.
- **Commits:** only Tarun and Devaki have commits so far. The other members must commit and push (`docs/TEAM_SPLIT.md`).

## 7. Commands for tomorrow morning
```
python check_stack.py --fix                 # ALL GREEN
python tests/test_offline.py                # 20 ok
python smoke_test_llm.py                    # PASS (needs quota)
./demo.sh                                   # Checkpoint 3 run (currency-stopped)
./demo.sh payment-failure "" --demo-hallucination
python run_all.py                           # full measurement, when the quota allows
python calibration.py                       # the table for the evaluation note
```
