# report.py — schema validation and turning a diagnosis into readable text.
# The JSON is what gets scored; the markdown is what a human reads before approving anything.
import json
import pathlib
import sys

import jsonschema

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent / "schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())
_VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())


def schema_errors(diagnosis):
    # returns a list of human-readable problems; empty list means valid
    problems = []
    for error in _VALIDATOR.iter_errors(diagnosis):
        where = "/".join(str(part) for part in error.absolute_path) or "(top level)"
        problems.append(where + ": " + error.message)
    return problems


def render_markdown(diagnosis):
    root_cause = diagnosis["root_cause"]
    action = diagnosis["proposed_action"]
    lines = [
        "# Incident report " + diagnosis["incident_id"],
        "",
        "- **Alert:** " + diagnosis["alert"],
        "- **Status:** " + diagnosis["status"].upper(),
        "- **Root cause service:** " + str(root_cause["service"]) + " (" + root_cause["fault_type"] + ")",
        "- **Confidence:** " + diagnosis["confidence_label"] + " (" + str(diagnosis["confidence"]) + ")",
    ]
    if diagnosis.get("symptom_services"):
        lines.append("- **Symptom-only services:** " + ", ".join(diagnosis["symptom_services"]))
    lines += ["", "## What happened", "", root_cause["summary"], "", "## Evidence (every item was returned by a tool in this run)", ""]
    if not diagnosis["evidence"]:
        lines.append("_No evidence cited._")
    for item in diagnosis["evidence"]:
        lines.append("- `" + item["reference"] + "` " + _evidence_one_liner(item))
    lines += [
        "",
        "## Proposed action (needs human approval)",
        "",
        "- **Action:** " + action["action"] + (" on `" + action["target"] + "`" if action.get("target") else ""),
        "- **Reason:** " + action["reason"],
    ]
    if diagnosis.get("prevention"):
        lines += ["", "## What would prevent a repeat", "", diagnosis["prevention"]]
    if diagnosis.get("timeline"):
        lines += ["", "## Timeline", ""]
        for entry in diagnosis["timeline"]:
            lines.append("- " + entry["time"] + " — " + entry["event"])
    investigation = diagnosis["investigation"]
    lines += [
        "",
        "## Investigation",
        "",
        "- Model: " + investigation["model"],
        "- Tool calls: " + str(investigation["tool_calls"]) + " (" + ", ".join(investigation["tools_used"]) + ")",
    ]
    for note in investigation.get("calibration_notes", []):
        lines.append("- Calibration: " + note)
    return "\n".join(lines) + "\n"


def _evidence_one_liner(item):
    kind = item["kind"]
    if kind == "trace":
        text = "trace " + item["trace_id"][:16] + " · " + str(item["service"]) + " · " + item["span_name"]
        text += " · " + str(item["duration_ms"]) + " ms · " + item["status"]
        if item.get("exception"):
            text += " · \"" + item["exception"][:160] + "\""
    elif kind == "log":
        text = item["timestamp"] + " · " + str(item["service"]) + " · " + item.get("severity", "") + " · \"" + item["message"][:200] + "\""
    else:
        text = str(item["service"]) + " · " + item.get("metric", "metric") + " = " + str(item["value"]) + " @ " + item["timestamp"]
    if item.get("why_it_matters"):
        text += " — " + item["why_it_matters"]
    return text


if __name__ == "__main__":
    # python report.py some_report.json  -> validates and prints the readable form
    loaded = json.loads(pathlib.Path(sys.argv[1]).read_text())
    found_problems = schema_errors(loaded)
    if found_problems:
        print("INVALID:\n  " + "\n  ".join(found_problems))
        sys.exit(1)
    print(render_markdown(loaded))
