# Incident report cart-failure

- **Alert:** Error rate elevated on frontend
- **Status:** DIAGNOSED
- **Root cause service:** valkey-cart (resource_exhaustion)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend

## What happened

The Valkey cache used by the cart service was running out of memory, causing connection errors that bubbled up as frontend errors. Restarting the cache clears the memory pressure and restores connectivity.

## Evidence (every item was returned by a tool in this run)

- `trace-8` trace 1bb96965be4fa748 · cart · POST /oteldemo.CartService/EmptyCart · 5804.8 ms · ERROR · "Status(StatusCode="FailedPrecondition", Detail="Can't access cart storage. System.ApplicationException: Wasn't able to connect to redis
   at cart.cartstore.Val" — deepest failing span shows cart cannot connect to redis
- `metric-7` valkey-cart · container.memory_climbing = 79.883 @ 2026-10-23T20:00:24Z — valkey-cart memory climbing from 64% to 80% of limit

## Proposed action (needs human approval)

- **Action:** restart_service on `valkey-cart`
- **Reason:** valkey-cart memory exhaustion caused connection failures to cart, propagating errors to frontend

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** DISPUTED (better candidate: `checkout`) — grounded in the data, confidence lowered
- DISPUTED: The evidence shows checkout has a deviation_score of 50.0, far exceeding the 0.108 of cart, indicating checkout is the likely source of the issue rather than valkey-cart resource exhaustion. | better candidate: checkout

## What would prevent a repeat

Add memory usage alert and auto‑restart or scale valkey-cart

## Timeline

- 2026-10-23T19:57:18Z — Alert received: Error rate elevated on frontend
- 2026-10-23T20:03:29Z — Diagnosis submitted after 6 tool calls

## Investigation

- Model: openai/gpt-oss-20b
- Tool calls: 6 (get_container_health, get_service_health, search_traces)
- Calibration: confidence capped from 0.90 to 0.70: only 1 evidence kind(s) name valkey-cart
- Calibration: confidence lowered from 0.70 to 0.60: the reviewer disputed it with a grounded alternative (checkout, deviation 50.0 vs None for valkey-cart)
