# Team form

| Field | Value |
|---|---|
| Team name | TEAM-33 |
| Members | Tarun, Devaki, Monish, Sanjana N, _Member 5_ (each member confirms their own name in their own commit) |

## Who built which part

| Part | Files | Owner |
|---|---|---|
| Host: stack, faultctl, ports, scripts | `config.py`, `practice/`, `run_day1.sh`, `demo.sh`, `SETUP_NOTES.md` | Monish |
| Tools | `tools.py` | Devaki |
| Loop | `agent.py`, `prompts/system_prompt.md`, `llm.py`, `smoke_test_llm.py` | Tarun |
| Output | `schema.json`, `report.py`, `examples/`, `tests/` | Sanjana N |
| Evidence | `run_all.py`, `reports/`, `evaluation-note.md`, `docs/` | _Member 5_ |

Full split, interview prep and git commands: `docs/TEAM_SPLIT.md`.

## Tools and AI models used

- Agent LLM: Groq `openai/gpt-oss-120b` via the OpenAI-compatible API (`llm.py`).
- AI coding assistant: Claude Code (Anthropic) helped write this code. Declared under rule 2. Every member must be able to explain and change it.
- Third-party libraries: `requests`, `openai`, `jsonschema`. No agent framework.
