# Incident report ui-20261024-150720

- **Alert:** Latency p95 above threshold on frontend
- **Status:** DIAGNOSED
- **Root cause service:** ad (resource_exhaustion)
- **Confidence:** medium (0.7)
- **Symptom-only services:** frontend-proxy, frontend

## What happened

The ad service is experiencing memory pressure (96% of its limit), which leads to long processing times for GetAds calls, inflating overall request latency observed at the frontend.

## Evidence (every item was returned by a tool in this run)

- `metric-1` ad · p95_latency_ms = 4549.2 @ 2026-10-24T09:37:22Z — ad service p95 latency 4549 ms vs baseline 24.6 ms, highest deviation_score.
- `metric-13` ad · container.memory_high = 96.232 @ 2026-10-24T09:42:30Z — ad container memory at 96% of limit, flagged MEMORY_HIGH.

## Proposed action (needs human approval)

- **Action:** restart_service on `ad`
- **Reason:** Ad service memory usage is at 96% of its limit, causing severe latency (p95 ~4.5 s) and the latency hotspot is in its GetAds call.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** CONFIRMED
- CONFIRMED: the ad service shows the highest deviation_score (50.0) with a massive p95 latency jump (4549 ms vs 24.6 ms baseline) and 96% memory usage, directly linking its resource exhaustion to the observed latency.

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** rejected by the human: no change was made
- **Mode:** interactive
- **Dry run:** Container ad stops and starts (or starts, if it was stopped). Requests to it fail for a few seconds; in-memory state (caches, leaked memory) is cleared.
- **Command:** `docker restart ad`
- **Approved:** no at 2026-10-24T09:50:18Z
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-24T09:50:18Z · rejected by the human restart_service on `ad` · approved=False · rejected by the human

## What would prevent a repeat

Increase memory limit for ad service or add auto‑restart on high memory usage.

## Timeline

- 2026-10-24T09:37:21Z — Alert received: Latency p95 above threshold on frontend
- 2026-10-24T09:46:40Z — Diagnosis submitted after 7 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 7 (get_container_health, get_dependency_health, get_service_health, get_trace, search_logs, search_traces)
- Calibration: confidence capped from 0.86 to 0.70: only 1 evidence kind(s) name ad
