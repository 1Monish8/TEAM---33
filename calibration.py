# calibration.py — does our stated confidence match how often we are actually right? (stretch goal 3)
# Reads the sweep reports we already produce. No new data, no LLM.
#
#   python calibration.py                 # every sweep under reports/
#   python calibration.py reports/sweep-20261024-0915
import json
import pathlib
import sys

import config

BANDS = [("high", 0.75, 1.01), ("medium", 0.5, 0.75), ("low", 0.0, 0.5)]
INCIDENTS = json.loads((config.REPO_ROOT / "practice" / "incidents.json").read_text())["incidents"]


def judge(incident_name, diagnosis):
    """Scored the same way as run_all.py: right service and not escalated. Escalations are counted separately."""
    incident = INCIDENTS.get(incident_name)
    if incident is None:
        return None
    said = diagnosis["root_cause"]["service"]
    escalated = diagnosis["status"] == "escalated"
    return {"incident": incident_name, "expected": incident["expected_service"], "said": said,
            "correct": (said in incident["accept"]) and not escalated, "escalated": escalated,
            "confidence": diagnosis.get("confidence", 0.0)}


def collect(sweep_dirs):
    rows = []
    for sweep in sweep_dirs:
        for diagnosis_file in sorted(pathlib.Path(sweep).glob("*/diagnosis.json")):
            verdict = judge(diagnosis_file.parent.name, json.loads(diagnosis_file.read_text()))
            if verdict:
                verdict["sweep"] = pathlib.Path(sweep).name
                rows.append(verdict)
    return rows


def build_table(rows):
    lines = ["| stated confidence | runs | correct | escalated | wrong | actual accuracy |", "|---|---|---|---|---|---|"]
    for name, low, high in BANDS:
        band = [r for r in rows if low <= r["confidence"] < high]
        correct = sum(r["correct"] for r in band)
        escalated = sum(r["escalated"] for r in band)
        wrong = len(band) - correct - escalated
        claimed = len(band) - escalated
        accuracy = ("%.0f%%" % (100.0 * correct / claimed)) if claimed else "— (none claimed)"
        lines.append("| %s (%s–%s) | %d | %d | %d | %d | %s |" % (name, low, min(high, 1.0), len(band), correct, escalated, wrong, accuracy))
    confident_wrong = [r for r in rows if r["confidence"] >= 0.75 and not r["correct"] and not r["escalated"]]
    lines += ["", "Runs: %d · correct %d · escalated %d · **confidently wrong (high and wrong): %d**%s" % (
        len(rows), sum(r["correct"] for r in rows), sum(r["escalated"] for r in rows), len(confident_wrong),
        (" (" + ", ".join("%s/%s→%s" % (r["sweep"][-13:], r["incident"], r["said"]) for r in confident_wrong) + ")") if confident_wrong else "")]
    return "\n".join(lines)


def main():
    sweeps = sys.argv[1:] or sorted(str(p) for p in (config.REPO_ROOT / "reports").glob("sweep-*") if p.is_dir())
    rows = collect(sweeps)
    print("Sweeps: " + ", ".join(pathlib.Path(s).name for s in sweeps) + "\n")
    print(build_table(rows))


if __name__ == "__main__":
    main()
