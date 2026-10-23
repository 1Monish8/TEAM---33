# actions.py — the ONLY way this agent changes the demo (our Action API).
#
# Four rules, all enforced in code here rather than promised in a prompt:
#   1. Only allowlisted actions exist. Anything else is refused, whatever the model asks for.
#   2. Nothing executes without approved=True, and only the human approval prompt in agent.py sets it.
#   3. Every call (dry runs, refusals, executions, rollbacks) is appended to action_log.jsonl.
#   4. Every action knows how to undo itself, or says honestly that it cannot.
# Plus: the KILL_SWITCH file blocks every execution, and some containers can never be touched.
#
#   python actions.py describe restart_service payment      # dry run: what WOULD change
#   python actions.py log                                    # show the action log
import getpass
import json
import subprocess
import sys
import time

import requests

import config

ACTION_LOG = config.REPO_ROOT / "action_log.jsonl"
KILL_SWITCH_FILE = config.REPO_ROOT / "KILL_SWITCH"

# The allowlist IS the safety boundary (the brief's Action API: restart a service, toggle a feature flag,
# throttle the load generator, scale a service on Kubernetes).
ALLOWED_ACTIONS = ("restart_service", "toggle_feature_flag", "throttle_load", "scale_service")

# Never restarted by the agent: restarting Jaeger throws away every trace (it stores them in memory), and
# the observability / flag services are the instruments we diagnose with, not the patient.
PROTECTED_CONTAINERS = {"jaeger", "prometheus", "opensearch", "otel-collector", "grafana", "flagd", "flagd-ui",
                        "telemetry-docs", "opamp-server", "load-generator"}
DEMO_COMPOSE_PROJECT = "opentelemetry-demo"
FLAG_UI_URL = config.os.environ.get("FLAG_UI_URL", "http://localhost:8080/feature/api")
PRISTINE_FLAGS_FILE = config.DEMO_DIR / "src" / "flagd" / "demo.flagd.json"
DEFAULT_LOAD_USERS = 5  # the demo's LOCUST_USERS


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _append_to_log(record):
    record["logged_at"] = _now()
    with ACTION_LOG.open("a") as log_file:
        log_file.write(json.dumps(record, default=str) + "\n")


def _demo_container_names():
    output = subprocess.run(["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=" + DEMO_COMPOSE_PROJECT,
                             "--format", "{{.Names}}"], capture_output=True, text=True, timeout=20).stdout
    return set(output.split())


def describe(action, target, parameters=None):
    """Dry run: exactly what WOULD change, and how it would be undone. Executes nothing; always safe."""
    parameters = parameters or {}
    if action not in ALLOWED_ACTIONS:
        return {"ok": False, "reason": "'%s' is not an allowlisted action (allowed: %s)" % (action, ", ".join(ALLOWED_ACTIONS))}

    if action == "restart_service":
        if target in PROTECTED_CONTAINERS:
            return {"ok": False, "reason": "'%s' is protected: the agent never restarts observability, flag or load "
                                           "services (restarting Jaeger would erase every trace)" % target}
        if target not in _demo_container_names():
            return {"ok": False, "reason": "'%s' is not a container of the demo (compose project %s)" % (target, DEMO_COMPOSE_PROJECT)}
        return {"ok": True, "command": "docker restart %s" % target,
                "effect": "Container %s stops and starts (or starts, if it was stopped). Requests to it fail for a few "
                          "seconds; in-memory state (caches, leaked memory) is cleared." % target,
                "reversible": False, "undo": "none needed: a restart changes no configuration"}

    if action == "toggle_feature_flag":
        flag, variant = parameters.get("flag"), parameters.get("variant", "off")
        if not flag:
            return {"ok": False, "needs_flag_name": True,
                    "reason": "toggle_feature_flag needs the flag's name from the on-call human: the agent never reads "
                              "flag configuration, so it cannot know which flag belongs to %s" % target}
        definitions = _flag_definitions()
        if flag not in definitions:
            return {"ok": False, "reason": "no flag named '%s' exists in the demo" % flag}
        if variant not in definitions[flag]["variants"]:
            return {"ok": False, "reason": "flag '%s' has no variant '%s' (it has: %s)"
                                           % (flag, variant, ", ".join(definitions[flag]["variants"]))}
        return {"ok": True, "command": "POST %s/write  (%s -> %s)" % (FLAG_UI_URL, flag, variant),
                "effect": "Sets flag %s to '%s'. WRITE-ONLY: the Flag UI API replaces the whole flag document, so every "
                          "OTHER flag returns to its default. No flag value is read to decide anything." % (flag, variant),
                "reversible": False,
                "undo": "cannot restore the previous variant automatically, because we never read flag state: a failed "
                        "recovery escalates to a human instead"}

    if action == "throttle_load":
        users = int(parameters.get("user_count", 1))
        return {"ok": True, "command": "POST %s/swarm user_count=%d" % (config.LOADGEN_BASE_URL, users),
                "effect": "The load generator drops to %d virtual user(s). Only synthetic traffic changes." % users,
                "reversible": True, "undo": "restore the previous user_count (captured before acting)"}

    # scale_service: the Action API defines it for Kubernetes only. We run Docker Compose; saying so honestly
    # is worth more than faking it.
    return {"ok": False, "reason": "scale_service requires Kubernetes; this deployment is Docker Compose"}


def capture_state(action, target, parameters=None):
    """What to restore if we have to roll back. Captured BEFORE acting."""
    if action == "throttle_load":
        try:
            stats = requests.get(config.LOADGEN_BASE_URL + "/stats/requests", timeout=10).json()
            return {"user_count": stats.get("user_count") or DEFAULT_LOAD_USERS, "state": stats.get("state")}
        except Exception as error:
            return {"user_count": DEFAULT_LOAD_USERS, "note": "could not read load generator (%s)" % error}
    if action == "restart_service":
        inspected = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}} {{.State.StartedAt}}", target],
                                   capture_output=True, text=True, timeout=15).stdout.split()
        return {"container_state": inspected[0] if inspected else None, "started_at": inspected[1] if len(inspected) > 1 else None}
    return {}


def execute(action, target, parameters=None, approved=False, incident_id=None, approved_by=None, purpose="remedy"):
    """Executes ONLY with approved=True and no KILL_SWITCH. Returns a result dict; never raises into the agent."""
    parameters = parameters or {}
    plan = describe(action, target, parameters)
    if KILL_SWITCH_FILE.exists():
        result = {"ok": False, "reason": "KILL_SWITCH present: refusing to act"}
    elif approved is not True:
        # the gate that matters: the agent cannot set this itself; only the human prompt in agent.py does
        result = {"ok": False, "reason": "not approved by a human: refusing to act"}
    elif not plan["ok"]:
        result = {"ok": False, "reason": plan["reason"]}
    else:
        result = _run(action, target, parameters)
    _append_to_log({"incident_id": incident_id, "purpose": purpose, "action": action, "target": target,
                    "parameters": parameters, "approved": approved is True, "approved_by": approved_by,
                    "planned": plan, "result": result})
    return result


def log_refusal_or_dry_run(action, target, parameters, incident_id, outcome, plan=None):
    # dry runs and human rejections are part of the audit trail too
    _append_to_log({"incident_id": incident_id, "purpose": outcome, "action": action, "target": target,
                    "parameters": parameters or {}, "approved": False, "planned": plan or describe(action, target, parameters),
                    "result": {"ok": False, "reason": outcome}})


def _run(action, target, parameters):
    try:
        if action == "restart_service":
            completed = subprocess.run(["docker", "restart", "-t", "10", target], capture_output=True, text=True, timeout=90)
            return {"ok": completed.returncode == 0, "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()[:300]}
        if action == "toggle_feature_flag":
            return _write_flag(parameters["flag"], parameters.get("variant", "off"))
        if action == "throttle_load":
            users = int(parameters.get("user_count", 1))
            response = requests.post(config.LOADGEN_BASE_URL + "/swarm",
                                     data={"user_count": users, "spawn_rate": parameters.get("spawn_rate", max(1, users))},
                                     timeout=15)
            return {"ok": response.status_code == 200, "status_code": response.status_code, "body": response.text[:200]}
    except Exception as error:
        # a failed action must not kill the run; it is reported, verified as not recovered, and escalated
        return {"ok": False, "reason": "%s: %s" % (type(error).__name__, str(error)[:200])}
    return {"ok": False, "reason": "unreachable"}


def _flag_definitions():
    # Which flags EXIST and their allowed variants, from the demo repository's pristine flag file. Used only to
    # validate and build a write; no current flag value is read and nothing here feeds the diagnosis.
    return json.loads(PRISTINE_FLAGS_FILE.read_text())["flags"]


def _write_flag(flag, variant):
    # Same mechanism as practice/faultctl.py and as a human clicking in the Flag UI: post a whole flag document,
    # built from the pristine defaults with ONE flag changed.
    document = {"flags": _flag_definitions()}
    for definition in document["flags"].values():
        if "off" in definition["variants"]:
            definition["defaultVariant"] = "off"
        branches = definition.get("targeting", {}).get("if")
        if branches:
            definition["targeting"]["if"] = [branches[0]] + ["off"] * (len(branches) - 1)
    chosen = document["flags"][flag]
    if chosen.get("targeting", {}).get("if"):
        chosen["targeting"]["if"][1] = variant
    else:
        chosen["defaultVariant"] = variant
    response = requests.post(FLAG_UI_URL + "/write", json={"data": document}, timeout=15)
    return {"ok": response.status_code == 200, "status_code": response.status_code}


def inverse_of(action, target, parameters, before_state):
    """The undo for a failed recovery (the brief: 'If it did not, roll back and escalate'). None = nothing to undo."""
    if action == "throttle_load":
        return ("throttle_load", target, {"user_count": before_state.get("user_count", DEFAULT_LOAD_USERS)})
    return None  # a restart changes no configuration; a flag write cannot be undone without reading flag state


def read_log(incident_id=None):
    if not ACTION_LOG.exists():
        return []
    records = [json.loads(line) for line in ACTION_LOG.read_text().splitlines() if line.strip()]
    return [r for r in records if incident_id is None or r.get("incident_id") == incident_id]


def current_operator():
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "log"
    if command == "describe":
        print(json.dumps(describe(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None,
                                  json.loads(sys.argv[4]) if len(sys.argv) > 4 else None), indent=2))
    elif command == "log":
        for record in read_log():
            print(json.dumps(record))
    else:
        raise SystemExit("usage: actions.py describe <action> <target> ['{json params}'] | log")
