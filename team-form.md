# Team form

| Field | Value |
|---|---|
| Team name | TEAM-33 |
| Members | Tarun, Devaki, Monish, _Member 4_, _Member 5_ (each member confirms their own name in their own commit) |

## Who built which part

| Part | Files | Owner |
|---|---|---|
| Host: stack, faultctl, ports, scripts, pre-flight | `config.py`, `practice/`, `run_day1.sh`, `demo.sh`, `check_stack.py`, `SETUP_NOTES.md` | Monish |
| Tools: telemetry tools, evidence registry, baselines/deviation ranking | `tools.py` | Devaki |
| Loop: agent loop, prompt, LLM client, reviewer, approval loop | `agent.py`, `prompts/system_prompt.md`, `llm.py`, `smoke_test_llm.py` | Tarun |
| Day 2 action layer: allowlist, dry run, approval-gated execute, rollback map | `actions.py` | Devaki |
| Day 2 recovery verification | `verify.py` | Monish |
| Output: schema, report, tests | `schema.json`, `report.py`, `examples/`, `tests/` | _Member 4_ |
| Evidence: sweeps, calibration, evaluation note, docs | `run_all.py`, `calibration.py`, `reports/`, `evaluation-note.md`, `docs/` | _Member 5_ |

Full split, interview prep and git commands: `docs/TEAM_SPLIT.md`.

## Tools and AI models used (every one, as rule 2 requires)

| What | Exact model / product | Where |
|---|---|---|
| Agent LLM (primary) | Groq `openai/gpt-oss-120b` via the OpenAI-compatible API | `llm.py`: every investigation step and the reviewer call |
| Agent LLM (fallback) | Groq `openai/gpt-oss-20b` (same API; separate per-model quota) | `llm.py`: used **only** if the primary is rate-limited beyond its retries. Each transcript line records which model answered (`"model"` in `llm_reply` events), so any run that used it can be identified. |
| AI coding assistant | Claude Code (Anthropic) | Helped write and test this code and its documentation on both days. Declared under rule 2. Every member must be able to explain and change the code they submit. |
| Third-party libraries | `requests`, `openai`, `jsonschema` | `requirements.txt`. No agent framework. |
| Application under test | OpenTelemetry Demo (Astronomy Shop), open source | run unmodified in Docker Compose full mode |
