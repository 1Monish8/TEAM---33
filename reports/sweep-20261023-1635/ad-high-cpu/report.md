# Incident report ad-high-cpu

- **Alert:** Latency p95 above threshold on frontend
- **Status:** DIAGNOSED
- **Root cause service:** accounting (latency)
- **Confidence:** high (0.85)
- **Symptom-only services:** frontend, frontend-proxy

## What happened

The accounting service is taking many seconds to process order-consumed requests, likely due to a downstream database slowdown, which inflates overall request latency observed at the frontend.

## Evidence (every item was returned by a tool in this run)

- `metric-1` accounting · p95_latency_ms = 15000.0 @ 2026-10-23T11:33:33Z — accounting shows SLOW status with p95 latency 15000 ms
- `trace-2` trace 17a814bb1069e443 · accounting · order-consumed · 57363.4 ms · OK — accounting order-consumed span takes ~57 seconds self time, dominating request latency

## Proposed action (needs human approval)

- **Action:** restart_service on `accounting`
- **Reason:** accounting service latency is causing frontend p95 to exceed threshold

## What would prevent a repeat

Add DB query performance monitoring and autoscale accounting service to handle load spikes

## Timeline

- 2026-10-23T11:33:32Z — Alert received: Latency p95 above threshold on frontend
- 2026-10-23T11:34:50Z — Diagnosis submitted after 8 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 8 (get_container_health, get_deploy_history, get_service_health, list_services, search_logs, search_traces)
