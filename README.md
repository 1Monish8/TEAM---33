# TEAM-33 · Incident Zero — AI On-Call Engineer

> **Day 1 handover** (filled in at 18:30, see bottom of this block)
> - **Works:** _see evaluation-note.md_
> - **Does not work:** _see evaluation-note.md_
> - **Fix first tomorrow:** _see evaluation-note.md_

An agent that takes a production alert on the OpenTelemetry Demo, investigates it with real telemetry tools (metrics, traces, logs, container health), names the **component that is actually broken** with evidence a tool returned, states a calibrated confidence, and proposes one allowlisted remedy for a human to approve. When it is not confident it **escalates with its findings** instead of guessing.

## Quick start

```bash
# 1. the demo stack in FULL mode (Kafka faults need it). Not `make start`: see SETUP_NOTES.md
cd ../opentelemetry-demo
docker compose --env-file .env --env-file .env.override -f compose.yaml -f compose.full.yaml \
  -f compose.observability.yaml -f compose.extras.yaml up -d --remove-orphans
cd -

# 2. this repo
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
# .env.local (never committed):  export API_KEY="..."  export BASE_URL="https://api.groq.com/openai/v1"
#                                export MODEL_NAME="openai/gpt-oss-120b"
.venv/bin/python smoke_test_llm.py      # proves key + tool calling

# 3. inject a practice fault, wait 2 minutes (metrics lag), investigate
.venv/bin/python practice/faultctl.py inject payment-failure
sleep 120
.venv/bin/python agent.py "Error rate above 5% on frontend"
.venv/bin/python practice/faultctl.py reset
```

Output: schema-valid JSON on stdout, and `runs/<incident_id>/` holding `diagnosis.json`, `report.md` and `transcript.jsonl` (every tool call and result = the action log).

| Command | What it does |
|---|---|
| `python agent.py "<alert>" [--incident-id X] [--out DIR]` | Investigate one alert |
| `python agent.py --watch` | Detect: poll service health, investigate when a threshold fires |
| `python tools.py <tool> [args]` | Run any telemetry tool by hand, no LLM (e.g. `python tools.py search_traces checkout`) |
| `python run_all.py [names…]` | Practice sweep: inject → wait → diagnose → score → reset; writes `reports/sweep-*/scoring-table.md` |
| `python report.py file.json` | Validate a diagnosis against `schema.json` and print the readable report |
| `python tests/test_offline.py` | Offline tests: evidence registry, calibration, deepest-failing-span, flag redaction |
| `touch KILL_SWITCH` | Stops a running investigation at the next loop step (Day 2: also blocks actions) |
| Python harness | `from agent import diagnose; diagnose("alert text") -> dict` |

## How it works

![architecture](docs/architecture.png)

| File | Role |
|---|---|
| `config.py` | The only place URLs, ports and the model name are written down. Discovers OpenSearch's ephemeral port. |
| `tools.py` | Seven telemetry tools and the evidence registry. Pure Python, **no LLM import**. |
| `agent.py` | Tool descriptions, the plain tool-calling loop, the `submit_diagnosis` guard, CLI and `--watch`. |
| `prompts/system_prompt.md` | The investigation policy (the cascade below). |
| `llm.py` | The only file that talks to the LLM (Groq, OpenAI-compatible; reads `.env.local`). |
| `SETUP_NOTES.md` | Verified endpoints, response shapes and gotchas for Jaeger v3, Prometheus, OpenSearch. |
| `schema.json`, `report.py` | Output schema, validation, readable report. |
| `practice/` | Stand-in `faultctl` and the practice incident list. Only `run_all.py` reads the expected answers, for scoring. The agent never imports this folder. |

### Investigation cascade (the agent design)
1. **Metrics first:** `get_service_health` is one cheap query that narrows ~20 services to one or two. A service that **stopped reporting** is down, not healthy.
2. **Errors → traces:** the root cause is the **deepest erroring span whose own children did not error**, not the service the alert named. This is computed in code (`find_deepest_failing_spans`), not left to the model.
3. **Logs last:** logs for that service and time window explain *what* happened.
4. **No errors, but latency or a silent service → container health:** stopped containers, restart loops (uptime resets), memory at the limit, CPU starvation. Then slow-span self-time to see where the time goes.
5. **Converge or escalate.**

### Safety and honesty controls (enforced in code, not in the prompt)
- **Evidence registry:** every item a tool returns gets a ref (`trace-4`, `log-9`, `metric-2`). `submit_diagnosis` rejects any ref that no tool returned in this run, and the model must resubmit. The report embeds the real registry records, so invented evidence cannot reach the output.
- **Calibration:** `high` needs at least two different evidence kinds (trace, log, metric) naming the root-cause service. With only one, confidence is capped at 0.70. `status=diagnosed` with no evidence about the named service is rejected. An escalation is forced to low confidence and `escalate_to_human`.
- **Always valid output:** the run ends only through `submit_diagnosis`, which is validated with `jsonschema`. If the budget runs out, the agent emits an honest automatic escalation instead of crashing.
- **Rule 6 (feature flags):** no tool calls flagd, the Flag UI or the flag file. The flagd services are hidden. Span attributes and log/exception text that mention a feature flag are **redacted in the tool layer**, until a mentor confirms that `feature_flag.*` telemetry is allowed as evidence.
- **Read-only on Day 1:** the agent proposes an action and never executes one. Every action carries `requires_approval: true`.

## Known limitations (honest list)
- `schema.json` is **provisional**: written from the brief before the organisers' schema was available on this laptop. Replace it verbatim when available, then update `build_diagnosis` field names.
- `practice/faultctl.py` is a **stand-in** for the organisers' faultctl (flags through the Flag UI API, plus `docker stop` / restart loop / CPU limit). Its practice list mirrors the brief's examples, not the official 10.
- `get_deploy_history` is a stand-in built on `docker inspect` (recent starts, stops, restarts, CPU limits) until the organisers' deploy-history source is known.
- The Action API, approval gate and recovery verification are Day 2.

## Team

- Tarun
- Devaki
- Sanjana N
See `team-form.md` for who built which part.
