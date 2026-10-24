# Incident report demo-currency-stopped-110953

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** currency (service_down)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend, checkout

## What happened

The currency service container stopped (exited) at 05:37:53, causing checkout’s price‑conversion calls to fail. These failures propagate to the frontend, raising its error rate.

## Evidence (every item was returned by a tool in this run)

- `metric-1` currency · container_state = exited @ 2026-10-24T05:39:58Z — Service health shows currency is NOT_REPORTING: DOWN (container exited) with highest deviation_score.
- `metric-5` currency · container.not_running = exited @ 2026-10-24T05:40:59Z — Container health reports currency state NOT_RUNNING (exited) and memory climbing, confirming the service is down.
- `trace-6` trace d834189d9968c513 · checkout · oteldemo.CurrencyService/Convert · 0.3 ms · ERROR · "name resolver error: produced zero addresses" — Checkout trace’s deepest failing span is a client call to CurrencyService/Convert failing with a name resolver error, indicating the callee (currency) is unavailable.

## Proposed action (needs human approval)

- **Action:** restart_service on `currency`
- **Reason:** Currency service container is exited, causing checkout failures and elevated frontend error rate.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `fraud-detection`) — grounded in the data, confidence lowered
- DISPUTED: the conclusion ignores that fraud-detection deviated far more (score 20) than currency (score 10), making it a stronger root‑cause candidate | better candidate: fraud-detection

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** recovered and verified: currency was not reporting; now reporting with error ratio 0.0000
- **Mode:** interactive
- **Dry run:** Container currency stops and starts (or starts, if it was stopped). Requests to it fail for a few seconds; in-memory state (caches, leaked memory) is cleared.
- **Command:** `docker restart currency`
- **Approved:** yes, by taruns at 2026-10-24T05:49:41Z
- **Executed:** ok
- **Verification:** RECOVERED — currency was not reporting; now reporting with error ratio 0.0000
  - check 1: currency was not reporting; now reporting with error ratio 0.0000
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-24T05:49:42Z · remedy restart_service on `currency` · approved=True · ok

## What would prevent a repeat

Add health‑check monitoring and automatic restart for the currency container to avoid prolonged downtime.

## Timeline

- 2026-10-24T05:39:54Z — Alert received: Error rate elevated on frontend
- 2026-10-24T05:48:20Z — Diagnosis submitted after 7 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 7 (get_container_health, get_deploy_history, get_service_health, search_logs, search_traces)
- Calibration: confidence capped from 0.86 to 0.70: only 1 evidence kind(s) name currency
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed it with a grounded alternative (fraud-detection, deviation 20.0 vs 10.0 for currency)
