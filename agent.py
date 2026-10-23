# agent.py — the investigation loop: system prompt + tool descriptions + a plain tool-calling loop.
# No framework on purpose: ~one screen of loop code that every team member can explain and change.
#
#   python agent.py "Error rate above 5% on frontend"          -> schema-valid JSON on stdout
#   python agent.py "..." --incident-id practice-01 --out reports
#   python agent.py --watch                                      -> detect: poll health, investigate on alert
#
# Entry point for a harness:  from agent import diagnose; diagnose("alert text") -> dict
import argparse
import datetime
import json
import pathlib
import sys
import time
import uuid

import config
import llm
import report
import tools

SYSTEM_PROMPT = (config.REPO_ROOT / "prompts" / "system_prompt.md").read_text()
KILL_SWITCH_FILE = config.REPO_ROOT / "KILL_SWITCH"


def _tool(name, description, properties=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
    }}


WINDOW = {"type": "integer", "description": "How many minutes back to look (default 15; use 5 for metrics)."}
TOOL_DESCRIPTIONS = [
    _tool("get_service_health", "Error ratio, request rate and p95 latency per service, worst first. Start here.",
          {"window_minutes": WINDOW}),
    _tool("get_container_health", "Per-container CPU, memory vs limit, uptime resets/restarts, stopped containers.",
          {"window_minutes": WINDOW}),
    _tool("list_services", "Every service name that reports traces."),
    _tool("search_traces", "Recent traces through one service; each result names its deepest failing span.",
          {"service": {"type": "string"},
           "only_errors": {"type": "boolean", "description": "true (default) = only traces with errors."},
           "min_duration_ms": {"type": "number", "description": "Only traces slower than this (use with only_errors=false for latency)."},
           "limit": {"type": "integer", "description": "Max traces (default 10)."},
           "window_minutes": WINDOW},
          ["service"]),
    _tool("get_trace", "One trace flattened to one line per span, with deepest_failing_spans and latency_hotspot.",
          {"trace_id": {"type": "string"}}, ["trace_id"]),
    _tool("search_logs", "Log records for a service in a time window, newest first.",
          {"service": {"type": "string"},
           "contains": {"type": "string", "description": "Optional phrase the log body must contain."},
           "min_severity": {"type": "string", "enum": ["WARN", "ERROR"]},
           "limit": {"type": "integer"},
           "window_minutes": WINDOW}),
    _tool("get_deploy_history", "Containers started, stopped, restarted or re-limited recently.",
          {"window_minutes": WINDOW}),
    _tool("submit_diagnosis", "Final answer. Ends the investigation. Cite evidence only by refs tools returned.",
          {"status": {"type": "string", "enum": ["diagnosed", "escalated"]},
           "root_cause_service": {"type": ["string", "null"], "description": "The failing component (deepest failing span / broken container), not the symptom."},
           "fault_type": {"type": "string", "enum": report.SCHEMA["properties"]["root_cause"]["properties"]["fault_type"]["enum"]},
           "root_cause_summary": {"type": "string", "description": "2-4 sentences: what is broken, how you know, what the user sees."},
           "symptom_services": {"type": "array", "items": {"type": "string"}},
           "confidence": {"type": "number", "description": "0..1 following the confidence rule."},
           "evidence": {"type": "array", "items": {"type": "object", "properties": {
               "ref": {"type": "string", "description": "e.g. trace-4, log-9, metric-2"},
               "why_it_matters": {"type": "string"}}, "required": ["ref"]}},
           "action": {"type": "string", "enum": report.SCHEMA["properties"]["proposed_action"]["properties"]["action"]["enum"]},
           "action_target": {"type": ["string", "null"]},
           "action_reason": {"type": "string"},
           "prevention": {"type": "string", "description": "One change that would stop this recurring."}},
          ["status", "root_cause_service", "fault_type", "root_cause_summary", "confidence", "evidence",
           "action", "action_target", "action_reason"]),
]

AVAILABLE_TOOLS = {
    "get_service_health": tools.get_service_health,
    "get_container_health": tools.get_container_health,
    "list_services": tools.list_services,
    "search_traces": tools.search_traces,
    "get_trace": tools.get_trace,
    "search_logs": tools.search_logs,
    "get_deploy_history": tools.get_deploy_history,
}


def _log(*parts):
    print(*parts, file=sys.stderr, flush=True)


def _label_for(confidence):
    return "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"


def build_diagnosis(arguments, run):
    """Turn submit_diagnosis arguments into a schema-valid diagnosis, or explain why not.
    Evidence checking and confidence calibration happen HERE, in code, not in the prompt."""
    cited = [item.get("ref", "") for item in arguments.get("evidence") or []]
    invented = tools.check_cited_evidence(cited)
    if invented:
        return None, ("These evidence references were not returned by any tool in this run: " + ", ".join(invented)
                      + ". Resubmit citing only refs you actually received.")

    status = arguments.get("status", "escalated")
    root_service = arguments.get("root_cause_service") or None
    evidence = []
    for item in arguments.get("evidence") or []:
        record = dict(tools.evidence_registry[item["ref"]])
        if item.get("why_it_matters"):
            record["why_it_matters"] = str(item["why_it_matters"])[:300]
        evidence.append(record)

    # Calibration: high needs >= 2 independent kinds of evidence naming the root-cause service.
    notes = []
    kinds_naming_root = {e["kind"] for e in evidence if root_service and e.get("service") == root_service}
    confidence = max(0.0, min(1.0, float(arguments.get("confidence", 0.3))))
    if status == "diagnosed" and not kinds_naming_root:
        return None, ("status=diagnosed but none of the cited evidence is about '" + str(root_service)
                      + "'. Cite evidence that names the root-cause service, or submit status=escalated.")
    if len(kinds_naming_root) < 2 and confidence > 0.7:
        notes.append("confidence capped from %.2f to 0.70: only %d evidence kind(s) name %s"
                     % (confidence, len(kinds_naming_root), root_service))
        confidence = 0.7
    if status == "escalated" and confidence > 0.49:
        notes.append("confidence capped from %.2f to 0.45 because the agent escalated" % confidence)
        confidence = 0.45

    action = arguments.get("action", "escalate_to_human")
    if status == "escalated" and action != "escalate_to_human":
        notes.append("action changed from " + action + " to escalate_to_human because status is escalated")
        action = "escalate_to_human"

    diagnosis = {
        "incident_id": run["incident_id"],
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "alert": run["alert"],
        "status": status,
        "root_cause": {"service": root_service, "fault_type": arguments.get("fault_type", "unknown"),
                       "summary": arguments.get("root_cause_summary", "")},
        "symptom_services": [s for s in arguments.get("symptom_services") or [] if s != root_service],
        "confidence": round(confidence, 2),
        "confidence_label": _label_for(confidence),
        "evidence": evidence,
        "proposed_action": {"action": action, "target": arguments.get("action_target"),
                            "reason": arguments.get("action_reason", ""), "requires_approval": True},
        "investigation": {"tool_calls": len(run["log"]), "tools_used": sorted({c["tool"] for c in run["log"]}),
                          "model": config.LLM_MODEL, "duration_seconds": round(time.time() - run["started"], 1),
                          "calibration_notes": notes},
        "timeline": _timeline(run, evidence),
    }
    if arguments.get("prevention"):
        diagnosis["prevention"] = arguments["prevention"]
    problems = report.schema_errors(diagnosis)
    if problems:
        return None, "Your submission does not fit the output schema: " + "; ".join(problems[:5])
    return diagnosis, None


def _timeline(run, evidence):
    entries = [{"time": run["started_iso"], "event": "Alert received: " + run["alert"]}]
    stamped = sorted((e.get("timestamp") or "", e) for e in evidence if e["kind"] == "log" and e.get("timestamp"))
    if stamped:
        entries.append({"time": stamped[0][0], "event": "Earliest cited log line from " + str(stamped[0][1]["service"])})
    entries.append({"time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "event": "Diagnosis submitted after %d tool calls" % len(run["log"])})
    return sorted(entries, key=lambda entry: entry["time"])


def fallback_escalation(run, reason):
    # The loop ran out of turns (or the model kept failing validation): still return valid JSON,
    # honestly marked as escalated, with the most suspicious things the tools actually returned.
    metric_refs = [token for token, item in tools.evidence_registry.items() if item["kind"] == "metric"][:4]
    arguments = {
        "status": "escalated", "root_cause_service": None, "fault_type": "unknown",
        "root_cause_summary": "Automatic escalation: " + reason + " The cited items are the most suspicious signals the tools returned; a human should take over.",
        "confidence": 0.2, "evidence": [{"ref": token} for token in metric_refs],
        "action": "escalate_to_human", "action_target": None,
        "action_reason": "The agent could not reach a confident, evidence-backed diagnosis.",
    }
    diagnosis, _ = build_diagnosis(arguments, run)
    return diagnosis


def run_investigation(alert_text, incident_id=None, maximum_iterations=None, transcript_path=None):
    tools.reset_evidence_registry()
    run = {"alert": alert_text, "incident_id": incident_id or "inc-" + uuid.uuid4().hex[:8], "log": [],
           "started": time.time(),
           "started_iso": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "ALERT: " + alert_text + "\nInvestigate it and finish with submit_diagnosis."},
    ]
    transcript = open(transcript_path, "w") if transcript_path else None

    def record(entry):
        if transcript:
            transcript.write(json.dumps(entry, default=str) + "\n")
            transcript.flush()

    record({"event": "alert", "incident_id": run["incident_id"], "alert": alert_text, "time": run["started_iso"]})
    diagnosis = None
    rejections = 0
    for iteration in range(maximum_iterations or config.MAX_AGENT_ITERATIONS):
        if KILL_SWITCH_FILE.exists():
            _log("KILL_SWITCH present: stopping the investigation")
            record({"event": "kill_switch"})
            break
        last_turn = iteration == (maximum_iterations or config.MAX_AGENT_ITERATIONS) - 1
        reply = llm.chat(messages, tools=TOOL_DESCRIPTIONS,
                         tool_choice={"type": "function", "function": {"name": "submit_diagnosis"}} if last_turn else "auto")
        messages.append(llm.assistant_message_to_dict(reply))
        if reply.content:
            record({"event": "thought", "iteration": iteration, "text": reply.content})
        if not reply.tool_calls:
            messages.append({"role": "user", "content": "Continue the investigation with a tool call, or finish with submit_diagnosis."})
            continue
        for call in reply.tool_calls:
            name = call.function.name
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            if name == "submit_diagnosis":
                diagnosis, problem = build_diagnosis(arguments, run)
                result = {"accepted": diagnosis is not None}
                if problem:
                    rejections += 1
                    result["reason"] = problem
                    _log("  submit_diagnosis rejected:", problem)
                record({"event": "submit", "iteration": iteration, "arguments": arguments, "result": result})
            else:
                started = time.time()
                try:
                    result = AVAILABLE_TOOLS[name](**arguments)
                except Exception as error:  # a broken tool must never kill the run; tell the model instead
                    result = {"error": type(error).__name__ + ": " + str(error)[:300]}
                run["log"].append({"tool": name, "arguments": arguments})
                _log("  [%d] %s(%s) %.1fs" % (iteration, name, json.dumps(arguments)[:120], time.time() - started))
                record({"event": "tool", "iteration": iteration, "tool": name, "arguments": arguments, "result": result})
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(result, default=str, separators=(",", ":"))})
        if diagnosis or rejections >= 3:
            break

    if diagnosis is None:
        diagnosis = fallback_escalation(run, "no accepted diagnosis within the iteration/rejection budget.")
    record({"event": "diagnosis", "diagnosis": diagnosis})
    if transcript:
        transcript.close()
    return diagnosis


def diagnose(alert_text, incident_id=None, out_dir=None):
    """Harness-friendly entry point: alert in, schema-valid diagnosis dict out (also written to disk)."""
    incident_id = incident_id or "inc-" + time.strftime("%Y%m%d-%H%M%S")
    run_dir = pathlib.Path(out_dir or config.REPO_ROOT / "runs") / incident_id
    run_dir.mkdir(parents=True, exist_ok=True)
    diagnosis = run_investigation(alert_text, incident_id, transcript_path=run_dir / "transcript.jsonl")
    (run_dir / "diagnosis.json").write_text(json.dumps(diagnosis, indent=2))
    (run_dir / "report.md").write_text(report.render_markdown(diagnosis))
    _log("wrote", run_dir)
    return diagnosis


def watch(poll_seconds=60, error_threshold=0.05, latency_threshold_ms=1500):
    """Detect: poll service health and start an investigation when a threshold is crossed."""
    _log("watching service health every %ds (errors >= %.0f%%, p95 >= %dms)" % (poll_seconds, error_threshold * 100, latency_threshold_ms))
    while True:
        tools.reset_evidence_registry()
        health = tools.get_service_health(5)["services"]
        alerts = [row for row in health if row["error_ratio"] >= error_threshold
                  or (row["p95_latency_ms"] or 0) >= latency_threshold_ms or row["status_hint"].startswith("NOT_REPORTING")]
        if alerts:
            worst = alerts[0]
            alert_text = "%s: error ratio %.1f%%, p95 %s ms, status %s" % (
                worst["service"], worst["error_ratio"] * 100, worst["p95_latency_ms"], worst["status_hint"])
            _log("ALERT ->", alert_text)
            print(json.dumps(diagnose(alert_text), indent=2))
            return
        time.sleep(poll_seconds)


def main():
    parser = argparse.ArgumentParser(description="Incident Zero on-call agent")
    parser.add_argument("alert", nargs="?", help="alert text, e.g. 'Error rate above 5%% on frontend'")
    parser.add_argument("--incident-id")
    parser.add_argument("--out", help="directory for transcript/diagnosis/report (default runs/)")
    parser.add_argument("--watch", action="store_true", help="poll metrics and investigate when an alert fires")
    args = parser.parse_args()
    if args.watch:
        watch()
        return
    if not args.alert:
        parser.error("give an alert text or --watch")
    print(json.dumps(diagnose(args.alert, args.incident_id, args.out), indent=2))


if __name__ == "__main__":
    main()
