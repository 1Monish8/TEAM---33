# Incident report cart-failure

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** astronomy-db (dependency_unreachable)
- **Confidence:** medium (0.7)
- **Symptom-only services:** frontend, frontend-proxy, checkout, payment, cart

## What happened

The Redis container (astronomy-db) restarted and was unavailable, causing the cart service to fail when accessing its storage. This failure propagated up through checkout and payment, leading to an elevated error rate observed at the frontend.

## Evidence (every item was returned by a tool in this run)

- `trace-2` trace 83ddd9aa4253ac0a · cart · POST /oteldemo.CartService/EmptyCart · 4244.2 ms · ERROR · "Status(StatusCode="FailedPrecondition", Detail="Can't access cart storage. System.ApplicationException: Wasn't able to connect to redis
   at cart.cartstore.Val" — Deepest failing span is cart POST /EmptyCart with redis connection error.
- `log-7` 2026-10-23T10:20:23.3928347Z · cart · Error · "Wasn't able to connect to redis" — Cart logs report 'Wasn't able to connect to redis'.
- `metric-9` astronomy-db · container.just_restarted = 1.0 @ 2026-10-23T10:21:54Z — Redis container astronomy-db just restarted 36s ago, indicating possible downtime.

## Proposed action (needs human approval)

- **Action:** restart_service on `astronomy-db`
- **Reason:** Redis container (astronomy-db) recently restarted and is unavailable, causing cart service to fail to connect to Redis and propagate errors upstream.

## What would prevent a repeat

Add health checks and automatic restart for the Redis container, and monitor its uptime to prevent brief outages.

## Timeline

- 2026-10-23T10:20:23.3928347Z — Earliest cited log line from cart
- 2026-10-23T10:20:53Z — Alert received: Error rate elevated on frontend
- 2026-10-23T10:22:27Z — Diagnosis submitted after 6 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 6 (get_container_health, get_service_health, search_logs, search_traces)
- Calibration: confidence capped from 0.88 to 0.70: only 1 evidence kind(s) name astronomy-db
