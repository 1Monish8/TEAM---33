# TEAM-33 · Day 2 demo script (5 minutes live + 3 minutes of questions)

**Before walking up:**
- Run `python check_stack.py` and confirm ALL GREEN.
- Inject the fault so the 2-minute metric lag has already passed: `python practice/faultctl.py inject payment-failure`.
- Open three terminals:
  - **A** for the agent;
  - **B** with `touch KILL_SWITCH` typed but not entered;
  - **C** showing `docs/architecture.png`.

Rehearse twice. Whoever drives the keyboard doesn't narrate.

---

## 0:00–0:30 · The problem, in one sentence
"When payment breaks, five services report errors and the alert names the frontend. Only one of them is broken. Here's an agent that finds which one, proves it, and fixes it only when you say yes."

## 0:30–1:30 · The diagnosis (terminal A)
```bash
python agent.py "Error rate above 5% on frontend checkout requests" --dry-run
```
While it works, say: **"The root cause is the deepest failing span whose own children did not fail, and we compute that in Python, not in the prompt."**
Point at the output: it names **payment**, while checkout, frontend, frontend-proxy and load-generator are listed as symptom-only. Show the evidence lines: a metric with its exact PromQL, the failing `charge` span, and the payment log line.

## 1:30–2:00 · The evidence guard, live
```bash
python agent.py "Error rate above 5% on frontend checkout requests" --dry-run --demo-hallucination
```
On screen: `[demo] planted a fake evidence reference: trace-9999`, then `submit_diagnosis rejected: ... trace-9999 ...`, then the model resubmits with real refs.
Say: **"Invented evidence can't reach our output, because it's checked in code against what the tools actually returned."**

## 2:00–3:00 · The safe fix (terminal A)
```bash
./demo.sh currency-stopped
```
(or inject beforehand and run `python agent.py "Error rate elevated on frontend"`)
- The dry run shows `docker restart currency`, its effect and its undo. **"Nothing has changed yet."**
- Point at the reviewer line: a second model tried to disprove the diagnosis.
- Type **`y`**. It acts, then: **"We wait 120 seconds, because Prometheus scrapes every 60, so an earlier check reads the old window."**
- Verification: "currency was not reporting; now reporting with error ratio 0.0000", so **recovered and verified**.
- `tail -3 action_log.jsonl`: every call, who approved it, the result.

## 3:00–3:30 · The kill switch (terminal B)
Start another run in A. In B press Enter on `touch KILL_SWITCH`. A prints `KILL_SWITCH present: stopping` / `refusing to act`. Then `rm KILL_SWITCH`.
"Checked at every step, inside every action, and every second of verification."

## 3:30–4:15 · Honesty: where we win
```bash
python calibration.py
```
- "**Before** the Day 2 fix: when we said *high*, we were right 50% of the time, with 3 confidently-wrong answers, all on faults that produce no errors."
- "**After**: [read the numbers from evaluation-note.md]."
- Then say what doesn't work, before anyone asks:
  - the schema and faultctl are stand-ins;
  - `scale_service` is refused on Compose;
  - Kafka incidents are our weakest area;
  - flag fixes can't roll back automatically, because we never read flag state.

## 4:15–5:00 · The design decision nobody else made
"The diagnosis path physically can't read feature flags: no tool touches flagd, and flag text in telemetry is redacted before the model sees it. The action path can only *write* one, with a flag name the human gives at approval. No code reads a flag to decide anything."

---

## Questions, with short answers
- **What if the LLM is wrong?** The reviewer argues against every diagnosis. High confidence needs two evidence kinds *and* a service that actually changed from its own baseline. Escalation is a correct outcome, not a failure. And nothing acts without a human yes.
- **Why no framework?** A plain loop of about 80 lines. Every member can explain it, and we can show the exact line where each decision is made.
- **How do you know it works?** Measured sweeps across 12 practice incidents, before and after the Day 2 fix, plus the calibration table in `evaluation-note.md`. And 16 offline tests covering every safety path.
- **What if the fix doesn't work?** We verify against numbers captured before acting. If recovery isn't confirmed, we roll back (when a safe inverse exists) and escalate. "Cannot tell" is reported as cannot tell, never as success.
- **What breaks it?** Read from the README's known-limitations list. Don't improvise a defence.
