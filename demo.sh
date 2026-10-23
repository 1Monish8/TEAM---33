#!/usr/bin/env bash
# demo.sh — the Checkpoint 3 live run: alert -> diagnosis -> reviewer -> dry run -> YOU approve -> act -> verify -> report.
#
#   ./demo.sh                                            # currency-stopped: restart_service, verified recovery
#   ./demo.sh payment-failure                            # flag fix: when asked, name the flag (the agent never reads flags)
#   ./demo.sh currency-stopped "" --dry-run              # show what WOULD change; nothing is touched
#   ./demo.sh payment-failure "" --demo-hallucination    # watch the evidence guard reject a planted trace-9999
#
# During the run, from another terminal:   touch KILL_SWITCH   (stops it at the next step; rm KILL_SWITCH to clear)
# With the organisers' faultctl, replace the two practice/faultctl.py lines.
set -euo pipefail
cd "$(dirname "$0")"
INCIDENT="${1:-currency-stopped}"
ALERT="${2:-}"
shift $(( $# > 2 ? 2 : $# )) || true
PY=.venv/bin/python

if pgrep -f run_all.py >/dev/null; then
  echo "A practice sweep (run_all.py) is running and would clash with this demo. Stop it first: pkill -f run_all.py"
  exit 1
fi
if [ -z "$ALERT" ]; then
  ALERT=$($PY -c "import json,sys; print(json.load(open('practice/incidents.json'))['incidents'][sys.argv[1]]['alert'])" "$INCIDENT")
fi

echo "==> pre-flight"
$PY check_stack.py --fix || { echo "stack not healthy: fix the FAIL lines above first"; exit 1; }

echo "==> inject $INCIDENT, then wait 120 s (Prometheus scrapes and SDKs export every 60 s, so metrics lag the fault)"
$PY practice/faultctl.py reset >/dev/null
$PY practice/faultctl.py inject "$INCIDENT"
sleep 120

RUN_ID="demo-$INCIDENT-$(date +%H%M%S)"
echo "==> agent: \"$ALERT\""
$PY agent.py "$ALERT" --incident-id "$RUN_ID" --out reports/demo "$@" > /dev/null

echo
echo "==> report: reports/demo/$RUN_ID/report.md"
sed -n '/^## Action loop/,/^## /p' "reports/demo/$RUN_ID/report.md" | sed '$d' || true
echo "==> action log entries for this run (action_log.jsonl):"
grep "\"$RUN_ID\"" action_log.jsonl 2>/dev/null | $PY -c "import json,sys; [print('  ', r['logged_at'], r['purpose'], r['action'], r['target'], 'approved=%s' % r['approved'], 'ok=%s' % r['result'].get('ok')) for r in map(json.loads, sys.stdin)]" || echo "   (none: nothing was executed)"

$PY practice/faultctl.py reset >/dev/null && echo "==> practice fault reset"
