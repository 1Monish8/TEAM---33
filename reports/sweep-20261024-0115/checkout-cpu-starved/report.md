# Incident report checkout-cpu-starved

- **Alert:** Latency p95 above threshold on checkout
- **Status:** DIAGNOSED
- **Root cause service:** checkout (resource_exhaustion)
- **Confidence:** high (0.9)

## What happened

The checkout service is running with a CPU limit of 0.03 cores, yet it consumes over 1 core, causing the publish orders step to take ~11s. This slowdown propagates as 15s timeouts in the frontend‑proxy, leading to the observed latency alert. The root cause is the CPU limit on the checkout container.

## Evidence (every item was returned by a tool in this run)

- `metric-8` checkout · p95_latency_ms = 15000.0 @ 2026-10-23T21:11:18Z — checkout p95 latency 15s vs baseline 70ms
- `metric-11` checkout · container.cpu_limited = 0.03 @ 2026-10-23T21:40:05Z — checkout container CPU_LIMITED (0.03 cores) while using 1.163 cores
- `trace-10` trace 0e89089dd9881240 · checkout · publish orders · 11600.3 ms · OK — checkout publish orders hotspot 11.6s

## Proposed action (needs human approval)

- **Action:** restart_service on `checkout`
- **Reason:** Checkout container is CPU‑starved due to a very low CPU limit, causing the publish orders operation to take ~11s and trigger upstream timeouts.

## Reviewer (a second model asked to disprove the diagnosis)

- **Verdict:** CONFIRMED
- 

## What would prevent a repeat

Increase the CPU limit for the checkout container or scale the service.

## Timeline

- 2026-10-23T21:08:13Z — Alert received: Latency p95 above threshold on checkout
- 2026-10-23T21:41:09Z — Diagnosis submitted after 6 tool calls

## Investigation

- Model: openai/gpt-oss-120b, openai/gpt-oss-20b
- Tool calls: 6 (get_container_health, get_service_health, get_trace, search_logs, search_traces)
