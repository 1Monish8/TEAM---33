# Incident report demo-currency-stopped-112657

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** currency (service_down)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend, checkout, frontend-proxy

## What happened

The currency microservice container exited, making its gRPC endpoint unreachable. Checkout attempts to convert prices fail, propagating errors to frontend and raising the frontend error rate.

## Evidence (every item was returned by a tool in this run)

- `metric-5` currency · container.not_running = exited @ 2026-10-24T05:58:20Z — Container health shows currency NOT_RUNNING (exited).
- `metric-6` currency · container_state = exited @ 2026-10-24T06:00:33Z — Service health marks currency as NOT_REPORTING: DOWN.
- `trace-10` trace 8249206695bae9c9 · checkout · oteldemo.CurrencyService/Convert · 0.0 ms · ERROR · "name resolver error: produced zero addresses" — Deepest failing span is checkout → CurrencyService/Convert with a name resolver error, indicating the callee is unavailable.
- `metric-8` frontend · error_ratio = 0.1176 @ 2026-10-24T06:00:32Z — Checkout error ratio spiked, matching the currency outage.

## Proposed action (needs human approval)

- **Action:** restart_service on `currency`
- **Reason:** Currency service container is exited, causing checkout failures; restarting will bring it back online.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `checkout`) — grounded in the data, confidence lowered
- DISPUTED: checkout’s deviation_score (10.139) exceeds currency’s and the trace shows a name‑resolver error, indicating a checkout‑side DNS/availability issue rather than the currency container being down | better candidate: checkout

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** rejected by the human: no change was made
- **Mode:** interactive
- **Dry run:** Container currency stops and starts (or starts, if it was stopped). Requests to it fail for a few seconds; in-memory state (caches, leaked memory) is cleared.
- **Command:** `docker restart currency`
- **Approved:** no at 2026-10-24T06:07:59Z
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-24T06:07:59Z · rejected by the human restart_service on `currency` · approved=False · rejected by the human

## What would prevent a repeat

Add health checks and automatic restart policy for the currency container.

## Timeline

- 2026-10-24T05:56:58Z — Alert received: Error rate elevated on frontend
- 2026-10-24T06:06:45Z — Diagnosis submitted after 6 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 6 (get_container_health, get_deploy_history, get_service_health, search_logs, search_traces)
- Calibration: confidence capped from 0.88 to 0.70: only 1 evidence kind(s) name currency
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed it with a grounded alternative (checkout, deviation 10.139 vs 10.0 for currency)
