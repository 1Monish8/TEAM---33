#!/usr/bin/env bash
# run_everything.sh: the whole project in one command.
#
#   ./run_everything.sh                 stack -> pre-flight -> tests -> API check -> tool snapshot ->
#                                       full live loop (you approve with y) -> action log -> calibration -> reset
#   ./run_everything.sh --matrix        also: tool-level fault detection for every injectable fault (~65 min, no LLM)
#   ./run_everything.sh --sweep         also: the agent on 4 practice incidents (~25 min, ~120k LLM tokens)
#   ./run_everything.sh --incident payment-failure     run the live loop on another incident
set -uo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
DEMO_DIR="${DEMO_DIR:-/Users/taruns/Downloads/bosch/opentelemetry-demo}"
INCIDENT="currency-stopped"
RUN_MATRIX=0
RUN_SWEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --matrix) RUN_MATRIX=1 ;;
    --sweep) RUN_SWEEP=1 ;;
    --incident) INCIDENT="$2"; shift ;;
    *) echo "unknown option $1"; exit 1 ;;
  esac
  shift
done

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$1"; exit 1; }

step "0. nothing else may inject faults at the same time"
if pgrep -f "run_all.py|fault_detection_check.py|demo.sh" >/dev/null; then
  echo "Another practice run is active. Running both would spoil both. Active now:"
  for pid in $(pgrep -f "run_all.py|fault_detection_check.py|demo.sh"); do
    ps -o command= -p "$pid" 2>/dev/null | tr '\n' ' ' | grep -E -o "(run_all|fault_detection_check)\.py[^;]*|demo\.sh.*" | head -1 | cut -c1-100 | sed 's/^/   /'
  done | sort -u
  echo "Progress: tail -3 runs/fault-detection.log runs/day2-final-sweep.log  ·  answer N to wait, then run this again"
  read -r -p "Stop it and continue? [y/N] " answer
  case "$answer" in y|Y|yes|YES|Yes) ;; *) fail "Stopped. Nothing was changed." ;; esac
  pkill -f "while pgrep -f fault_detection_check" ; pkill -f fault_detection_check.py ; pkill -f run_all.py ; sleep 2
fi
[ -f KILL_SWITCH ] && { echo "A KILL_SWITCH file is present; removing it."; rm -f KILL_SWITCH; }
$PY practice/faultctl.py reset >/dev/null && echo "no practice fault active"

step "1. demo stack (full mode, one folder: $DEMO_DIR)"
dc() { (cd "$DEMO_DIR" && docker compose --env-file .env --env-file .env.override -f compose.yaml \
        -f compose.full.yaml -f compose.observability.yaml -f compose.extras.yaml "$@"); }
docker info >/dev/null 2>&1 || fail "Docker is not running: start Docker Desktop first."
running=$(dc ps --format '{{.State}}' | grep -c running || true)
if [ "$running" -lt 28 ]; then
  echo "only $running/28 running: starting the stack (Kafka is slow, so retrying)"
  for attempt in 1 2 3 4 5 6; do
    dc up -d --remove-orphans >/dev/null 2>&1 || true
    running=$(dc ps --format '{{.State}}' | grep -c running || true)
    echo "  attempt $attempt: $running/28 running"
    [ "$running" -ge 28 ] && break
    sleep 15
  done
  echo "letting telemetry build up for 3 minutes"
  sleep 180
fi
echo "stack: $running/28 containers running"

step "2. pre-flight: every data source fresh"
$PY check_stack.py --fix || fail "Pre-flight failed: fix the FAIL lines above, then run again."

step "3. offline tests (no stack, no LLM)"
results=$($PY tests/test_offline.py 2>&1) || { echo "$results"; fail "Offline tests failed."; }
echo "passed: $(echo "$results" | grep -c '^ok ') tests"

step "4. LLM key and tool calling"
$PY smoke_test_llm.py || fail "LLM check failed: check API_KEY in .env.local (or the daily token cap)."

step "5. what the agent's tools see right now (no LLM)"
$PY - <<'EOF'
import tools
health = tools.get_service_health(5)
print("services ranked by deviation from their own normal:")
for row in health["services"][:5]:
    print("   %-16s deviation %-6s %s" % (row["service"], row["deviation_score"], row["status_hint"][:60]))
containers = tools.get_container_health(15)["containers_with_problems"]
print("containers with problems:", [(c["container"], c["problems"][0]) for c in containers] or "none")
deps = tools.get_dependency_health(10)
print("kafka / database / cache / disk problems:", [(p["service"], p["problem"]) for p in deps["problems"]] or "none")
EOF

step "6. the full loop on '$INCIDENT': diagnose -> reviewer -> dry run -> YOU approve (y) -> act -> verify"
echo "tip: to test the kill switch, run 'touch KILL_SWITCH' in another terminal during this step"
./demo.sh "$INCIDENT"

step "7. action log (every attempt, refusal and approval)"
tail -5 action_log.jsonl 2>/dev/null | $PY -c "import json,sys; [print('  ', r['logged_at'], r['purpose'], r['action'], r['target'], 'approved=%s' % r['approved'], 'ok=%s' % r['result'].get('ok')) for r in map(json.loads, sys.stdin)]"

if [ "$RUN_MATRIX" = "1" ]; then
  step "8. fault detection matrix (tool layer, no LLM, ~65 min)"
  $PY practice/fault_detection_check.py
fi

if [ "$RUN_SWEEP" = "1" ]; then
  step "9. agent sweep on 4 practice incidents (~120k tokens)"
  $PY run_all.py payment-failure currency-stopped kafka-queue-problems homepage-flood
fi

step "10. calibration: stated confidence vs actual accuracy (all sweeps so far)"
$PY calibration.py | tail -7

step "11. reset"
$PY practice/faultctl.py reset
rm -f KILL_SWITCH
echo
echo "Done. Reports: reports/demo/  ·  action log: action_log.jsonl  ·  docs: README.md, evaluation-note.md"
