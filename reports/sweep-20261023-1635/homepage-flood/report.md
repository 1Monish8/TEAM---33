# Incident report homepage-flood

- **Alert:** Request rate and latency spiking on frontend-proxy
- **Status:** DIAGNOSED
- **Root cause service:** accounting (latency)
- **Confidence:** high (0.85)
- **Symptom-only services:** frontend-proxy

## What happened

The accounting service is experiencing very high processing latency (up to 15 seconds) for order consumption, causing downstream latency spikes observed at the frontend-proxy. No errors are reported, but traces show the accounting span dominates the latency.

## Evidence (every item was returned by a tool in this run)

- `metric-1` accounting · p95_latency_ms = 15000.0 @ 2026-10-23T11:39:22Z — accounting shows SLOW status with p95 latency 15000ms
- `trace-2` trace 295271321d1955b0 · accounting · order-consumed · 5274.2 ms · OK — accounting order-consumed span takes >5s self time, indicating internal slowness

## Proposed action (needs human approval)

- **Action:** restart_service on `accounting`
- **Reason:** accounting service latency is high, likely due to stuck state or DB connection issue

## What would prevent a repeat

Add health checks and auto-restart on prolonged latency, or investigate DB query performance

## Timeline

- 2026-10-23T11:39:21Z — Alert received: Request rate and latency spiking on frontend-proxy
- 2026-10-23T11:40:28Z — Diagnosis submitted after 7 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 7 (get_container_health, get_deploy_history, get_service_health, list_services, search_logs, search_traces)
