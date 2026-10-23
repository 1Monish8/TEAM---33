# Incident report product-catalog-failure

- **Alert:** Error rate elevated on frontend product pages
- **Status:** DIAGNOSED
- **Root cause service:** product-catalog (application_error)
- **Confidence:** medium (0.6)
- **Symptom-only services:** frontend, frontend-proxy, frontend-web

## What happened

The product-catalog service's GetProduct operation is failing, likely due to a recent feature flag change that triggers an exception. This propagates up as errors on the frontend product pages.

## Evidence (every item was returned by a tool in this run)

- `trace-4` trace 8eef8ec4070576e3 · product-catalog · oteldemo.ProductCatalogService/GetProduct · 3.8 ms · ERROR · "[redacted by tool layer: text referenced a feature flag]" — Deepest failing span is product-catalog GetProduct, indicating the error originates there
- `trace-6` trace f17d2750a978b94c · product-catalog · oteldemo.ProductCatalogService/GetProduct · 12.7 ms · ERROR · "[redacted by tool layer: text referenced a feature flag]" — Consistent deepest failing span in product-catalog across multiple traces
- `metric-3` accounting · p95_latency_ms = 15000.0 @ 2026-10-23T11:20:23Z — No resource issues reported for product-catalog, pointing to application logic rather than infra

## Proposed action (needs human approval)

- **Action:** toggle_feature_flag on `product-catalog`
- **Reason:** Feature flag causing exceptions in product-catalog GetProduct calls

## What would prevent a repeat

Ensure feature flag changes are tested and rolled back if they cause errors

## Timeline

- 2026-10-23T11:20:22Z — Alert received: Error rate elevated on frontend product pages
- 2026-10-23T11:21:56Z — Diagnosis submitted after 7 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 7 (get_container_health, get_service_health, search_logs, search_traces)
