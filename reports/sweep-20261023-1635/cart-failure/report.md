# Incident report cart-failure

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** cart (dependency_unreachable)
- **Confidence:** medium (0.62)
- **Symptom-only services:** frontend, frontend-proxy

## What happened

The cart service is failing to connect to its Redis (valkey-cart) storage, causing FailedPrecondition errors. These errors propagate up through checkout to the frontend, raising the observed error rate.

## Evidence (every item was returned by a tool in this run)

- `trace-2` trace 1c4b5c441dbdf840 · cart · POST /oteldemo.CartService/EmptyCart · 3223.3 ms · ERROR · "Status(StatusCode="FailedPrecondition", Detail="Can't access cart storage. System.ApplicationException: Wasn't able to connect to redis
   at cart.cartstore.Val" — Deepest failing span is cart POST /EmptyCart with Redis connection error
- `log-5` 2026-10-23T11:12:08.6973152Z · cart · Error · "Wasn't able to connect to redis" — Cart logs report 'Wasn't able to connect to redis'

## Proposed action (needs human approval)

- **Action:** restart_service on `cart`
- **Reason:** Cart service cannot connect to Redis, causing errors that bubble up to frontend

## What would prevent a repeat

Add health checks for Redis connectivity and alert before errors propagate

## Timeline

- 2026-10-23T11:12:08.6973152Z — Earliest cited log line from cart
- 2026-10-23T11:12:22Z — Alert received: Error rate elevated on frontend
- 2026-10-23T11:14:39Z — Diagnosis submitted after 8 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 8 (get_container_health, get_service_health, list_services, search_logs, search_traces)
