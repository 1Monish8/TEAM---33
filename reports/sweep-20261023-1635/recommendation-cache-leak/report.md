# Incident report recommendation-cache-leak

- **Alert:** Latency p95 above threshold on frontend
- **Status:** DIAGNOSED
- **Root cause service:** cart (dependency_unreachable)
- **Confidence:** high (0.85)
- **Symptom-only services:** frontend, checkout, quote

## What happened

The cart service cannot connect to its Redis (valkey-cart) cache, raising FailedPrecondition errors. These errors surface in quote and checkout flows, inflating overall request latency observed at the frontend.

## Evidence (every item was returned by a tool in this run)

- `trace-2` trace 0058c3159f7fbc23 · cart · POST /oteldemo.CartService/EmptyCart · 4009.5 ms · ERROR · "Status(StatusCode="FailedPrecondition", Detail="Can't access cart storage. System.ApplicationException: Wasn't able to connect to redis
   at cart.cartstore.Val" — Deepest failing span is cart POST /EmptyCart with connection error to Redis.
- `trace-3` trace 56ce11c261072008 · cart · POST /oteldemo.CartService/EmptyCart · 4480.1 ms · ERROR · "Status(StatusCode="FailedPrecondition", Detail="Can't access cart storage. System.ApplicationException: Wasn't able to connect to redis
   at cart.cartstore.Val" — Repeated same failure in another trace, confirming cart issue.
- `log-5` 2026-10-23T11:13:57.0796826Z · cart · Error · "Wasn't able to connect to redis" — Cart logs error 'Wasn't able to connect to redis' matching trace failures.

## Proposed action (needs human approval)

- **Action:** restart_service on `cart`
- **Reason:** Cart service is failing to connect to its Redis cache, causing errors and high latency upstream.

## What would prevent a repeat

Add health checks and circuit breaker for Redis connection in cart service to avoid propagating failures.

## Timeline

- 2026-10-23T11:13:57.0796826Z — Earliest cited log line from cart
- 2026-10-23T11:26:27Z — Alert received: Latency p95 above threshold on frontend
- 2026-10-23T11:29:01Z — Diagnosis submitted after 8 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 8 (get_container_health, get_service_health, list_services, search_logs, search_traces)
