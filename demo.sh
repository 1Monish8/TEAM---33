#!/usr/bin/env bash
# demo.sh — the checkpoint live run, as one command: reset, inject, wait for metrics, investigate.
#   ./demo.sh                      # payment-failure
#   ./demo.sh currency-stopped "Error rate elevated on frontend"
# With the organisers' faultctl, replace the two faultctl lines with theirs.
set -euo pipefail
cd "$(dirname "$0")"
INCIDENT="${1:-payment-failure}"
ALERT="${2:-Error rate above 5% on frontend checkout requests}"
PY=.venv/bin/python

$PY practice/faultctl.py reset
$PY practice/faultctl.py inject "$INCIDENT"
echo "waiting 120s: Prometheus scrapes and SDKs export every 60s, so metrics lag the fault"
sleep 120
$PY agent.py "$ALERT" --incident-id "demo-$INCIDENT-$(date +%H%M%S)" --out reports/demo
echo
echo "readable report: reports/demo/<incident>/report.md · action log: transcript.jsonl"
$PY practice/faultctl.py reset
