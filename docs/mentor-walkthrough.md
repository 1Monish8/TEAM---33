# TEAM-33 · Mentor walkthrough (about 20 minutes)

How to use this: read it aloud, or speak from the bold lines. Times are cumulative. Keep `docs/flow.png` open on screen. Start the live demo in a second terminal at 0:00 (`./demo.sh`), because it waits 2 minutes for metrics before the agent runs.

---

## 0:00 – 1:00 · Opening

**"We built an AI on-call engineer that names the component that is actually broken, proves it with evidence a tool really returned, says how sure it is, and asks a human before anything changes."**

The brief says a good agent is not the one that always acts: it acts when it has evidence, and says "I am not sure, here is what I found" when it does not. We built every part of the design around that sentence. The rule that matters most:

- the alert names the **symptom** (usually frontend);
- the answer is the **deepest failure** (for example payment).

*(Point at the second terminal.)* The demo has just injected a fault. Metrics lag by up to two minutes, so it waits 120 seconds, then the agent investigates. We'll come back to it.

---

## 1:00 – 3:00 · The problem, and our approach in one breath

The OpenTelemetry Astronomy Shop is about twenty microservices with traces in Jaeger, metrics in Prometheus and logs in OpenSearch. When it breaks, an on-call engineer spends the first hour searching and correlating. That hour is what we automate.

**Our approach is a cascade: cheapest signal first, and each tool chosen from what the last one returned.**

1. **Metrics first.** One Prometheus query covers every service at once and narrows twenty services down to one or two.
2. **If there are errors, traces.** The broken component is the deepest failing span whose own children did not fail.
3. **Then logs** for that service and that time window. The log line usually states the cause in plain English.
4. **If there is only latency, or a service went silent: container health.** Stopped containers, restart loops, OOM kills and CPU starvation are invisible in traces.
5. **Then decide.** If the evidence converges on one component, report it with a confidence. If not, escalate to a human with the findings.

**Why this order?** Starting with traces means guessing which service to look at, which is exactly the guessing we want to remove. Logs come last because traces tell you *where* and logs tell you *what*.

---

## 3:00 – 6:00 · How one run flows (walk the diagram)

*(Point at the left half of `docs/flow.png`.)*

1. **Alert in.** Three entry points:
   - CLI: `python agent.py "Error rate above 5% on frontend"`
   - Watch mode: `--watch` polls service health and starts an investigation when a threshold fires (the "Detect" step).
   - Harness: `diagnose(alert)`, if the scoring harness wants to call us as a function.
2. **`run_investigation` starts** with an empty evidence registry, the system prompt and the alert.
3. **The model picks one tool.** It's Groq's `openai/gpt-oss-120b`, called through the OpenAI-compatible API. We ask it to call one tool at a time and decide the next from what it just learned. The brief rewards that over pasting everything into one prompt.
4. **If it asked for a telemetry tool**, Python runs it against real data. The tool summarises the result, caps it, redacts anything that names a feature flag, and gives every item a reference such as `metric-2`, `trace-5` or `log-10`. The result goes back to the model, and the call is written to `transcript.jsonl`, our action log. Then the loop goes round again, up to 14 steps. A `KILL_SWITCH` file stops it at the next step.
5. **If it asked to finish**, it must call `submit_diagnosis`. A guard written in code checks four things:
   - every cited reference was returned by a tool in this run;
   - a "diagnosed" answer cites evidence about the service it names;
   - "high" confidence has at least two independent kinds of evidence;
   - the output is valid against `schema.json`.
   If any check fails, the reason goes back to the model and it resubmits.
6. **Output:** `diagnosis.json` (the scored, schema-valid one), `report.md` for the human approver, and the transcript.
7. **If the budget runs out**, it still returns valid JSON, marked as an honest escalation. It never crashes.

*(Point at the right half.)* This is the same cascade, written as rules in the system prompt: metrics first, then the errors branch or the latency/silent branch, then converge or escalate.

*(Point at the grey boxes.)* Day 2 is already designed: a human approval gate, then the Action API, then verifying recovery. We greyed those boxes out because they're planned, not built.

---

## 6:00 – 13:00 · Every file, what it does, and why

**`config.py`: the only place URLs, ports and the model name are written down.**
- Jaeger goes through Envoy at `localhost:8080/jaeger/ui`, and Prometheus is at `localhost:9090`.
- OpenSearch has no fixed host port and the port changes every restart, so `config.py` asks `docker compose port opensearch 9200` on each run.
- It also reads `.env.local` (API key, base URL, model name). That file is git-ignored, so the key never enters the repo.

**`llm.py`: the only file that talks to the LLM.**
- Groq is OpenAI-compatible, so we use the OpenAI SDK with a different base URL. Switching provider is a config change.
- Venue wifi drops, so connection, timeout, rate-limit and server errors are retried with back-off from 5 seconds up to 90. A bad request or a wrong key fails immediately, because those are real bugs.

**`tools.py`: seven telemetry tools plus the evidence registry. The most important rule in the repo: this file never imports the LLM SDK.** So we can debug any tool from the shell without spending tokens, for example `python tools.py search_traces checkout`.
- **`get_service_health`** runs PromQL over the span-metrics connector: error ratio, request rate and p95 latency per service, worst first. A service that reported in the last hour but has no traffic now is marked NOT_REPORTING: down, not healthy. Load generators are marked as clients, because their roughly 5% background errors only mirror downstream services.
- **`search_traces` and `get_trace`** use Jaeger's v3 API. Jaeger 2.21 removed the old `/api/traces` endpoint, and the v3 search ignores attribute filters, so we filter for errors ourselves. Every trace is flattened to one line per span: never raw Jaeger JSON, which can be 200 KB.
- **`find_deepest_failing_spans`** computes the culprit in Python: an erroring span with no erroring children, ranked by depth in the tree. Envoy and the load generator break some parent links, so depth ranking keeps `payment charge` ahead of `frontend-proxy egress`. It's a fixed rule, so a loop gets it right every time while an LLM gets it right most of the time.
- **`search_logs`** queries OpenSearch filtered by service, time window and severity, never the whole index. We verified the real field names by hand: `body`, `resource.service.name`, `@timestamp`, `severity.text`. Repeated identical lines are collapsed with a count to save tokens.
- **`get_container_health`** combines the Docker engine's view (stopped, exit code, OOM-killed, restart count, CPU limit) with Prometheus container metrics (CPU, memory against the limit, uptime resets).
  - It recognises a stack-wide restart, so one reset is not treated as a fault.
  - Its thresholds are tuned against the real baseline; for example, Kafka's JVM idles at about 95% memory.
- **`get_deploy_history`** lists what was started, stopped, restarted or re-limited recently. It's a stand-in built on `docker inspect` until the organisers tell us their deploy-history source.
- **The evidence registry** is about 15 lines: `register_evidence_item` gives each returned item a reference, and `check_cited_evidence` finds references that were never returned.
- **Rule-6 hygiene:**
  - no tool ever calls flagd, the Flag UI or the flag file;
  - the flagd services are hidden;
  - any attribute or log text naming a feature flag is replaced by a redaction marker. The demo really does log lines like "Feature Flag adManualGc enabled".

**`agent.py`: the loop, the tool descriptions, the guard and the CLI.**
- The loop is about 70 lines of plain Python, with no agent framework, so every one of us can explain and change it.
- A tool that throws returns `{"error": ...}` to the model instead of killing the run.
- **`build_diagnosis`** is the guard: it rejects invented references and enforces calibration *in code*:
  - high confidence needs two evidence kinds naming the root-cause service; otherwise confidence is capped at 0.70;
  - an escalation is capped at 0.45 and its action is forced to `escalate_to_human`.
- **`fallback_escalation`** guarantees valid output even when the model never finishes.
- **`watch()`** is the detection loop.

**`prompts/system_prompt.md`: the investigation policy, kept in its own file so we can compare versions.** Five parts:
1. who it is;
2. an infrastructure map (valkey-cart is redis, astronomy-db is Postgres, Kafka connects checkout to accounting and fraud-detection);
3. the cascade as numbered rules;
4. the evidence rule;
5. the confidence rule.
The two rules that moved our scores most:
- "the deepest erroring span, not the service the alert named";
- "blame a dependency only if it is actually unhealthy; if it is healthy, blame the caller".

**`schema.json` and `report.py`: output that passes the schema every time.**
- `schema.json` is provisional: we wrote it from the brief because the organisers' schema wasn't in our kit. Swapping theirs in is a one-file change plus field names in `build_diagnosis`.
- Each evidence item is a *typed record*, not a sentence:
  - a trace carries the trace ID, service, span, duration and status;
  - a log carries the timestamp, service and the actual line;
  - a metric carries the exact PromQL, the value and the timestamp.
- `report.py` validates with `jsonschema` and renders the readable report.

**`practice/faultctl.py` and `practice/incidents.json`: a stand-in for the organisers' faultctl.**
- It injects 12 practice incidents and resets everything.
- Application faults go through the Flag UI's API, which is the same thing a person clicking in the UI does.
- Infrastructure faults use `docker stop`, a restart loop and a CPU limit.
- The expected answers live only here. **The agent never imports this folder**, so nothing is hard-coded (rule 4).

**`run_all.py`: the practice sweep.** For each incident:
1. reset;
2. wait for a quiet baseline (we learned this when Kafka's startup noise fooled a run);
3. inject;
4. wait two minutes;
5. diagnose, score, reset.
It writes `reports/sweep-*/scoring-table.md`.

**`tests/test_offline.py`: seven tests that need no stack and no LLM.** They cover:
- an invented reference is rejected;
- one evidence kind caps confidence at medium;
- an escalation forces low confidence;
- the deepest failing span is payment, not frontend;
- feature-flag text is redacted.

**`smoke_test_llm.py`** is the Checkpoint 0 proof: one tool, `get_time`, which the model must call and then use the result.

**`demo.sh`** is the live run as one command.

**`docs/`** holds the architecture sketch, this flow diagram, the kickoff notes and the mentor questions.

**`reports/`** holds real agent output, including the Checkpoint 1 payment diagnosis and every sweep with its transcripts.

---

## 13:00 – 15:00 · Live demo result (back to the second terminal)

Read the report out loud:

- "Root cause: **payment**, application error. Symptom-only services: checkout, frontend, frontend-proxy."
- "Evidence: `metric` (payment error ratio from Prometheus, with the exact PromQL), `trace` (the payment `charge` span: *Invalid token*), `log` (the payment WARN line at that timestamp). Three kinds agree, so **high** confidence."
- "Proposed action, waiting for approval: one allowlisted remedy, with a reason."

Then open `transcript.jsonl`: "Every tool call and every result is here. Four calls, under a minute."

**If it fails live, say exactly what happened.** For example: "it found the right service but the log tool timed out; here is the transcript." Honesty is scored, and the escalation path exists for exactly this.

---

## 15:00 – 17:00 · Safety and honesty, by design

- **Invented evidence is structurally impossible.** The report contains the registry's copy of each item, not the model's retelling. We can show the guard rejecting a made-up `trace-99` (that's the offline test).
- **Calibration is enforced in code, not requested in the prompt.** Our target metric is *zero confidently-wrong answers*: being wrong at medium confidence is acceptable, being wrong at high confidence is not.
- **Escalation is a first-class result**, with its own status, low confidence and an `escalate_to_human` action.
- **Read-only on Day 1.** The agent proposes and never executes. Every action carries `requires_approval: true`.
- **Rule 6.** No flag settings are read, and flag-naming telemetry is redacted until a mentor says otherwise. That's one of our questions for you.

---

## 17:00 – 18:30 · Problems we hit, and what each one taught us

1. **Jaeger 2.21 has no `/api/traces`, only v3**, and v3 ignores error filters. We rewrote the trace tools against real responses.
2. **OpenSearch's port changes on every restart**, so `config.py` discovers it on each run.
3. **Two copies of the demo shared one compose project name** and recreated each other's containers mid-sweep, which wiped Jaeger and Prometheus. Lesson: one stack, one owner.
4. **A sweep started too early** got Kafka's startup errors. The agent read them *correctly*, but they weren't the injected fault. The sweep now waits for a quiet baseline.
5. **The agent once blamed astronomy-db (Postgres) for a redis error.** Fix: an infrastructure map, plus "blame a dependency only if it is unhealthy". Calibration had already capped that wrong answer at medium.
6. **load-generator shows about 5% errors when healthy.** It's now treated as a client, never a suspect.

---

## 18:30 – 20:00 · Results, limitations, Day 2

**Results:** read the current table from `evaluation-note.md`: passes, escalations, and the confidently-wrong count, which should be zero.

**Limitations, stated plainly:**
- the schema and faultctl are stand-ins until we have the official ones;
- deploy history is derived from Docker;
- detecting CPU starvation relies on the container's CPU limit plus slow spans;
- the load is light (about 1.5 requests per second), so checkout faults produce few error traces.

**Day 2 plan:**
- an Action API wrapper that only allows allowlisted remedies;
- a `y/N` approval gate in the terminal, logged, plus a dry-run mode;
- the kill switch, which already stops the loop, also blocks actions;
- recovery verified with the same health tools, with roll-back and escalation if recovery fails;
- stretch goals: reusing past incident reports as memory, and a reviewer agent that tries to disprove the diagnosis.

**Close:** "It finds the deepest failure, proves it with evidence that exists, says how sure it is, and asks before it acts."

---

## Likely mentor questions, with short answers

1. **Why not LangChain or LangGraph?** We're judged on agent design, and each of us has to explain and change the code. A 70-line loop is faster to debug, cheaper in tokens, and fully explainable.
2. **How do you stop hallucinated evidence?** The evidence registry, enforced in `build_diagnosis`. References not returned in this run are rejected, and the report embeds the registry's records, not the model's text.
3. **Why compute the deepest failing span in Python?** It's a fixed rule. Code gets it right every time, an LLM most of the time. The model still decides *which* traces to look at and how to combine the evidence.
4. **How is confidence decided?** The model proposes a number, and code caps it: high needs at least two independent evidence kinds naming the same service, one kind caps at 0.70, and an escalation caps at 0.45.
5. **What happens when it's wrong?** Ideally it's wrong at medium or low confidence, or it escalates. We track the confidently-wrong count and drive it to zero.
6. **How do you detect infrastructure faults with no exceptions?** `get_container_health` (Docker state plus uptime resets, memory and CPU limit), silent services in metrics (NOT_REPORTING), latency hotspots by self-time, and deploy history.
7. **Did you read the feature flags?** No. No tool touches flagd, the Flag UI or the flag file. The practice injector uses the Flag UI API only to *inject* faults, the way a person would, and the agent never imports it. Flag-naming telemetry is redacted.
8. **How would the hidden-test harness call you?** `from agent import diagnose; diagnose(alert_text)` returns the schema-valid dict, or use the CLI, which prints JSON on stdout. `--watch` covers the case where we must detect the incident ourselves.
9. **Why metrics before traces?** One query covers everything, and starting from traces means guessing a service.
10. **What if a tool fails or the network drops?** Tools return `{"error": ...}` to the model, LLM calls retry with back-off, and running out of budget still produces a valid escalation.
11. **Token and cost control?** Small, capped tool results (15 items, 300 characters, one line per span), one tool per step, a 14-step cap, and a 49-second, 4-call run for payment.
12. **What did each of you build?** Answer from `team-form.md`. Each member should be able to walk the whole flow on `docs/flow.png`, not just their own file.
13. **What's not finished?** The Day 2 action layer, the official schema and faultctl, and a real deploy-history source. See the limitations above.
14. **How do you know it works?** The offline tests, plus the practice sweep: 12 injected incidents, scored against expected answers the agent never sees, with transcripts in `reports/`.
15. **Did you use AI coding assistants?** Yes, declared in `team-form.md` (Claude Code). Every member has read and can change the code.
