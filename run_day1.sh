#!/usr/bin/env bash
# run_day1.sh — the whole Day 1 pipeline in one command:
#   stack up (full mode) -> LLM smoke test -> offline tests -> live incident -> report -> reset
#
#   ./run_day1.sh                                   # payment-failure
#   ./run_day1.sh currency-stopped "Error rate elevated on frontend"
set -euo pipefail
cd "$(dirname "$0")"

INCIDENT="${1:-payment-failure}"
ALERT="${2:-Error rate above 5% on frontend checkout requests}"
DEMO_DIR="${DEMO_DIR:-/Users/taruns/Downloads/bosch/opentelemetry-demo}"
PY=.venv/bin/python
RUN_ID="day1-$INCIDENT-$(date +%H%M%S)"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$1"; }

if pgrep -f run_all.py >/dev/null; then
  echo "A practice sweep (run_all.py) is running; it would clash with this run."
  echo "Wait for it, or stop it with: pkill -f run_all.py"
  exit 1
fi

step "1/6 demo stack (full mode, one folder: $DEMO_DIR)"
dc() { (cd "$DEMO_DIR" && docker compose --env-file .env --env-file .env.override -f compose.yaml \
        -f compose.full.yaml -f compose.observability.yaml -f compose.extras.yaml "$@"); }
running=$(dc ps --format '{{.State}}' | grep -c running || true)
if [ "$running" -lt 28 ]; then
  echo "only $running/28 running: starting the stack (kafka can be slow, so retrying)"
  for attempt in 1 2 3 4 5 6; do
    dc up -d --remove-orphans >/dev/null 2>&1 || true
    running=$(dc ps --format '{{.State}}' | grep -c running || true)
    echo "  attempt $attempt: $running/28 running"
    [ "$running" -ge 28 ] && break
    sleep 15
  done
  echo "letting telemetry settle for 3 minutes"
  sleep 180
fi
echo "stack: $running/28 containers running"

$PY check_stack.py --fix || { echo "stack not healthy: fix the FAIL lines above first"; exit 1; }

step "2/6 LLM smoke test (key + tool calling)"
$PY smoke_test_llm.py

step "3/6 offline tests (evidence registry, calibration, deepest span, flag redaction)"
$PY tests/test_offline.py

step "4/6 inject '$INCIDENT', then wait 120s (metrics lag the fault)"
$PY practice/faultctl.py reset
$PY practice/faultctl.py inject "$INCIDENT"
sleep 120

step "5/6 agent investigates: \"$ALERT\""
$PY agent.py "$ALERT" --incident-id "$RUN_ID" --no-act > /dev/null   # Day 1 = diagnosis only; demo.sh runs the Day 2 loop
$PY report.py "runs/$RUN_ID/diagnosis.json"

step "6/6 reset"
$PY practice/faultctl.py reset

echo
echo "JSON (scored):      runs/$RUN_ID/diagnosis.json"
echo "report (readable):  runs/$RUN_ID/report.md"
echo "action log:         runs/$RUN_ID/transcript.jsonl"
