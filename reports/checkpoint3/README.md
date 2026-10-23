# Checkpoint 3 live runs

Console logs of the four live action-loop tests. Full reports (diagnosis.json, report.md, transcript.jsonl) are in `reports/demo/<run>/`; every action attempt is in `action_log.jsonl` at the repo root.

| Log | Path tested | Outcome |
|---|---|---|
| live-test1-approve.log | approve → act → verify (currency-stopped, restart_service) | recovered and verified |
| live-test2-flag.log | --demo-hallucination + write-only flag fix (payment-failure) | trace-9999 rejected; recovered and verified (deviation 20 → 0) |
| live-test3-reject.log | human answers n | rejected by the human: no change was made |
| live-test4-killswitch.log | touch KILL_SWITCH mid-investigation | investigation stopped, 0 actions |
