# run_all.py — the practice sweep: inject, wait, run the agent, record, reset. Writes the scoring table.
#
#   python run_all.py                       # all practice incidents
#   python run_all.py payment-failure ad-high-cpu
#   WAIT_SECONDS=150 python run_all.py
#
# The sweep measures DIAGNOSIS only (it never acts on the demo): every run goes through agent.diagnose(),
# including the reviewer. Each incident gets diagnosis.json, report.md, transcript.jsonl and verdict.json;
# calibration.py turns the verdicts into the stated-confidence vs actual-accuracy table.
#
# The expected answers live in practice/incidents.json and are used ONLY here, for scoring
# after the agent has answered. The agent never sees them (rule: no hard-coded answers).
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time

import agent
import check_stack
import config
import report

HERE = config.REPO_ROOT
INCIDENTS = json.loads((HERE / "practice" / "incidents.json").read_text())["incidents"]
WAIT_SECONDS = int(os.environ.get("WAIT_SECONDS", "120"))
SETTLE_SECONDS = int(os.environ.get("SETTLE_SECONDS", "150"))
# The ONE place the fault injector is called. When the organisers' faultctl arrives, change this line only.
FAULTCTL = [sys.executable, str(HERE / "practice" / "faultctl.py")]


def faultctl(*args):
    subprocess.run(FAULTCTL + list(args), check=True)


def wait_for_quiet_baseline(max_wait_seconds=600):
    # Never inject into a stack that is still booting (e.g. kafka creating its topics):
    # the agent would correctly diagnose the startup noise instead of the injected fault.
    import tools
    deadline = time.time() + max_wait_seconds
    while True:
        tools.reset_evidence_registry()
        noisy = [row["service"] for row in tools.get_service_health(3)["services"] if row["status_hint"] == "ERRORS"]
        if not noisy:
            return
        if time.time() > deadline:
            print("baseline still noisy after %ds (%s); injecting anyway" % (max_wait_seconds, ", ".join(noisy)), flush=True)
            return
        print("baseline not quiet yet (%s); waiting" % ", ".join(noisy), flush=True)
        time.sleep(30)


def score(name, incident, diagnosis):
    said = diagnosis["root_cause"]["service"]
    correct = said in incident["accept"]
    escalated = diagnosis["status"] == "escalated"
    if correct and not escalated:
        verdict = "PASS"
    elif escalated:
        verdict = "ESCALATED"
    else:
        verdict = "WRONG" + (" (confident!)" if diagnosis["confidence_label"] == "high" else "")
    return {
        "incident": name,
        "correct": correct and not escalated,
        "escalated": escalated,
        "confidence_value": diagnosis["confidence"],
        "reviewer": ("disputed" if diagnosis.get("review", {}).get("disputed") else "confirmed") if diagnosis.get("review", {}).get("ran") else "-",
        "expected": incident["expected_service"],
        "agent_said": said,
        "fault_type": diagnosis["root_cause"]["fault_type"],
        "confidence": diagnosis["confidence_label"] + " " + str(diagnosis["confidence"]),
        "evidence_real": "yes (%d cited, registry-checked)" % len(diagnosis["evidence"]),
        "schema_valid": "yes" if not report.schema_errors(diagnosis) else "NO",
        "tool_calls": diagnosis["investigation"]["tool_calls"],
        "seconds": diagnosis["investigation"].get("duration_seconds"),
        "verdict": verdict,
    }


def write_table(rows, path):
    columns = ["incident", "expected", "agent_said", "fault_type", "confidence", "reviewer", "evidence_real", "schema_valid",
               "tool_calls", "seconds", "verdict"]
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        lines.append("| " + " | ".join(str(row[c]) for c in columns) + " |")
    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    confident_wrong = sum(1 for r in rows if "confident" in r["verdict"])
    lines += ["", "PASS %d/%d · escalated %d · confidently wrong %d" % (
        passed, len(rows), sum(1 for r in rows if r["verdict"] == "ESCALATED"), confident_wrong)]
    path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    names = sys.argv[1:] or [name for name, incident in INCIDENTS.items() if not incident.get("helper")]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = HERE / "reports" / ("sweep-" + stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in names:
        incident = INCIDENTS[name]
        print("\n=== %s: inject, wait %ds" % (name, WAIT_SECONDS), flush=True)
        faultctl("reset")
        check_stack.ensure_span_metrics(log=lambda text: print("  preflight: " + text, flush=True))
        wait_for_quiet_baseline()
        faultctl("inject", name)
        time.sleep(WAIT_SECONDS)
        try:
            diagnosis = agent.diagnose(incident["alert"], incident_id=name, out_dir=out_dir)
            rows.append(score(name, incident, diagnosis))
            (out_dir / name / "verdict.json").write_text(json.dumps(
                {k: rows[-1][k] for k in ("incident", "expected", "agent_said", "correct", "escalated", "confidence_value", "verdict")},
                indent=2) + "\n")
        except Exception as error:  # record the crash and keep sweeping: fix after the table exists
            rows.append({"incident": name, "expected": incident["expected_service"], "agent_said": "CRASH",
                         "fault_type": "-", "confidence": "-", "reviewer": "-", "evidence_real": "-", "schema_valid": "-",
                         "tool_calls": "-", "seconds": "-", "verdict": "CRASH: " + str(error)[:80]})
        finally:
            faultctl("reset")
        print(rows[-1], flush=True)
        write_table(rows, out_dir / "scoring-table.md")
        if name != names[-1]:
            time.sleep(SETTLE_SECONDS)  # let metrics recover so incidents don't bleed into each other
    print("\nwrote", out_dir / "scoring-table.md")


if __name__ == "__main__":
    main()
