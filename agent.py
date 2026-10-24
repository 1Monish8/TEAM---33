# agent.py — the investigation loop: system prompt + tool descriptions + a plain tool-calling loop.
# No framework on purpose: ~one screen of loop code that every team member can explain and change.
#
# Day 2 adds the act-and-verify loop around the unchanged diagnosis loop, with four safety gates:
#   GATE 1 reviewer disputes the diagnosis -> GATE 2 a human types y -> GATE 3 the actions.py allowlist
#   -> GATE 4 KILL_SWITCH, checked at every step. Nothing changes without a human yes; nothing is called
#   fixed without a before/after comparison (verify.py); a failed fix is rolled back and escalated.
#
#   python agent.py "Error rate above 5% on frontend"     diagnose -> dry run -> ask y/N -> act -> verify -> report
#   python agent.py "..." --dry-run                        diagnose and show what WOULD change; never acts
#   python agent.py "..." --no-act                         diagnose only (what the practice sweep measures)
#   python agent.py "..." --demo-hallucination             plant one fake evidence ref to show the guard reject it
#   python agent.py --watch                                detect: poll health, investigate when a threshold fires
#
# Entry points for a harness:  from agent import diagnose, handle_incident
#   diagnose("alert text") -> schema-valid dict (diagnosis only, never acts)
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import time
import uuid

import actions
import config
import llm
import report
import tools
import verify

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
    _tool("get_deploy_history", "Recent changes: containers recreated (config/image), restarted, stopped, crashed, re-limited or detached.",
          {"window_minutes": WINDOW}),
    _tool("get_dependency_health", "Kafka consumer groups (lag, members), PostgreSQL (connections vs max, deadlocks), the Valkey "
          "cache (down, rejected connections, evictions) and host disk, each against its own baseline.",
          {"window_minutes": WINDOW}),
    _tool("submit_diagnosis", "Final answer. Ends the investigation. Cite evidence only by refs tools returned.",
          {"status": {"type": "string", "enum": ["diagnosed", "escalated"]},
           "root_cause_service": {"type": ["string", "null"], "description": "The failing component (deepest failing span / broken container), not the symptom."},
           "fault_type": {"type": "string", "enum": report.SCHEMA["properties"]["root_cause"]["properties"]["fault_type"]["enum"]},
           "root_cause_summary": {"type": "string", "description": "2-4 sentences: what is broken, how you know, what the user sees."},
           "symptom_services": {"type": ["array", "null"], "items": {"type": "string"}},
           "confidence": {"type": "number", "description": "0..1 following the confidence rule."},
           "evidence": {"type": "array", "items": {"type": "object", "properties": {
               "ref": {"type": "string", "description": "e.g. trace-4, log-9, metric-2"},
               "why_it_matters": {"type": "string"}}, "required": ["ref"]}},
           "action": {"type": "string", "enum": report.SCHEMA["properties"]["proposed_action"]["properties"]["action"]["enum"]},
           "action_target": {"type": ["string", "null"]},
           "action_parameters": {"type": ["object", "null"], "description": "Optional, e.g. {\"user_count\": 1} for throttle_load. "
                                 "Never a flag name: you do not know flag names."},
           "action_reason": {"type": "string"},
           "prevention": {"type": ["string", "null"], "description": "One change that would stop this recurring."},
           "additional_findings": {"type": ["array", "null"], "description": "Only if the evidence shows a SECOND independent "
                                   "problem: [{\"service\": ..., \"finding\": ..., \"refs\": [...]}]. Leave out otherwise.",
                                   "items": {"type": "object", "properties": {"service": {"type": "string"},
                                             "finding": {"type": "string"}, "refs": {"type": "array", "items": {"type": "string"}}}}}},
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
    "get_dependency_health": tools.get_dependency_health,
}


def _log(*parts):
    print(*parts, file=sys.stderr, flush=True)


STALE_EVIDENCE_MINUTES = 10


def _is_stale(evidence_item, run):
    # True when the item's own timestamp is well before this investigation started
    stamp = str(evidence_item.get("timestamp") or "")[:19]
    try:
        moment = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False  # no timestamp: cannot tell, do not penalise
    return moment.timestamp() < run["started"] - STALE_EVIDENCE_MINUTES * 60


def _known_arguments(function, arguments):
    # P2 invalid tool output: a model sometimes invents parameters. Drop the ones the tool does not have instead of
    # crashing it; type errors still come back to the model as {"error": ...}.
    import inspect
    accepted = set(inspect.signature(function).parameters)
    return {key: value for key, value in (arguments or {}).items() if key in accepted}


def _additional_findings(raw):
    """P2 multiple simultaneous faults: secondary problems, each backed by real refs (same registry check)."""
    findings = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("service"):
            continue
        refs = [str(ref) for ref in item.get("refs") or []]
        invented = tools.check_cited_evidence(refs)
        if invented:
            return ("additional_findings cites references no tool returned in this run: " + ", ".join(invented)
                    + ". Resubmit citing only refs you actually received.")
        findings.append({"service": str(item["service"]), "finding": str(item.get("finding", ""))[:300],
                         "evidence": [dict(tools.evidence_registry[ref]) for ref in refs]})
    return findings[:3]


def _label_for(confidence):
    return "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"


def build_diagnosis(arguments, run):
    """Turn submit_diagnosis arguments into a schema-valid diagnosis, or explain why not.
    Evidence checking and confidence calibration happen HERE, in code, not in the prompt."""
    cited = [item.get("ref", "") for item in arguments.get("evidence") or []]
    if os.environ.get("DEMO_HALLUCINATION") == "1" and not run.get("hallucination_planted"):
        # DEMO ONLY (documented in the README): poison our own submission once, so the audience watches the
        # evidence guard reject an invented reference and the model resubmit with real ones.
        run["hallucination_planted"] = True
        cited = cited + ["trace-9999"]
        _log("  [demo] planted a fake evidence reference in the submission: trace-9999")
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

    # Calibration: high needs >= 2 independent kinds of evidence naming the root-cause service,
    # and only CURRENT evidence counts: anything from before the incident window belongs to another incident.
    notes = []
    stale = [e["reference"] for e in evidence if _is_stale(e, run)]
    if stale:
        notes.append("evidence older than %d min before the investigation does not count: %s"
                     % (STALE_EVIDENCE_MINUTES, ", ".join(stale)))
    kinds_naming_root = {e["kind"] for e in evidence
                         if root_service and e.get("service") == root_service and e["reference"] not in stale}
    confidence = max(0.0, min(1.0, float(arguments.get("confidence", 0.3))))
    if status == "diagnosed" and not kinds_naming_root:
        return None, ("status=diagnosed but none of the cited CURRENT evidence is about '" + str(root_service)
                      + "' (evidence from more than %d minutes ago belongs to an earlier incident). Cite recent evidence "
                      "that names the root-cause service, or submit status=escalated." % STALE_EVIDENCE_MINUTES)
    # Consistency check, the infrastructure twin of the evidence guard: if this run SAW a demo container stopped,
    # crashed or restart-looping and the diagnosis names something else, challenge it once. Not an override: the
    # model may keep its answer if it explains why the container is unrelated. (Found in the Day 2 sweep: the
    # fallback model named frontend-proxy while get_container_health showed valkey-cart NOT_RUNNING.)
    unexplained = {name: problem for name, problem in tools.hard_container_problems.items() if name != root_service}
    if status == "diagnosed" and unexplained and root_service not in tools.hard_container_problems \
            and not run.get("infra_challenge_done"):
        run["infra_challenge_done"] = True
        return None, ("Before this is accepted: get_container_health showed " + "; ".join(
            "%s %s" % item for item in unexplained.items()) + ". A stopped, crashed or restart-looping container is the "
            "strongest evidence an outage can have. Either name that container as the root cause (if your evidence "
            "connects it), or resubmit and explain in root_cause_summary why it is unrelated.")
    if len(kinds_naming_root) < 2 and confidence > 0.7:
        notes.append("confidence capped from %.2f to 0.70: only %d evidence kind(s) name %s"
                     % (confidence, len(kinds_naming_root), root_service))
        confidence = 0.7
    # The no-error twin of the deepest-failing-span rule: the root cause should be one of the services that moved
    # furthest from its OWN normal. If the named service is ranked but barely changed while another moved a lot,
    # a confident answer is exactly the Day 1 failure mode (accounting at its usual 15 s), so cap it.
    ranking = [(name, score) for name, score in tools.last_deviation_ranking if score is not None]
    ranked_names = [name for name, _ in ranking]
    if confidence > 0.7 and root_service in ranked_names and ranking and ranking[0][1] >= 1.0:
        top_changed = [name for name, score in ranking[:3] if score >= 0.5]
        if root_service not in top_changed:
            notes.append("confidence capped from %.2f to 0.70: %s is not among the services that moved most from their "
                         "own baseline (top: %s)" % (confidence, root_service, ", ".join(top_changed) or ranking[0][0]))
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
                            "parameters": {k: v for k, v in (arguments.get("action_parameters") or {}).items() if k != "flag"},
                            "reason": arguments.get("action_reason", ""), "requires_approval": True},
        "investigation": {"tool_calls": len(run["log"]), "tools_used": sorted({c["tool"] for c in run["log"]}),
                          "model": ", ".join(sorted(m for m in (run.get("models") or {config.LLM_MODEL}) if m)) or config.LLM_MODEL,
                          "duration_seconds": round(time.time() - run["started"], 1),
                          "calibration_notes": notes},
        "timeline": _timeline(run, evidence),
    }
    if arguments.get("prevention"):
        diagnosis["prevention"] = arguments["prevention"]
    findings = _additional_findings(arguments.get("additional_findings"))
    if isinstance(findings, str):
        return None, findings
    if findings:
        diagnosis["additional_findings"] = findings
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


FULL_RECENT_TOOL_RESULTS = 2
COMPACT_CHARS = 600
# (tool results kept in full, characters kept of older results, characters kept of the recent ones) per level
COMPACT_LEVELS = [(2, 600, None), (1, 250, 4000), (0, 120, 2000)]


def compact_history(messages, level=0):
    """What the model is sent each step. The last two tool results go in full; older ones are cut to their first
    ~600 characters plus EVERY evidence ref they contained, so citations keep working. Our Groq key allows 8,000
    tokens per minute and every step resends the whole history, so this roughly halves the cost of a step and the
    time an investigation spends waiting for the rate limit. The transcript always keeps the full results.
    Higher levels cut harder: one request may never exceed the whole per-minute allowance (a 10-call run once
    asked for 8,082 tokens against a limit of 8,000, got HTTP 413 and crashed)."""
    keep_full, older_chars, recent_chars = COMPACT_LEVELS[min(level, len(COMPACT_LEVELS) - 1)]
    tool_positions = [index for index, message in enumerate(messages) if message.get("role") == "tool"]
    recent = set(tool_positions[len(tool_positions) - keep_full:]) if keep_full else set()
    compacted = []
    for index, message in enumerate(messages):
        limit = None if index not in tool_positions else (recent_chars if index in recent else older_chars)
        if limit and len(message["content"]) > limit:
            refs = sorted(set(re.findall(r'"(?:ref|reference)":"((?:trace|log|metric)-\d+)"', message["content"])),
                          key=lambda ref: int(ref.split("-")[1]))
            message = dict(message, content=message["content"][:limit]
                           + ' ...[result shortened to save tokens; its evidence refs are still valid: %s]' % (", ".join(refs) or "none"))
        compacted.append(message)
    return compacted


def _fitting_history(messages, minimum_level=0):
    # the gentlest compaction whose request fits the per-minute allowance (the hardest one if none does)
    for level in range(minimum_level, len(COMPACT_LEVELS)):
        compacted = compact_history(messages, level)
        if llm._estimate_tokens({"messages": compacted, "tools": TOOL_DESCRIPTIONS}) <= llm.TOKEN_BUDGET:
            return compacted, level
    return compacted, len(COMPACT_LEVELS) - 1


def run_investigation(alert_text, incident_id=None, maximum_iterations=None, transcript_path=None, review_enabled=True):
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
    minimum_level = 0      # raised after an HTTP 413: from then on every request is cut harder
    llm_failure = None     # an LLM error we could not recover from: escalate honestly instead of crashing
    seen_calls = {}        # (tool, arguments) -> step it was first called at
    for iteration in range(maximum_iterations or config.MAX_AGENT_ITERATIONS):
        if KILL_SWITCH_FILE.exists():
            _log("KILL_SWITCH present: stopping the investigation")
            record({"event": "kill_switch"})
            break
        last_turn = iteration == (maximum_iterations or config.MAX_AGENT_ITERATIONS) - 1
        history, level = _fitting_history(messages, minimum_level)
        try:
            reply = llm.chat(history, tools=TOOL_DESCRIPTIONS,
                             tool_choice={"type": "function", "function": {"name": "submit_diagnosis"}} if last_turn else "auto")
        except llm.RequestTooLarge as error:
            record({"event": "request_too_large", "iteration": iteration, "level": level, "error": str(error)[:400]})
            if level >= len(COMPACT_LEVELS) - 1:
                llm_failure = "every request was larger than the provider's per-minute token limit, even fully compacted."
                break
            minimum_level = level + 1
            _log("  request too large for the per-minute limit: compacting the history harder (level %d) and retrying"
                 % minimum_level)
            continue
        except llm.ToolCallRejected as error:
            # Groq refused a malformed tool call before it ran (HTTP 400). A bad call must never crash the run:
            # tell the model exactly what was wrong and let it try again; it counts like a rejected submission.
            rejections += 1
            _log("  tool call rejected by the API:", str(error)[:200])
            record({"event": "tool_call_rejected", "iteration": iteration, "error": str(error)[:1000]})
            messages.append({"role": "user", "content": "Your last tool call was rejected by the API before it ran: "
                             + str(error)[:600] + " The only tools that exist are: "
                             + ", ".join(t["function"]["name"] for t in TOOL_DESCRIPTIONS)
                             + ". Call one of them with arguments that exactly match its schema "
                             "(use null or leave out optional fields you do not need)."})
            if rejections >= 3:
                break
            continue
        except Exception as error:  # any other LLM failure: never crash, end in an honest escalation
            llm_failure = "the LLM call failed (%s: %s)." % (type(error).__name__, str(error)[:200])
            _log("  " + llm_failure)
            record({"event": "llm_error", "iteration": iteration, "error": str(error)[:1000]})
            break
        run.setdefault("models", set()).add(llm.last_model_used)
        messages.append(llm.assistant_message_to_dict(reply))
        record({"event": "llm_reply", "iteration": iteration, "model": llm.last_model_used, "usage": llm.last_usage,
                "tool_calls": [c.function.name for c in reply.tool_calls or []], "text": reply.content or ""})
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
            elif (name, json.dumps(arguments, sort_keys=True)) in seen_calls:
                # the same call again (one run asked get_container_health three times in a row): a short reminder
                # instead of the same large result, so the history stays small and the model moves on
                first = seen_calls[(name, json.dumps(arguments, sort_keys=True))]
                result = {"note": "You already called %s with these arguments at step %d. Its result is above and its "
                                  "evidence refs are still valid. Do not repeat it: call a different tool or "
                                  "submit_diagnosis." % (name, first)}
                _log("  [%d] %s repeated: reminded the model instead of running it again" % (iteration, name))
                record({"event": "tool", "iteration": iteration, "tool": name, "arguments": arguments, "result": result})
            else:
                seen_calls[(name, json.dumps(arguments, sort_keys=True))] = iteration
                started = time.time()
                try:
                    result = AVAILABLE_TOOLS[name](**_known_arguments(AVAILABLE_TOOLS[name], arguments))
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
        reason = ("the investigation was stopped by the KILL_SWITCH." if KILL_SWITCH_FILE.exists()
                  else llm_failure or "no accepted diagnosis within the iteration/rejection budget.")
        diagnosis = fallback_escalation(run, reason)
    elif review_enabled and diagnosis["status"] == "diagnosed":
        apply_review(diagnosis)
        record({"event": "review", "model": llm.last_model_used, "review": diagnosis["review"]})
    record({"event": "diagnosis", "diagnosis": diagnosis})
    if transcript:
        transcript.close()
    return diagnosis


def diagnose(alert_text, incident_id=None, out_dir=None, review_enabled=None):
    """Harness-friendly entry point: alert in, schema-valid diagnosis dict out (also written to disk). Never acts."""
    if review_enabled is None:
        review_enabled = os.environ.get("REVIEWER", "1") != "0"
    incident_id = incident_id or "inc-" + time.strftime("%Y%m%d-%H%M%S")
    run_dir = _run_dir(incident_id, out_dir)
    diagnosis = run_investigation(alert_text, incident_id, transcript_path=run_dir / "transcript.jsonl",
                                  review_enabled=review_enabled)
    write_outputs(diagnosis, run_dir)
    _log("wrote", run_dir)
    return diagnosis


def _run_dir(incident_id, out_dir=None):
    run_dir = pathlib.Path(out_dir or config.REPO_ROOT / "runs") / incident_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_outputs(diagnosis, run_dir):
    (run_dir / "diagnosis.json").write_text(json.dumps(diagnosis, indent=2, default=str))
    (run_dir / "report.md").write_text(report.render_markdown(diagnosis))


# ---------------------------------------------------------------------------
# GATE 1: a reviewer that is paid to disagree (stretch goal 2)
# ---------------------------------------------------------------------------
REVIEWER_PROMPT = """You are reviewing another on-call engineer's incident diagnosis. Your job is to DISPROVE it, not to agree with it.
You see only the evidence that was actually collected, the conclusion drawn from it, and how far each service has moved
from its OWN last-hour baseline (deviation_score; higher = more changed). Find the strongest reason the conclusion is wrong.
Consider in particular:
- a service that is merely downstream of the real fault, or merely a client of it (frontend, checkout, load-generator)
- a service whose numbers look bad but are normal FOR THAT SERVICE (deviation_score near 0)
- a different service that moved much further from its own baseline than the one named
- evidence that is consistent with the conclusion but does not actually support it
Dispute only for a concrete reason grounded in the evidence or the ranking above, ideally naming a better candidate
service. Speculation about things the evidence does not show is not a reason: if you cannot point to a concrete flaw,
reply CONFIRMED. (Only a dispute that names a better-supported service changes the confidence.)
Reply with exactly one line, one of:
CONFIRMED: <one sentence on why the evidence does support this conclusion>
DISPUTED: <the flaw> | better candidate: <service name, or none>"""


def review_diagnosis(diagnosis):
    """A second opinion paid to disagree. One call per investigation; never raises (a failed review is not a failed run)."""
    summary = json.dumps({
        "claimed_root_cause": diagnosis["root_cause"],
        "status": diagnosis["status"],
        "confidence": diagnosis["confidence"],
        "symptom_services": diagnosis.get("symptom_services", []),
        "evidence": diagnosis["evidence"],
        "services_ranked_by_deviation_from_their_own_baseline": [
            {"service": name, "deviation_score": score} for name, score in tools.last_deviation_ranking[:6]],
    }, indent=1, default=str)[:6000]
    try:
        reply = llm.chat([{"role": "system", "content": REVIEWER_PROMPT}, {"role": "user", "content": summary}])
        verdict_text = " ".join((reply.content or "").split())
    except Exception as error:
        return {"ran": False, "disputed": False, "verdict": "review failed: %s: %s" % (type(error).__name__, str(error)[:200])}
    disputed = verdict_text.upper().startswith("DISPUTED")
    better = None
    if disputed and "better candidate:" in verdict_text.lower():
        better = verdict_text.lower().split("better candidate:", 1)[1].strip(" .").split()[0:1]
        better = better[0] if better and better[0] not in ("none", "n/a") else None
    return {"ran": True, "disputed": disputed, "better_candidate": better, "verdict": verdict_text[:500],
            "model": llm.last_model_used}


def apply_review(diagnosis):
    """A dispute lowers confidence only when it is GROUNDED in the data: it names a real service as the better
    candidate, and that service moved at least as far from its own baseline as the one claimed (the Day 1
    failure: accounting claimed at deviation 0 while ad sat at 10x its normal CPU). Speculation ("maybe the
    token is wrong upstream, better candidate: none") is recorded in the report but does not override evidence;
    on the first live tests the reviewer disputed every correct diagnosis that way."""
    review = review_diagnosis(diagnosis)
    diagnosis["review"] = review
    if not review.get("disputed"):
        return diagnosis
    deviation = dict(tools.last_deviation_ranking)
    claimed, better = diagnosis["root_cause"]["service"], review.get("better_candidate")
    known = set(deviation) | {item.get("service") for item in diagnosis["evidence"]}
    grounded = bool(better) and better != claimed and better in known and (
        claimed not in deviation or (deviation.get(better) or 0) >= 0.8 * (deviation.get(claimed) or 0))
    review["grounded"] = grounded
    if grounded and diagnosis["confidence"] > 0.6:
        # a second model found a concrete hole: exactly when a confident answer is dangerous
        diagnosis["investigation"]["calibration_notes"].append(
            "confidence lowered from %.2f to 0.60: the reviewer disputed it with a grounded alternative (%s, deviation %s "
            "vs %s for %s)" % (diagnosis["confidence"], better, deviation.get(better), deviation.get(claimed), claimed))
        diagnosis["confidence"] = 0.6
        diagnosis["confidence_label"] = _label_for(0.6)
    elif not grounded:
        diagnosis["investigation"]["calibration_notes"].append(
            "reviewer dispute recorded but not applied: it named no better candidate supported by the data")
    return diagnosis


# ---------------------------------------------------------------------------
# The act-and-verify loop: dry run -> GATE 2 human approval -> GATE 3 allowlist -> act -> verify -> roll back
# ---------------------------------------------------------------------------
MIN_CONFIDENCE_TO_ACT = 0.5


def act_on_diagnosis(diagnosis, auto_approve=False, dry_run=False, ask=None, transcript_path=None, progress=None):
    """Propose -> approve -> act -> verify -> (roll back). Returns the loop record that goes into the report."""
    ask = ask or _ask_human
    progress = progress or (lambda text: print(text, file=sys.stderr, flush=True))
    proposal = diagnosis["proposed_action"]
    action, target = proposal["action"], proposal.get("target")
    parameters = dict(proposal.get("parameters") or {})
    incident_id = diagnosis["incident_id"]
    loop = {"started_at": _utc_now(), "proposed": proposal, "mode": "dry-run" if dry_run else ("auto-approve" if auto_approve else "interactive")}

    def finish(outcome, **fields):
        loop.update(fields, outcome=outcome, finished_at=_utc_now())
        _append_transcript(transcript_path, {"event": "action_loop", "loop": loop})
        progress("  OUTCOME: " + outcome)
        return loop

    if KILL_SWITCH_FILE.exists():  # checked first, so the record says WHY nothing happened
        return finish("halted: KILL_SWITCH present, nothing was changed")
    if diagnosis["status"] != "diagnosed" or action == "escalate_to_human":
        return finish("escalated to a human, no action: the agent was not confident enough to propose a change")
    if diagnosis["confidence"] < MIN_CONFIDENCE_TO_ACT:
        return finish("escalated to a human, no action: confidence %.2f is below %.2f" % (diagnosis["confidence"], MIN_CONFIDENCE_TO_ACT))
    if KILL_SWITCH_FILE.exists():
        return finish("halted: KILL_SWITCH present, nothing was changed")

    # 1. DRY RUN: always computed, always shown before any question is asked
    plan = actions.describe(action, target, parameters)
    _print_proposal(diagnosis, plan, progress)
    if plan.get("needs_flag_name") and not dry_run and not auto_approve:
        flag = ask("  The agent never reads flag configuration. Name the flag to set for %s (blank = cancel): " % target)
        if flag:
            parameters["flag"] = flag
            parameters.setdefault("variant", "off")
            plan = actions.describe(action, target, parameters)
            progress("  would  : %s" % plan.get("effect", plan.get("reason")))
    loop["dry_run"] = plan
    loop["parameters"] = parameters
    if dry_run:
        actions.log_refusal_or_dry_run(action, target, parameters, incident_id, "dry run only", plan)
        return finish("dry run only: nothing was changed")
    if not plan["ok"]:
        actions.log_refusal_or_dry_run(action, target, parameters, incident_id, "not executable", plan)
        return finish("not executable, escalated to a human: " + plan["reason"])

    # 2. APPROVAL: the only place approved can become True
    if auto_approve:
        approved, approved_by = True, "auto-approve (--yes, unattended run; declared in the README)"
        progress("  APPROVAL: auto-approved by --yes (unattended mode)")
    else:
        answer = ask("\n  Approve this action? [y/N] ").strip().lower()
        approved, approved_by = answer in ("y", "yes"), actions.current_operator()
    loop["approved"], loop["approved_by"], loop["approved_at"] = approved, approved_by if approved else None, _utc_now()
    if not approved:
        actions.log_refusal_or_dry_run(action, target, parameters, incident_id, "rejected by the human", plan)
        return finish("rejected by the human: no change was made")
    if KILL_SWITCH_FILE.exists():  # belt and braces: re-checked after the human answered
        return finish("halted: KILL_SWITCH appeared before acting, nothing was changed")

    # 3. SNAPSHOT, then ACT through the allowlisted Action API only
    verify_service = diagnosis["root_cause"]["service"] or target
    loop["before"] = verify.snapshot(verify_service)
    loop["before_state"] = actions.capture_state(action, target, parameters)
    progress("  acting : %s" % plan["command"])
    loop["result"] = actions.execute(action, target, parameters, approved=True, incident_id=incident_id, approved_by=approved_by)
    if not loop["result"].get("ok"):
        return finish("action failed, escalated to a human: %s" % loop["result"].get("reason", loop["result"]))

    # 4. VERIFY against the numbers captured before acting
    loop["verification"] = verify.confirm_recovery(loop["before"], kill_switch_file=KILL_SWITCH_FILE, progress=progress)
    if loop["verification"]["recovered"] is True:
        return finish("recovered and verified: " + loop["verification"]["verdict"])

    # 5. ROLL BACK and escalate when recovery was not confirmed (the brief: "If it did not, roll back and escalate")
    undo = actions.inverse_of(action, target, parameters, loop["before_state"])
    if undo:
        progress("  rolling back: %s %s %s" % undo)
        loop["rollback"] = actions.execute(undo[0], undo[1], undo[2], approved=True, incident_id=incident_id,
                                           approved_by=approved_by, purpose="rollback")
        return finish("recovery not confirmed (%s): rolled back and escalated to a human" % loop["verification"]["verdict"])
    return finish("recovery not confirmed (%s): nothing to roll back (%s), escalated to a human"
                  % (loop["verification"]["verdict"], plan.get("undo", "no inverse")))


def _print_proposal(diagnosis, plan, progress):
    proposal, root = diagnosis["proposed_action"], diagnosis["root_cause"]
    progress("\n--- DIAGNOSIS ---")
    progress("  root cause : %s (%s), confidence %s %.2f" % (root["service"], root["fault_type"], diagnosis["confidence_label"], diagnosis["confidence"]))
    progress("  summary    : %s" % root["summary"])
    progress("  evidence   : %s" % ", ".join(e["reference"] for e in diagnosis["evidence"]))
    for note in diagnosis.get("investigation", {}).get("calibration_notes", []):
        progress("  confidence : %s" % note[:200])  # why the code capped (or kept) the model's own number
    if diagnosis.get("review"):
        progress("  reviewer   : %s" % diagnosis["review"]["verdict"][:200])
    progress("--- PROPOSED ACTION (dry run: nothing has changed yet) ---")
    progress("  action : %s on %s %s" % (proposal["action"], proposal.get("target"), proposal.get("parameters") or ""))
    progress("  reason : %s" % proposal["reason"])
    progress("  would  : %s" % plan.get("effect", plan.get("reason")))
    progress("  undo   : %s" % plan.get("undo", "n/a"))


def _ask_human(question):
    # The question goes to stderr so a human sees it even when the JSON on stdout is redirected.
    # No terminal (e.g. a harness piping stdin) means no human: that is a "no", never a "yes".
    try:
        sys.stderr.write(question)
        sys.stderr.flush()
        return input()
    except EOFError:
        print("\n  (no interactive input available: treating as NOT approved)", file=sys.stderr)
        return ""


def _append_transcript(transcript_path, entry):
    if transcript_path:
        with open(transcript_path, "a") as transcript:
            transcript.write(json.dumps(entry, default=str) + "\n")


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_incident(alert_text, incident_id=None, out_dir=None, act=True, auto_approve=False, dry_run=False,
                    review_enabled=None, ask=None):
    """The full Day 2 loop: diagnose, then (unless act=False) dry run -> approve -> act -> verify -> roll back."""
    incident_id = incident_id or "inc-" + time.strftime("%Y%m%d-%H%M%S")
    diagnosis = diagnose(alert_text, incident_id, out_dir, review_enabled=review_enabled)
    if act or dry_run:
        run_dir = _run_dir(incident_id, out_dir)
        diagnosis["action_loop"] = act_on_diagnosis(diagnosis, auto_approve=auto_approve, dry_run=dry_run, ask=ask,
                                                    transcript_path=run_dir / "transcript.jsonl")
        diagnosis["action_loop"]["action_log_entries"] = actions.read_log(incident_id)
        write_outputs(diagnosis, run_dir)  # rewrite JSON and report now that the loop has run
        _log("updated", run_dir, "with the action loop")
    return diagnosis


def watch(poll_seconds=60, error_threshold=0.05, latency_threshold_ms=1500, **loop_options):
    """Detect: poll service health and start an investigation when a threshold is crossed."""
    _log("watching service health every %ds (errors >= %.0f%%, p95 >= %dms)" % (poll_seconds, error_threshold * 100, latency_threshold_ms))
    while True:
        if KILL_SWITCH_FILE.exists():
            _log("KILL_SWITCH present: watch stopped")
            return
        tools.reset_evidence_registry()
        health = tools.get_service_health(5)["services"]
        alerts = [row for row in health if row["status_hint"].startswith(("ERRORS", "SLOW", "NOT_REPORTING"))]
        if alerts:
            worst = alerts[0]
            alert_text = "%s: error ratio %.1f%%, p95 %s ms, status %s" % (
                worst["service"], worst["error_ratio"] * 100, worst["p95_latency_ms"], worst["status_hint"])
            _log("ALERT ->", alert_text)
            print(json.dumps(handle_incident(alert_text, **loop_options), indent=2, default=str))
            return
        time.sleep(poll_seconds)


def main():
    parser = argparse.ArgumentParser(description="Incident Zero on-call agent")
    parser.add_argument("alert", nargs="?", help="alert text, e.g. 'Error rate above 5%% on frontend'")
    parser.add_argument("--incident-id")
    parser.add_argument("--out", help="directory for transcript/diagnosis/report (default runs/)")
    parser.add_argument("--watch", action="store_true", help="poll metrics and investigate when an alert fires")
    parser.add_argument("--dry-run", action="store_true", help="show exactly what would change, never act")
    parser.add_argument("--no-act", action="store_true", help="diagnose only (no proposal loop)")
    parser.add_argument("--yes", action="store_true",
                        help="UNATTENDED runs only: auto-approve the proposed action. Recorded as such in the report and action log.")
    parser.add_argument("--no-review", action="store_true", help="skip the reviewer call (saves one LLM call)")
    parser.add_argument("--demo-hallucination", action="store_true",
                        help="DEMO ONLY: plant one fake evidence reference to show the guard rejecting it")
    args = parser.parse_args()
    if args.demo_hallucination:
        os.environ["DEMO_HALLUCINATION"] = "1"
    if args.yes:
        _log("WARNING: --yes auto-approves actions. Use only for unattended runs; every action is still logged.")
    options = dict(out_dir=args.out, act=not args.no_act, auto_approve=args.yes, dry_run=args.dry_run,
                   review_enabled=not args.no_review)
    if args.watch:
        watch(**options)
        return
    if not args.alert:
        parser.error("give an alert text or --watch")
    result = handle_incident(args.alert, incident_id=args.incident_id, **options)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
