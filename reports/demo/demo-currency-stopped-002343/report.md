# Incident report demo-currency-stopped-002343

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** currency (service_down)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend, checkout

## What happened

The Currency service container has exited, causing it to be unavailable. Frontend and Checkout services report errors when they attempt to call CurrencyService, leading to elevated error rates on frontend.

## Evidence (every item was returned by a tool in this run)

- `metric-1` currency · container_state = exited @ 2026-10-23T18:53:44Z — Currency service not reporting metrics, marked DOWN.
- `metric-4` currency · container.not_running = exited @ 2026-10-23T18:54:46Z — Container health shows currency container NOT_RUNNING (exited).
- `trace-5` trace 204d324949b5ce7c · checkout · oteldemo.CurrencyService/Convert · 0.4 ms · ERROR · "name resolver error: produced zero addresses" — Checkout trace fails at CurrencyService/Convert, indicating calls to currency fail.
- `trace-6` trace 53ee291e6578e5ed · frontend · oteldemo.CurrencyService/GetSupportedCurrencies · 0.8 ms · ERROR — Frontend trace fails at CurrencyService/GetSupportedCurrencies, confirming downstream errors.

## Proposed action (needs human approval)

- **Action:** restart_service on `currency`
- **Reason:** Currency service container is exited; restarting will bring it back online and stop downstream errors.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `payment`)
- DISPUTED: the conclusion ignores that the payment service deviated far more from its baseline (score 499) than currency, making payment a far more likely root cause | better candidate: payment.

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** rejected by the human: no change was made
- **Mode:** interactive
- **Dry run:** Container currency stops and starts (or starts, if it was stopped). Requests to it fail for a few seconds; in-memory state (caches, leaked memory) is cleared.
- **Command:** `docker restart currency`
- **Approved:** no at 2026-10-23T18:57:53Z
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-23T18:57:53Z · rejected by the human restart_service on `currency` · approved=False · rejected by the human

## What would prevent a repeat

Implement health checks and auto-restart for the currency service to avoid manual downtime.

## Timeline

- 2026-10-23T18:53:43Z — Alert received: Error rate elevated on frontend
- 2026-10-23T18:57:52Z — Diagnosis submitted after 4 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 4 (get_container_health, get_service_health, search_traces)
- Calibration: confidence capped from 0.86 to 0.70: only 1 evidence kind(s) name currency
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed this diagnosis
