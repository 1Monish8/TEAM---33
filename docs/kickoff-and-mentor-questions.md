# Kickoff capture and mentor questions

## What the organiser kit actually contained on this laptop

| Expected at kickoff | What we have | Consequence |
|---|---|---|
| JSON output schema | Not received | `schema.json` is provisional, written from the brief. Swap in theirs verbatim, then align field names in `agent.build_diagnosis`. |
| `faultctl` + the 10 practice incident names | Not received | `practice/faultctl.py` is a stand-in: built-in flags through the Flag UI API, plus `docker stop`, a restart loop and a CPU limit for infrastructure faults. 12 practice incidents. |
| Action API spec | Not received | Diagnosis maps onto the slide's remedies: restart / toggle flag / throttle load / scale, or `escalate_to_human`. |
| Deploy history | Not received | `get_deploy_history` is a stand-in built on `docker inspect` (recent starts, stops, restarts, CPU limits). |
| Template repo | `TEAM---33` (this repo) | Code lives here. |
| LLM key + spend limit | Groq key, `openai/gpt-oss-120b` | Spend limit unknown: ask. Tools return capped, summarised JSON, so one investigation is a few thousand tokens. |

## Environment facts verified by hand (see also SETUP_NOTES.md)

- Jaeger 2.21 serves **only** `/jaeger/ui/api/v3/...`. The legacy `/api/traces` path is a 404. The v3 search ignores attribute filters, so errors are filtered client side.
- Span metrics: `traces_span_metrics_calls_total` and `traces_span_metrics_duration_milliseconds_bucket`, with `status_code="STATUS_CODE_ERROR"`.
- Container metrics: `container_uptime_seconds`, `container_cpu_utilization_ratio`, `container_memory_usage_total_bytes`, `container_memory_usage_limit_bytes`. There is no restart counter, so restarts come from uptime resets and `docker inspect`.
- Logs: index `otel-logs-YYYY-MM-DD`; fields `body`, `resource.service.name`, `@timestamp`, `severity.text` / `severity.number`, `traceId`.
- OpenSearch's host port changes on every restart: `config.py` asks `docker compose port` each run.
- Two copies of the demo in folders both named `opentelemetry-demo` share one compose project and recreate each other's containers. Run only one.

## Questions to ask at Checkpoint 0 (write the answers in)

1. Are `feature_flag.*` attributes in traces and logs allowed as evidence, or do they count as reading flag settings? **Until answered, the tool layer strips them**, and also redacts log lines like "Feature Flag … enabled". Answer: ____
2. Code freeze: 14:00 on Day 2 (milestones slide) or 16:30 (deliverables slide)? Answer: ____
3. Teams of 5 vs "all three members must commit": is it every member, whatever the team size? Answer: ____
4. Is the hidden test scored on the JSON fields only, or is the readable report scored too? Answer: ____
5. Does the harness inject and then call our agent, or must the agent detect the incident itself? (We support both: `diagnose(alert)` / CLI, and `agent.py --watch`.) Answer: ____
6. What exactly is the deploy-history source, and does the hidden test use it? Answer: ____
7. Please give us the official schema, faultctl and Action API spec. Answer: ____
