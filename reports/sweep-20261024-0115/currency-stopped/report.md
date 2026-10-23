# Incident report currency-stopped

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** currency (service_down)
- **Confidence:** medium (0.7)
- **Symptom-only services:** frontend, frontend-proxy, frontend-web

## What happened

The currency service container exited, so calls from frontend to get supported currencies fail, raising error rate on frontend. Restarting the currency container will restore functionality.

## Evidence (every item was returned by a tool in this run)

- `metric-1` currency · container_state = exited @ 2026-10-23T20:37:07Z — Currency service marked NOT_REPORTING: DOWN
- `trace-2` trace 892f479f4962ec74 · frontend · oteldemo.CurrencyService/GetSupportedCurrencies · 0.3 ms · ERROR — Deepest failing span is CurrencyService/GetSupportedCurrencies
- `metric-11` currency · container.not_running = exited @ 2026-10-23T20:39:10Z — Currency container state exited

## Proposed action (needs human approval)

- **Action:** restart_service on `currency`
- **Reason:** Currency service container exited, causing frontend errors

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** CONFIRMED
- CONFIRMED: The evidence shows the currency container exited and the deepest failing span is a call to CurrencyService/GetSupportedCurrencies, matching the claimed root cause.

## What would prevent a repeat

Add a restart policy or health check to keep currency service running

## Timeline

- 2026-10-23T20:37:06Z — Alert received: Error rate elevated on frontend
- 2026-10-23T20:40:12Z — Diagnosis submitted after 3 tool calls

## Investigation

- Model: openai/gpt-oss-120b, openai/gpt-oss-20b
- Tool calls: 3 (get_container_health, get_service_health, search_traces)
- Calibration: confidence capped from 0.90 to 0.70: only 1 evidence kind(s) name currency
