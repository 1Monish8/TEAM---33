# Incident report killswitch-test

- **Alert:** Error rate elevated on frontend
- **Status:** ESCALATED
- **Root cause service:** None (unknown)
- **Confidence:** low (0.2)

## What happened

Automatic escalation: no accepted diagnosis within the iteration/rejection budget. The cited items are the most suspicious signals the tools returned; a human should take over.

## Evidence (every item was returned by a tool in this run)

- `metric-1` currency · container_state = exited @ 2026-10-23T19:01:26Z
- `metric-2` frontend · error_ratio = 0.0962 @ 2026-10-23T19:01:26Z
- `metric-3` checkout · error_ratio = 0.1111 @ 2026-10-23T19:01:26Z
- `metric-4` frontend-proxy · error_ratio = 0.0656 @ 2026-10-23T19:01:26Z

## Proposed action (needs human approval)

- **Action:** escalate_to_human
- **Reason:** The agent could not reach a confident, evidence-backed diagnosis.

## Action loop (dry run → human approval → act → verify → roll back)

- **Outcome:** escalated to a human, no action: the agent was not confident enough to propose a change
- **Mode:** interactive

## Timeline

- 2026-10-23T19:01:25Z — Alert received: Error rate elevated on frontend
- 2026-10-23T19:02:27Z — Diagnosis submitted after 2 tool calls

## Investigation

- Model: openai/gpt-oss-120b
- Tool calls: 2 (get_service_health, search_traces)
