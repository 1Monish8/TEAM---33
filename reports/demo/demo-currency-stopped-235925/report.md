# Incident report demo-currency-stopped-235925

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** currency (service_down)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend, checkout

## What happened

The currency microservice is down (container exited), causing checkout's calls to fail. These failures propagate up, raising the error rate observed in the frontend service.

## Evidence (every item was returned by a tool in this run)

- `metric-9` currency · container.not_running = exited @ 2026-10-23T18:32:31Z — Container health shows currency service is NOT_RUNNING (exited).
- `trace-4` trace 81f4f6eac625357e · checkout · oteldemo.CurrencyService/Convert · 0.4 ms · ERROR · "name resolver error: produced zero addresses" — Deepest failing span reports CurrencyService/Convert name resolver error, indicating calls to currency fail.

## Proposed action (needs human approval)

- **Action:** restart_service on `currency`
- **Reason:** Currency service container is exited (NOT_RUNNING), causing checkout failures and elevated frontend error rate.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `payment`)
- DISPUTED: the conclusion ignores that the services with the largest deviation scores are payment and fraud‑detection (both 10.0), while currency isn’t even listed as deviating, suggesting it isn’t the primary fault; better candidate: payment.

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** recovered and verified: currency was not reporting; now reporting with error ratio 0.0000
- **Mode:** interactive
- **Dry run:** Container currency stops and starts (or starts, if it was stopped). Requests to it fail for a few seconds; in-memory state (caches, leaked memory) is cleared.
- **Command:** `docker restart currency`
- **Approved:** yes, by taruns at 2026-10-23T18:33:35Z
- **Executed:** ok
- **Verification:** RECOVERED — currency was not reporting; now reporting with error ratio 0.0000
  - check 1: currency was not reporting; now reporting with error ratio 0.0000
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-23T18:33:35Z · remedy restart_service on `currency` · approved=True · ok

## What would prevent a repeat

Implement health checks and auto-restart for currency service to avoid downtime.

## Timeline

- 2026-10-23T18:29:25Z — Alert received: Error rate elevated on frontend
- 2026-10-23T18:33:34Z — Diagnosis submitted after 4 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 4 (get_container_health, get_service_health, search_traces)
- Calibration: confidence capped from 0.85 to 0.70: only 1 evidence kind(s) name currency
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed this diagnosis
