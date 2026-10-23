# Incident report demo-payment-failure-001050

- **Alert:** Error rate above 5% on frontend checkout requests
- **Status:** DIAGNOSED
- **Root cause service:** payment (application_error)
- **Confidence:** medium (0.6)
- **Symptom-only services:** checkout, frontend, frontend-proxy

## What happened

The payment service is returning an 'Invalid token' error for checkout requests, causing the checkout endpoint to fail and surface a >5% error rate to users.

## Evidence (every item was returned by a tool in this run)

- `metric-1` checkout · error_ratio = 0.2041 @ 2026-10-23T18:40:52Z — checkout service shows high error ratio (20%) and high latency, indicating failures.
- `trace-8` trace 8ea7bce9efe7a487 · payment · charge · 0.6 ms · ERROR · "Payment request failed. Invalid token. demo.user_context.loyalty_level=gold" — Deepest failing span shows payment charge error with Invalid token.
- `log-7` 2026-10-23T18:42:57.348Z · payment · warn · "Payment request failed. Invalid token. demo.user_context.loyalty_level=gold" — Payment service log repeats the same Invalid token warning.

## Proposed action (needs human approval)

- **Action:** toggle_feature_flag on `payment`
- **Reason:** Payment service is rejecting checkout requests with 'Invalid token', causing checkout failures.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `checkout`)
- DISPUTED: payment’s deviation_score is near zero, indicating normal behavior, while checkout shows a massive deviation and error ratio, suggesting checkout itself (or its upstream) is the real fault | better candidate: checkout

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** recovered and verified: deviation from its own baseline 20.00 -> 0.00 (error ratio 1.0000 -> 0.0000, p95 4.8 -> 3.8 ms)
- **Mode:** interactive
- **Dry run:** Sets flag paymentFailure to 'off'. WRITE-ONLY: the Flag UI API replaces the whole flag document, so every OTHER flag returns to its default. No flag value is read to decide anything.
- **Command:** `POST http://localhost:8080/feature/api/write  (paymentFailure -> off)`
- **Approved:** yes, by taruns at 2026-10-23T18:48:06Z
- **Executed:** ok
- **Verification:** RECOVERED — deviation from its own baseline 20.00 -> 0.00 (error ratio 1.0000 -> 0.0000, p95 4.8 -> 3.8 ms)
  - check 1: deviation from its own baseline 20.00 -> 0.00 (error ratio 1.0000 -> 0.0000, p95 4.8 -> 3.8 ms)
- **Action log (`action_log.jsonl`):** 1 entry for this incident
  - 2026-10-23T18:48:07Z · remedy toggle_feature_flag on `payment` · approved=True · ok

## What would prevent a repeat

Review token validation logic or feature flag controlling token checks in payment service.

## Timeline

- 2026-10-23T18:40:51Z — Alert received: Error rate above 5% on frontend checkout requests
- 2026-10-23T18:42:57.348Z — Earliest cited log line from payment
- 2026-10-23T18:47:05Z — Diagnosis submitted after 5 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 5 (get_container_health, get_service_health, get_trace, search_logs, search_traces)
- Calibration: confidence capped from 0.82 to 0.70: payment is not among the services that moved most from their own baseline (top: checkout, ad, frontend)
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed this diagnosis
