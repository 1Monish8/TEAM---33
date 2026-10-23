# Incident report payment-failure

- **Alert:** Error rate above 5% on frontend checkout requests
- **Status:** DIAGNOSED
- **Root cause service:** kafka (dependency_unreachable)
- **Confidence:** medium (0.7)
- **Symptom-only services:** frontend, checkout

## What happened

The Kafka broker lost its metadata, making the 'orders' topic unavailable. Accounting cannot consume order messages, causing errors that propagate up to checkout requests, leading to the observed >5% error rate on frontend checkout.

## Evidence (every item was returned by a tool in this run)

- `metric-1` accounting · error_ratio = 0.1111 @ 2026-10-23T10:46:46Z — Accounting shows 11% error rate, highest among services
- `trace-2` trace 604431104d91ff2c · accounting · receive orders · 88.4 ms · ERROR · "Subscribed topic not available: orders: Broker: Unknown topic or partition" — Deepest failing span is accounting receiving orders, error 'Subscribed topic not available'
- `log-4` 2026-10-23T10:43:50.313207805Z · kafka · WARN · "[QuorumController id=1] Performing controller activation. The metadata log appears to be empty. Appending 6 bootstrap record(s) in metadata transaction at metadata.version 4.3-IV0 from bootstrap sourc" — Kafka log indicates controller activation with empty metadata, suggesting topic loss

## Proposed action (needs human approval)

- **Action:** restart_service on `kafka`
- **Reason:** Kafka broker lost metadata and the 'orders' topic is unavailable, causing accounting consumption failures

## What would prevent a repeat

Ensure Kafka topic persistence and monitor controller activation; automate topic recreation on startup

## Timeline

- 2026-10-23T10:43:50.313207805Z — Earliest cited log line from kafka
- 2026-10-23T10:46:45Z — Alert received: Error rate above 5% on frontend checkout requests
- 2026-10-23T10:48:14Z — Diagnosis submitted after 5 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 5 (get_container_health, get_service_health, search_logs, search_traces)
- Calibration: confidence capped from 0.86 to 0.70: only 1 evidence kind(s) name kafka
