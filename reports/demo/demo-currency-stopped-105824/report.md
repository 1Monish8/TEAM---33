# Incident report demo-currency-stopped-105824

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** currency (service_down)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend, frontend-proxy

## What happened

The currency service container has stopped (exited), causing DNS lookup failures for the frontend service. This results in a high error rate observed on the frontend. Users experience failed API requests when the frontend tries to call currency.

## Evidence (every item was returned by a tool in this run)

- `metric-1` currency · container_state = exited @ 2026-10-24T05:28:30Z — Service health shows currency is NOT_REPORTING: DOWN with high deviation_score.
- `metric-13` currency · container.not_running = exited @ 2026-10-24T05:30:40Z — Container health reports currency NOT_RUNNING (exited).
- `trace-7` trace ab4a8248a8b66588 · frontend · dns.lookup · 33.4 ms · ERROR · "getaddrinfo ENOTFOUND currency" — Traces from frontend show deepest failing span DNS lookup ENOTFOUND currency (dns_failure).

## Proposed action (needs human approval)

- **Action:** restart_service on `currency`
- **Reason:** Currency service container is stopped, causing DNS lookup failures in frontend and elevated error rate.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `payment`) — grounded in the data, confidence lowered
- DISPUTED: the payment service has a significantly higher deviation_score (14.118) than currency, indicating it deviated more from its baseline and is a more likely root cause, with currency possibly downstream; better candidate: payment.

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** recovered and verified: currency was not reporting; now reporting with error ratio 0.0000
- **Mode:** interactive
- **Dry run:** Container currency stops and starts (or starts, if it was stopped). Requests to it fail for a few seconds; in-memory state (caches, leaked memory) is cleared.
- **Command:** `docker restart currency`
- **Approved:** yes, by taruns at 2026-10-24T05:34:35Z
- **Executed:** ok
- **Verification:** RECOVERED — currency was not reporting; now reporting with error ratio 0.0000
  - check 1: currency was not reporting; now reporting with error ratio 0.0000
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-24T05:34:36Z · remedy restart_service on `currency` · approved=True · ok

## What would prevent a repeat

Add health checks and auto-restart for currency service to avoid downtime.

## Timeline

- 2026-10-24T05:28:25Z — Alert received: Error rate elevated on frontend
- 2026-10-24T05:33:50Z — Diagnosis submitted after 4 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 4 (get_container_health, get_service_health, search_logs, search_traces)
- Calibration: confidence capped from 0.86 to 0.70: only 1 evidence kind(s) name currency
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed it with a grounded alternative (payment, deviation 14.118 vs 10.0 for currency)
