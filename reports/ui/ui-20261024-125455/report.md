# Incident report ui-20261024-125455

- **Alert:** Error rate is elevated on the frontend
- **Status:** DIAGNOSED
- **Root cause service:** currency (service_down)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend, checkout

## What happened

The currency service container has exited, so checkout cannot convert product prices to USD. This causes checkout errors, which propagate to the frontend, raising its error rate.

## Evidence (every item was returned by a tool in this run)

- `metric-6` currency · container.not_running = exited @ 2026-10-24T07:25:58Z — Container health shows currency is NOT_RUNNING (exited).
- `metric-12` currency · container_state = exited @ 2026-10-24T07:28:03Z — Service health marks currency as NOT_REPORTING: DOWN.
- `trace-16` trace 0fe789741840eba9 · checkout · oteldemo.CurrencyService/Convert · 0.2 ms · ERROR · "name resolver error: produced zero addresses" — Deepest failing span is checkout calling CurrencyService/Convert with a name resolver error, indicating the callee is unavailable.

## Proposed action (needs human approval)

- **Action:** restart_service on `currency`
- **Reason:** Currency service container is stopped, causing checkout conversion failures and elevated frontend error rate.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `checkout`) — grounded in the data, confidence lowered
- DISPUTED: checkout's deviation_score (50) far exceeds currency's (10), indicating checkout is the primary abnormal service rather than a downstream effect; better candidate: checkout.

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** recovered and verified: currency was not reporting; now reporting with error ratio 0.0000
- **Mode:** interactive
- **Dry run:** Container currency stops and starts (or starts, if it was stopped). Requests to it fail for a few seconds; in-memory state (caches, leaked memory) is cleared.
- **Command:** `docker restart currency`
- **Approved:** yes, by root at 2026-10-24T07:35:36Z
- **Executed:** ok
- **Verification:** RECOVERED — currency was not reporting; now reporting with error ratio 0.0000
  - check 1: currency was not reporting; now reporting with error ratio 0.0000
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-24T07:35:38Z · remedy restart_service on `currency` · approved=True · ok

## What would prevent a repeat

Configure a health check and auto-restart policy for the currency container to avoid it staying stopped.

## Timeline

- 2026-10-24T07:24:56Z — Alert received: Error rate is elevated on the frontend
- 2026-10-24T07:33:14Z — Diagnosis submitted after 6 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 6 (get_container_health, get_deploy_history, get_service_health, get_trace, search_traces)
- Calibration: confidence capped from 0.85 to 0.70: only 1 evidence kind(s) name currency
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed it with a grounded alternative (checkout, deviation 50.0 vs 10.0 for currency)
