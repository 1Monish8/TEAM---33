# TEAM-33 · Who owns what (5 members)

The roles come from the Day 1 plan: **Host, Tools, Loop, Output, Evidence**. Names are a starting suggestion: swap them freely, then copy the final names into `team-form.md`.

Three rules apply to everyone:

1. **Everyone commits real work under their own name.** Checkpoint 0 and the rules check that all members committed. Each person's "your commits" list below is real work that still needs doing.
2. **Everyone can explain the whole pipeline, not just their own file.** Each student gets a one-to-one interview. Learn `docs/flow.png` end to end, and read `docs/mentor-walkthrough.md`.
3. **Two people never edit the same file.** If you need a change in someone else's file, ask the owner. Merge into `main` at least every 40 minutes.

Declared honestly (rule 2): much of the Day 1 code was written with an AI coding assistant (Claude Code), as `team-form.md` states. "Owning" a file means you have read every line, can explain why it works that way, and can change it under pressure.

---

## At a glance

| Role | Suggested member | Owns (files) | Day 2 job (Checkpoint 3 "Hands") |
|---|---|---|---|
| 1. Host | **Monish** | the demo stack, `config.py`, `practice/faultctl.py`, `practice/incidents.json`, `run_day1.sh`, `demo.sh`, `SETUP_NOTES.md` | Recovery verification and roll-back |
| 2. Tools | **Devaki** | `tools.py` (7 tools + evidence registry) | Action API wrapper (allowlisted remedies only) |
| 3. Loop | **Tarun** | `agent.py`, `prompts/system_prompt.md`, `llm.py`, `smoke_test_llm.py` | Approval gate, dry-run, kill switch |
| 4. Output | **Member 4** | `schema.json`, `report.py`, `examples/`, `tests/test_offline.py` | Final incident report (timeline, action, prevention) + schema compliance |
| 5. Evidence | **Member 5** | `run_all.py`, `reports/`, `evaluation-note.md`, `docs/` (diagrams, walkthrough, Day 1 report) | Day 2 testing table, README, final demo script |

---

## 1. Host: Monish

**Owns:** the running demo, ports, fault injection, the one-command scripts.
**Files:** `config.py`, `practice/faultctl.py`, `practice/incidents.json`, `run_day1.sh`, `demo.sh`, `SETUP_NOTES.md`

**Must be able to explain:**
- Why we start with `docker compose … up -d --remove-orphans` in **full mode** rather than `make start`: Kafka is slow to start, and the Kafka faults need full mode.
- Why only **one** stack may run: both demo folders share the compose project name and recreate each other's containers.
- That OpenSearch's port changes on every restart, so `config.py` asks `docker compose port` each run. And that Jaeger must never be restarted: it keeps traces in memory, so a restart loses them.
- How `faultctl.py reset` turns every flag and targeting rule off, starts stopped containers, kills restart loops and removes CPU limits. And why the agent never imports `practice/`.

**Your commits (Day 1):**
- [ ] Add your name to `README.md` → *Team* and to `team-form.md` (first commit).
- [ ] When the organisers' `faultctl` arrives: wire it into `run_day1.sh` / `demo.sh` / `run_all.py` and record the 10 official incident names in `practice/incidents.json`.
- [ ] Do the clean run from scratch with `./run_day1.sh` and paste the result into the README handover.
- [ ] Push from a hotspot (`github.com` is blocked on the venue wifi), check the contributor list, then `git tag day1-end && git push --tags`.

**Day 2:** recovery verification. After an approved action, re-run `get_service_health` / `get_container_health` until healthy or timed out. If not recovered, roll back and escalate.

**At checkpoints:** drives the keyboard for the live demo (`./demo.sh`).

---

## 2. Tools: Devaki

**Owns:** everything the agent can see.
**File:** `tools.py`

**Must be able to explain:**
- The 7 tools and their data sources (Prometheus, Jaeger v3, OpenSearch, Docker), and why `tools.py` **never imports the LLM**.
- `find_deepest_failing_spans`: an erroring span with no erroring children, ranked by depth. Why it is computed in code rather than by the model.
- The evidence registry: `register_evidence_item` / `check_cited_evidence`, and refs like `trace-5`.
- Baselines (the last-hour median) for error ratio, p95 and CPU; why `accounting`'s 15 s p95 is "chronic"; `CPU_SPIKE`; `CRASHED_AND_RESTARTED`.
- Rule 6 hygiene: flag services hidden, and flag-naming text redacted.
- Why Jaeger needs the v3 API with client-side error filtering. (Your own `SETUP_NOTES.md` found this first.)

**Your commits (Day 1):**
- [ ] Add your name to `team-form.md`.
- [ ] Run each tool by hand against a live fault (`python tools.py get_service_health 5`, `search_traces checkout`, `get_container_health 15`) and add anything surprising to `SETUP_NOTES.md`.
- [ ] Commit `llm_test.py` (still untracked) or delete it. It's your or Tarun's file, so the author decides.
- [ ] Ask the mentor whether `feature_flag.*` telemetry is allowed; record the answer in `docs/kickoff-and-mentor-questions.md`.

**Day 2:** the Action API wrapper: only the allowlisted remedies (restart service, toggle flag, throttle load, scale), with every call logged.

**At checkpoints:** explains "how the agent sees" (the tools and the deepest-failing-span rule).

---

## 3. Loop: Tarun

**Owns:** how the agent thinks and decides.
**Files:** `agent.py`, `prompts/system_prompt.md`, `llm.py`, `smoke_test_llm.py`

**Must be able to explain:**
- The plain tool-calling loop: one tool per step, 14-step cap, `KILL_SWITCH` check, a tool error becomes `{"error": …}`. Why no agent framework.
- The investigation cascade in the system prompt: metrics → traces → logs, or container health; "blame a dependency only if it is unhealthy"; only a change from baseline counts as evidence.
- `build_diagnosis`, the guard:
  - invented refs rejected;
  - "diagnosed" must cite current evidence about the named service;
  - "high" needs 2 evidence kinds, otherwise capped at 0.70;
  - escalation capped at 0.45;
  - stale evidence (over 10 minutes old) excluded.
- `llm.py`: Groq through the OpenAI SDK; pacing to the 8,000 tokens/minute limit; honouring retry-after; back-off on network drops.
- `fallback_escalation`: always valid JSON. `diagnose()` for a harness and `--watch` for detection.

**Your commits (Day 1):**
- [ ] After the sweep: fix the most frequent failure mode (usually one prompt rule), re-run only the failures, and keep the before/after tables.
- [ ] Calibration check: get the confidently-wrong count to **0**, even if that means escalating on cases the agent could have guessed.

**Day 2:** the approval gate (`approve? [y/N]`, logged), a `--dry-run` that shows the plan without acting, and a kill switch that also blocks actions.

**At checkpoints:** narrates the live run and answers "why did it choose that tool?"

---

## 4. Output: Member 4

**Owns:** what we hand over, and that it always passes the schema.
**Files:** `schema.json`, `report.py`, `examples/example_diagnosis.json`, `tests/test_offline.py`

**Must be able to explain:**
- The output fields: `status` (diagnosed / escalated), `root_cause`, `symptom_services`, `confidence` + `confidence_label`, typed `evidence` (trace / log / metric records, not sentences), `proposed_action` with `requires_approval: true`, `investigation`, `timeline`.
- Why the final answer is a **tool call** (`submit_diagnosis`) rather than free text: bad JSON becomes impossible, and validation failures go back to the model.
- What each offline test proves, and how to run them (`python tests/test_offline.py`).

**Your commits (Day 1):**
- [ ] Add your name to `team-form.md`.
- [ ] **When the organisers' JSON schema arrives:** paste it verbatim into `schema.json`, update the field names in `agent.build_diagnosis`, and fix `examples/example_diagnosis.json` until `python report.py examples/example_diagnosis.json` passes.
- [ ] Add one more offline test of your choice (for example: an escalation with zero evidence still validates).

**Day 2:** the final incident report (timeline, root cause, evidence, action taken, verification result, prevention), plus the 13:30 schema-compliance check before the code freeze.

**At checkpoints:** shows the JSON and `report.md`, and the guard rejecting an invented `trace-99` (the offline test).

---

## 5. Evidence: Member 5

**Owns:** proof that it works, and the documents.
**Files:** `run_all.py`, `reports/`, `evaluation-note.md`, `docs/` (`architecture.*`, `flow.*`, `mentor-walkthrough.md`, `DAY1_REPORT.md`, `kickoff-and-mentor-questions.md`)

**Must be able to explain:**
- How a sweep works: reset → wait for a quiet baseline → inject → wait 120 s → diagnose → score against answers the agent never sees → reset → settle.
- The scoring-table columns, and what each earlier sweep taught us (see the `NOTE.md` in each `reports/sweep-*` folder).
- Why "confidently wrong" is the number that matters most.
- The architecture and flow diagrams.

**Your commits (Day 1):**
- [ ] Add your name to `team-form.md`.
- [ ] Run the sweep (`python run_all.py`; about 1.5–2 hours with rate-limit pacing, or pass only some incident names) and keep each table.
- [ ] Write `evaluation-note.md`: which incidents are right or wrong, and why.
- [ ] Update `docs/DAY1_REPORT.md` §11 and `mentor-walkthrough.md` "Results" with the final numbers.
- [ ] Fill in the README's 5 handover lines: what works, what doesn't, what to fix first tomorrow.

**Day 2:** the testing table for Checkpoint 3, the README (setup, how to run, approval gate and kill switch, known limitations), and the 5-minute final demo script.

**At checkpoints:** presents results, honesty and limitations.

---

## Shared timeline

| When | Everyone |
|---|---|
| Now | First commit each: your name in `team-form.md` / README. Agree the names in this file. |
| During the sweep | Each person reads their own files line by line, then `docs/flow.png` end to end. |
| After the sweep | Loop fixes the most common failure → Evidence re-runs the failures → Output swaps in the official schema if it has arrived. |
| 18:00 freeze | No new features. Host does the clean run from scratch; Evidence writes `evaluation-note.md`. |
| 18:30 | Everyone pushes; check the GitHub contributor list; Host tags `day1-end`. |
| Before leaving | Read out loud who owns which Day 2 job (table above). |

## Interview prep (everyone)

Practise answering these without notes:
1. Walk me through one investigation from alert to JSON.
2. Why is the root cause the deepest failing span?
3. How do you prevent invented evidence?
4. How is confidence decided, and when does it escalate?
5. What did you build, and what would you change next?

The full Q&A list is at the end of `docs/mentor-walkthrough.md`.

---

## Day 2: who owns the new parts, and what each must explain

| Member | Day 2 files | Must be able to explain |
|---|---|---|
| **Devaki** (Tools) | `actions.py`, the baseline/deviation code in `tools.py` | The allowlist; the protected containers (why never Jaeger); `approved=True` set in exactly one place; why `scale_service` is refused on Compose; why a flag write has no automatic undo; `deviation_score`, and why a missing baseline fails *closed* |
| **Monish** (Host) | `verify.py`, `check_stack.py`, `practice/faultctl.py` residue reset, `demo.sh` | Why verification waits 120 s and reads a fresh 2-min window; recovered True / False / **None = cannot tell**; the one re-check; the collector freeze and `--fix`; why reset restarts `ad` after `adHighCpu` |
| **Tarun** (Loop) | `agent.py` act loop, reviewer, `llm.py` fallback and pacing | The four gates in order; the confidence gate (≥0.5, diagnosed); the reviewer prompt and the 0.60 cap; `--dry-run`, `--yes`, `--demo-hallucination`; history compaction; fallback to `gpt-oss-20b` |
| **Member 4** (Output) | `schema.json` (`review`, `action_loop`), `report.py` action-loop section, `tests/test_offline.py` (16 tests) | What each Day 2 test proves (reject, dry run, kill switch, low confidence, recovery, rollback, hallucination) |
| **Member 5** (Evidence) | `calibration.py`, `evaluation-note.md`, `docs/architecture.png`, `docs/demo-script-day2.md` | Before and after numbers; the calibration table and what "confidently wrong" means; the 5-minute demo script |

**Day 2 interview questions to practise:**
1. Walk me through what happens after the diagnosis, up to "recovered".
2. What stops the agent from acting without a human?
3. What happens if the fix doesn't work?
4. Your agent was confidently wrong 3 times on Day 1: why, and what did you change?
5. Can your agent read feature flags? Can it change them?

---

## Git commands for all 5 members

Repo: `https://github.com/1Monish8/TEAM---33.git`, branch `main`.

**`github.com` is blocked on the venue wifi.** Run every `clone`, `pull` and `push` on a phone hotspot. Each member needs collaborator access to the repo: Monish adds them under GitHub → Settings → Collaborators.

**One rule prevents almost every conflict:** before every push, run `git pull --rebase origin main`, and only `git add` **your own files**, never `git add -A`.

### Step 0: Tarun pushes the Day 1 code first (it currently exists only on Tarun's laptop)

```bash
cd "/Users/taruns/Downloads/hakathon bosch /TEAM---33"
git pull --rebase origin main
git push origin main
```

### Step 1: one-time setup (each member, on their own laptop)

```bash
git clone https://github.com/1Monish8/TEAM---33.git
cd TEAM---33
git config user.name "Your Name"
git config user.email "the-email-on-your-github-account@example.com"
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create `.env.local` (never committed) with the team's key:
```bash
printf 'export API_KEY="PASTE_KEY"\nexport BASE_URL="https://api.groq.com/openai/v1"\nexport MODEL_NAME="openai/gpt-oss-120b"\n' > .env.local
.venv/bin/python smoke_test_llm.py
```

Use the **same email as your GitHub account** in `user.email`. Otherwise your commits won't count for you in the contributor list.

### Step 2: everyone's first commit (name in the team form)

Each member adds their own name to the *Members* row of `team-form.md`, then:
```bash
git pull --rebase origin main
git add team-form.md
git commit -m "add <your name> to team form"
git push origin main
```

### The everyday loop (every commit after that)

```bash
git pull --rebase origin main        # get everyone else's work first
# ...edit ONLY your own files...
git status                           # check that only your files changed
git add <your files>
git commit -m "<what you changed and why>"
git pull --rebase origin main        # again, in case someone pushed meanwhile
git push origin main
```

If `pull --rebase` reports a conflict: open the file, keep both sides' intent, then `git add <file> && git rebase --continue`. If unsure, `git rebase --abort` and ask the file's owner.

### Per member: their files and example commits

**1. Host: Monish**
```bash
git add practice/faultctl.py practice/incidents.json run_day1.sh demo.sh run_all.py
git commit -m "Wire in the organisers' faultctl and the 10 official practice incidents"
git add README.md
git commit -m "README handover: result of the clean run from scratch"
git pull --rebase origin main && git push origin main
```
End of day (after everyone has pushed):
```bash
git pull --rebase origin main
git tag day1-end
git push origin main --tags
```

**2. Tools: Devaki**
```bash
git add SETUP_NOTES.md
git commit -m "Setup notes: live tool checks against injected faults"
git add llm_test.py
git commit -m "Add the original LLM tool-calling test"
git add docs/kickoff-and-mentor-questions.md
git commit -m "Record the mentor's answer on feature_flag telemetry"
git pull --rebase origin main && git push origin main
```

**3. Loop: Tarun**
```bash
git add prompts/system_prompt.md agent.py
git commit -m "Prompt: fix the most frequent sweep failure"
git add agent.py
git commit -m "Calibration: zero confidently-wrong answers on the practice set"
git pull --rebase origin main && git push origin main
```

**4. Output: Member 4**
```bash
git add schema.json agent.py examples/example_diagnosis.json
git commit -m "Use the organisers' JSON schema verbatim; align submit_diagnosis fields"
git add tests/test_offline.py
git commit -m "Test: an escalation with no evidence still validates"
git pull --rebase origin main && git push origin main
```
(`agent.py` belongs to Tarun: tell Tarun before touching `build_diagnosis`, or pair on that one change.)

**5. Evidence: Member 5**
```bash
git add reports/
git commit -m "Practice sweep results with transcripts"
git add evaluation-note.md docs/DAY1_REPORT.md docs/mentor-walkthrough.md
git commit -m "Evaluation note and final Day 1 numbers"
git add README.md
git commit -m "README: five-line Day 1 handover"
git pull --rebase origin main && git push origin main
```

### Checking that everyone counts

```bash
git shortlog -sne
```
Each of the 5 names should appear. Then check the same on GitHub: **Insights → Contributors**.
