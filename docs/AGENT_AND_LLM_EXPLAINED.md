# agent.py and llm.py, explained step by step

**What this is:** a study guide for explaining the brain of the project, and for answering questions about it.

**How to read it:**
- Every claim points to a line in the real code (`agent.py:NNN`, `llm.py:NNN`), so you can open the file and show it.
- Parts 1–4 trace one incident through `agent.py`.
- Part 5 explains `llm.py`.
- Part 6 lists likely questions, with short answers.

---

## The big picture in 30 seconds

```
alert text
  └─ agent.py  run_investigation()            ← the LOOP (up to 14 turns)
       ├─ llm.py  chat()                      ← asks the model "what next?"   (the only file that talks to Groq)
       │     model answers: "call tool X with arguments Y"
       ├─ tools.py  X(Y)                      ← fetches real telemetry, returns facts with refs (metric-3, trace-7, log-12)
       ├─ result goes back into the conversation → repeat
       └─ model calls submit_diagnosis
             └─ build_diagnosis()             ← TRUST CHECKS in code (evidence guard, calibration, consistency)
  └─ apply_review()                           ← a 2nd LLM call tries to disprove it
  └─ act_on_diagnosis()                       ← dry run → human y/N → act → verify → roll back
  └─ diagnosis.json + report.md + transcript.jsonl
```

**The one sentence to remember:** *the model decides what to look at next; the code decides what counts as evidence, how confident the answer may be, and whether anything is allowed to change.*

---

## Part 1: Start-up (what happens before the loop)

| Step | Code | What it does |
|---|---|---|
| 1 | `agent.py:657` `main()` | Reads the command line: the alert text, plus `--no-act`, `--dry-run`, `--yes`, `--no-review`, `--demo-hallucination`, `--watch`, `--out` and `--incident-id`. |
| 2 | `agent.py:682` | Calls `handle_incident(alert, …)`, the full Day 2 loop. |
| 3 | `agent.py:34` | At import time, the system prompt is loaded from `prompts/system_prompt.md`. It holds the map of the shop, the investigation steps, and the evidence and confidence rules. |
| 4 | `agent.py:46–94` | `TOOL_DESCRIPTIONS` holds the **9 tools in JSON Schema** that the model may call: 8 investigation tools plus `submit_diagnosis`. This is the OpenAI "function calling" format: the model can't do anything except pick one of these and fill in its arguments. |
| 5 | `agent.py:96–105` | `AVAILABLE_TOOLS` maps each tool name to the **real Python function** in `tools.py`. The model only ever produces a *name and arguments*; our code decides what actually runs. |
| 6 | `agent.py:397` `diagnose()` | Creates the output folder (`runs/<incident>/` by default, `agent.py:410`) and starts the investigation with a transcript file. |

**Two entry points for a test harness:**
- `diagnose(alert)` only diagnoses and never acts.
- `handle_incident(alert)` runs the full loop.

---

## Part 2: The investigation loop, `run_investigation()` (`agent.py:307–394`)

### 2.1 Setting up
- `tools.reset_evidence_registry()` (`:308`) empties the evidence registry, so references from an earlier incident can't be cited.
- `run = {…}` (`:309`) holds the incident id, the start time and a log of tool calls.
- `messages` (`:312`) is the whole conversation. It starts with two entries:
  - the **system** message (the prompt);
  - a **user** message: `"ALERT: <text> Investigate it and finish with submit_diagnosis."`
- The transcript gets an `alert` event (`:323`). The transcript is one JSON line per event, written as it happens.

### 2.2 Each turn of the loop (`:326`, at most `config.MAX_AGENT_ITERATIONS` = **14** turns)

1. **Kill switch check** (`:327`). If the file `KILL_SWITCH` exists, stop immediately, record `kill_switch`, and fall through to an automatic escalation.
2. **Last turn?** (`:331`). On the final turn, the model is **forced** to call `submit_diagnosis` (`tool_choice` names it), so a run always ends with an answer, never mid-way.
3. **Ask the model** (`:333`):
   - `llm.chat(compact_history(messages), tools=TOOL_DESCRIPTIONS, tool_choice="auto")`.
   - `compact_history` (`:289`) sends the last 2 tool results in full and **shortens older ones to 600 characters, keeping every evidence reference** they contained. That roughly halves the tokens per step. The transcript still keeps the full results.
4. **Groq rejected the tool call?** (`:335`, the `ToolCallRejected` exception from llm.py):
   - Happens, for example, when the model invented a tool called `json`, or put a string where an object was expected.
   - We **don't crash**. We tell the model exactly what was wrong and list the real tool names (`:341`). After 3 rejections the run gives up and escalates.
5. **Record the reply** (`:349–352`): which model answered, the token usage, and which tools it called.
6. **No tool call?** (`:353`): the model just wrote text. We nudge it with "Continue with a tool call, or finish with submit_diagnosis".
7. **For each tool call** (`:356`):
   - The arguments arrive as a **JSON string**. Parse them; if they're broken, use `{}` (`:358–361`).
   - **If it's `submit_diagnosis`** (`:362`), hand it to `build_diagnosis()` (Part 3). It either accepts the answer, or rejects it **with a reason the model reads**, and the model must try again.
   - **Otherwise** (`:370–378`), run the real tool: `AVAILABLE_TOOLS[name](**_known_arguments(...))`.
     - `_known_arguments` (`:125`) **drops arguments the tool doesn't have**, so an invented argument can't crash it.
     - If the tool itself raises, the model gets `{"error": "..."}` instead of the run dying (`:374`).
     - The call is logged, printed (`[3] search_traces({...}) 1.2s`) and written to the transcript.
   - The result goes back into `messages` as a **`tool` message tied to the call id** (`:379`), so the model knows which answer belongs to which question.
8. **Stop when** a diagnosis was accepted, or after 3 rejections (`:381`).

### 2.3 After the loop (`:384–394`)
- **No accepted diagnosis** (budget used up, kill switch, or 3 rejections): `fallback_escalation()` (`:270`) still returns **valid JSON**. It's honestly marked *escalated*, confidence 0.2, and cites the most suspicious metrics the tools returned. The output is never empty and never a crash.
- **Diagnosed:** `apply_review()` runs the reviewer (Part 4). It can be disabled with `--no-review` or `REVIEWER=0`.
- The final diagnosis is written to the transcript. `diagnose()` then writes `diagnosis.json` and `report.md` (`:416`).

### What a typical run looks like
```
[0] get_service_health({"window_minutes": 5})        → payment ERRORS, deviation 20.0 (top)
[1] search_traces({"service": "payment"})             → deepest failing span: payment Charge, "Invalid token"
[2] search_logs({"service": "payment", "min_severity": "WARN"}) → "Payment request failed. Invalid token."
[3] submit_diagnosis(root=payment, evidence=[metric-1, trace-4, log-7], confidence 0.85)
     → accepted (3 evidence kinds name payment) → reviewer → dry run → y/N
```
That's usually **4–8 tool calls in about 3–4 minutes**, most of it waiting for the rate limit.

---

## Part 3: The trust checks, `build_diagnosis()` (`agent.py:153–257`)

This is the most important function to explain. **The model's answer is only a proposal. This function decides whether to accept it, and how confident it's allowed to be.** The checks run in this order:

| # | Check | Code | Rule | If it fails |
|---|---|---|---|---|
| 0 | Hallucination demo | `:157` | Only with `--demo-hallucination`: plants a fake `trace-9999` once | (goes straight to check 1) |
| 1 | **Evidence guard** | `:163–166` | Every cited reference must exist in the evidence registry, meaning a tool really returned it this run | **Rejected.** The model reads "these refs were not returned by any tool… resubmit" |
| 2 | **Fresh evidence** | `:180–183`, `_is_stale` `:115` | Evidence timestamped more than 10 min before the run belongs to an earlier incident | Doesn't count toward confidence |
| 3 | **Evidence about the named service** | `:184–190` | "diagnosed" needs at least one current piece of evidence that names the root-cause service | **Rejected:** "cite recent evidence that names it, or escalate" |
| 4 | **Consistency** | `:195–202` | If the run *saw* a container stopped, crashed or restart-looping, and the answer names something else | **Challenged once:** "name it, or explain why it's unrelated". If the model insists, it's accepted (we don't override). |
| 5 | **Two kinds for "high"** | `:203–206` | Confidence above 0.70 needs ≥ 2 different *kinds* (metric, trace, log) naming the service | Capped at **0.70** |
| 6 | **Twin rule** | `:210–217` | High confidence needs the named service to be among the **top 3 that moved most from their own baseline** | Capped at **0.70** |
| 7 | **Escalation means low** | `:218–225` | If the model escalates, confidence is capped at **0.45** and the action becomes `escalate_to_human` | Forced |
| 8 | **Schema** | `:254–256` | The result must fit `schema.json` | **Rejected** with the schema problems listed |

**Also:**
- Every cap is written into `calibration_notes` (shown in the report and on screen as `confidence : …`), so you can explain **why** a number is what it is.
- The labels are: **high** ≥ 0.75, **medium** ≥ 0.50, **low** below that (`:149`).
- Flag names are **removed** from `action_parameters` (`:239`). The model can't put a flag name in its answer; only the human types one.

---

## Part 4: The reviewer and the hands

### 4.1 The reviewer, `review_diagnosis()` + `apply_review()` (`agent.py:424–491`)
- It's a **second LLM call**, with a prompt whose job is to **disprove** the diagnosis (`:424`).
- It sees the claimed root cause, the evidence, and the **deviation ranking** (`:442–450`).
- It answers in exactly one line, either `CONFIRMED: …` or `DISPUTED: … | better candidate: <service>`.
- **A dispute only counts if it's grounded** (`:478`). It must:
  - name a real service the data knows about, **and**
  - that service must have moved at least 80% as far from its own baseline as the claimed one.

  Then confidence is capped at **0.60**. A speculative dispute ("maybe upstream…") is **recorded but not applied** (`:488`).
- **Why:** in the first live tests, the reviewer disputed every *correct* answer with speculation.
- It **never raises** (`:454`): a failed review isn't a failed run.

### 4.2 Acting, `act_on_diagnosis()` (`agent.py:500–580`)

| Step | Code | What happens |
|---|---|---|
| Kill switch | `:516` | Present → stop, "nothing was changed" |
| Not diagnosed / escalate | `:518` | → escalate, no action |
| Confidence < **0.50** | `:520` | → escalate, no action (`MIN_CONFIDENCE_TO_ACT`, `:497`) |
| **Dry run** | `:526–527` | `actions.describe()` works out exactly what *would* change, plus the undo, and prints the DIAGNOSIS and PROPOSED ACTION blocks |
| Flag name | `:528–534` | A flag fix needs a name: the **human types it**. The agent never reads flag configuration. |
| `--dry-run` | `:537` | Stop here, log "dry run only" |
| Not executable | `:540` | e.g. not on the allowlist, a protected container, or `scale` on Compose → escalate |
| **Approval** | `:544–551` | `Approve this action? [y/N]`. Only `y` or `yes` approves; the operator's name is logged. **No terminal = no** (`_ask_human`, `:600–609`, `EOFError` → ""). `--yes` exists only for unattended sweeps and is labelled as such in the logs. |
| Kill switch again | `:555` | Re-checked **after** the human answered |
| **Snapshot** | `:559–561` | `verify.snapshot()` captures the numbers to judge by; `capture_state()` saves what's needed to undo (e.g. the previous user count) |
| **Act** | `:563` | `actions.execute(..., approved=True)`, the only place `approved=True` is ever passed |
| **Verify** | `:568` | `verify.confirm_recovery()`: waits about 120 s and compares before and after (kill-switch aware) |
| **Roll back** | `:573–580` | Not recovered → `inverse_of()` undoes it where possible, then escalates |

Finally, `handle_incident` (`:622–634`) attaches the loop record and the action-log entries to the diagnosis and rewrites the JSON and report.

---

## Part 5: llm.py, the only file that talks to the LLM

### 5.1 Why a separate file?
- One place for the provider: **Groq**, through the **OpenAI Python SDK** with a different `base_url` (`llm.py:1–3`).
- Switching to another OpenAI-compatible provider means changing `BASE_URL` and `MODEL_NAME` in `.env.local`, nothing else.
- All the messy reality lives here: rate limits, retries, quotas, model switching. `agent.py` just calls `llm.chat(...)`.

### 5.2 `chat()`, step by step (`llm.py:135–174`)
1. **Build the request** (`:138`):
   - `temperature=0.0`: as deterministic as possible.
   - `max_completion_tokens=2048`: caps the reply, so request sizes are predictable.
   - The tools and `tool_choice`.
2. **Up to 6 attempts** (`:142`), with back-off waits of **5, 15, 30, 60 and 90 s** (`:23`).
3. **Before every attempt:**
   - `_maybe_return_to_primary()` (`:98`): if a better key or model has finished its cool-down, switch back to it.
   - `request["model"] = config.LLM_MODEL`: re-read every attempt, because the route may have changed.
   - **`_wait_for_token_budget()`** (`:114`), the **pacing**:
     - We keep our own record of the tokens used in the last 60 s (`_recent_usage`).
     - If the next request would exceed **7,200 tokens/min** (90% of Groq's 8,000), we **wait before sending** until the oldest request leaves the 60 s window. It prints `pacing: … waiting Ns`.
     - The request size is estimated by `_estimate_tokens()` (`:106`): about 4 characters per token for messages and tools, plus room for the reply based on the **replies actually seen** (1.5 × the largest recent reply, minimum 600, maximum 2,048).
   - **Why pacing exists:** each step resends the whole history, so without it we hit HTTP 429 by the third or fourth step. This crashed a run on Day 1.
4. **Send** (`:147`) and record the real usage (`:148–155`) for pacing and the transcript. `last_model_used` (`:156`) records **which model answered**, written into every transcript line (so we can always say which model produced an answer).
5. **Errors:**
   - **HTTP 400 "tool call validation failed"** (`:158–161`): becomes `ToolCallRejected`, which agent.py feeds back to the model. Any other 400 (e.g. a bad request) is a real bug and is raised.
   - **Temporary errors** (`:163`): connection, timeout, 429 and 5xx.
     - A 429 marks the current minute as full (`:165`).
     - If the 429 says **"per day"** (TPD/RPD), it's a **daily cap** → `_switch_to_fallback()` and retry immediately (`:167`). Waiting can't fix a daily cap.
     - Otherwise it waits **as long as Groq says**: `_retry_after_seconds()` (`:127`) parses "try again in 7.5s" or "1m2.3s".
     - After the last attempt, the error is raised.

### 5.3 Daily caps and routes (`llm.py:53–103`, `config.py`)
- Groq's free tier limits **each (key, model) pair** to **8k tokens/min** and **200k tokens/day**. One investigation uses about 20–35k tokens.
- `config.LLM_ROUTES` lists the pairs in order:
  **120b on the main key → 120b on the backup key → 20b on the main key → 20b on the backup key.**
- On a daily cap (`_switch_to_fallback`, `:79`):
  - the current route rests for the cool-down Groq names (at least **10 min**);
  - we take the **first route not resting**, so the big model on the backup key comes **before** any small model;
  - if all routes are capped, we take the one that clears soonest.
- **Only a daily cap switches.** A per-minute burst is handled by waiting. (Switching on bursts once put a whole sweep on the small model while the main one still had 979 requests left.)
- Every switch is printed (`… DAILY-CAPPED -> using …`), and **keys are never printed** (`_route_label`, `:64`).

### 5.4 `assistant_message_to_dict()` (`:177`)
The SDK returns an object, but the next request needs a plain dict in the history, including the `tool_calls` with their ids. This converts it.

---

### 5.5 A request bigger than the whole per-minute limit (HTTP 413)
- **What happened:** pacing waits for room in the minute, but one request can be larger than the *entire* 8,000-token allowance. A 10-call run once sent 8,082 tokens, got `413 Request too large`, and crashed.
- **Now:**
  - Before every call, `agent._fitting_history()` picks the gentlest of 3 compaction levels whose request fits. Old results are cut harder at each level, and their evidence refs are always kept.
  - If Groq still answers 413, `llm.py` raises `RequestTooLarge`. The loop moves to a harder level and retries.
  - Any other LLM failure ends in an honest escalation (`fallback_escalation`), never a crash.
- **Repeated calls:** an identical tool call (same tool, same arguments) gets a short reminder, "already called at step N, use that result", instead of a second large result.

---

## Part 6: Questions you may get, with short answers

**Why no framework (LangChain etc.)?**
The loop is about 80 lines (`agent.py:307–394`). Every member can explain it, and we can point to the exact line where each decision is made. It also let us put the trust checks exactly where we needed them.

**How does the model "call" a tool?**
Function calling. We send JSON Schemas of the 9 tools. The model replies with a tool name and a JSON string of arguments. **Our code** parses it, checks the arguments, runs the real function and sends the result back as a `tool` message tied to that call's id.

**Can the model run anything it likes?**
No. It can only *name* one of 9 tools. Unknown arguments are dropped, a malformed call gets an error back, and the only side-effect-free entry points are in `AVAILABLE_TOOLS`. Changing the system is done only by `actions.py`, after a human types y.

**How do you stop hallucinated evidence?**
Every fact a tool returns gets a reference in the registry. `build_diagnosis` rejects any citation that isn't in it (`:163`). We demo this live with `--demo-hallucination`, which plants `trace-9999`.

**Who decides the confidence: the model or you?**
The model proposes a number; the code caps it:
- 0.70 without two kinds of evidence, or when the service isn't among the top-changed;
- 0.45 for an escalation;
- 0.60 after a grounded reviewer dispute.

Every cap is written into `calibration_notes`.

**What if the model never finishes?**
On the 14th turn it's forced to call `submit_diagnosis`. After 3 rejected submissions, or a kill switch, `fallback_escalation` returns a valid, honest escalation. There's always valid JSON.

**What if a request is too big for the rate limit?**
It can't crash any more. Every request is compacted to fit under 8,000 tokens; on a 413 the agent compacts harder and retries; any other LLM error ends in a valid escalation. An identical repeated tool call gets a reminder instead of a second result.

**What if a tool or Groq fails?**
- A failing tool returns `{"error": …}` to the model, and the run continues.
- A Groq connection error, timeout or 5xx is retried with back-off, waiting as long as Groq asks.
- A daily cap switches to the next key or model.
- A malformed tool call is fed back with the list of real tools.

**Why temperature 0?**
To make it as repeatable as possible: the same evidence should lead to the same next step.

**Why does it take 3–4 minutes?**
Mostly waiting on the 8,000 tokens/minute limit. Each step resends the history, which is why we compact old tool results and pace requests ourselves.

**Does it read feature flags?**
Never for diagnosis. The tools hide flag services and redact flag text. On the action side, it can only **write** one flag whose name the **human types**, and flag names are stripped from the model's own answer (`:239`).

**What does the reviewer actually do?**
A second LLM call told to *disprove* the diagnosis, given the evidence and the deviation ranking. Only a grounded dispute lowers confidence, to 0.60. A speculative dispute is just recorded.

**What stops it acting when it shouldn't?**
In order:
1. kill switch;
2. not diagnosed, or confidence below 0.50;
3. dry run shown first;
4. a human must type y (no terminal means no);
5. the allowlist and protected containers in `actions.py`;
6. the kill switch again, after approval and during verification;
7. verification, with rollback if it didn't help.

**Which model answered?**
Every transcript line records it (`llm.last_model_used`), the diagnosis lists the models used (`investigation.model`), and the team form declares both models.

**How much does an investigation cost?**
About 20–35k tokens: roughly 4–8 tool calls plus one reviewer call. With two keys and two models, that's about 25 investigations a day on the free tier.
