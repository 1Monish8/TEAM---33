# practice/faultctl.py — STAND-IN for the organisers' faultctl, used only to practise.
# It injects a practice incident and resets everything. It is NOT part of the agent:
# agent.py and tools.py never import this folder (the answers live in incidents.json).
#
#   python practice/faultctl.py list
#   python practice/faultctl.py inject payment-failure
#   python practice/faultctl.py reset
#   python practice/faultctl.py status
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent
INCIDENTS = json.loads((HERE / "incidents.json").read_text())["incidents"]
STATE_FILE = HERE / ".faultctl_state.json"
FLAG_UI_URL = os.environ.get("FLAG_UI_URL", "http://localhost:8080/feature/api")
DEMO_DIR = pathlib.Path(os.environ.get("DEMO_DIR", HERE.parent.parent / "opentelemetry-demo"))
PRISTINE_FLAGS_FILE = DEMO_DIR / "src" / "flagd" / "demo.flagd.json"


def _docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)


def _load_state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"active": []}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _all_off(flags_document):
    # normalise to "nothing injected": every flag's default and every targeting branch -> off
    for flag in flags_document["flags"].values():
        if "off" in flag["variants"]:
            flag["defaultVariant"] = "off"
        targeting_if = flag.get("targeting", {}).get("if")
        if targeting_if:
            flag["targeting"]["if"] = [targeting_if[0]] + ["off"] * (len(targeting_if) - 1)
    return flags_document


def _write_flags(set_variants):
    # same thing the Flag UI does when a human clicks: replace the whole flag document.
    # Always starts from "everything off", so reset is deterministic even though the live file changes.
    flags_document = _all_off(json.loads(PRISTINE_FLAGS_FILE.read_text()))
    for flag_name, variant in set_variants.items():
        flag = flags_document["flags"][flag_name]
        if flag.get("targeting", {}).get("if"):
            flag["targeting"]["if"][1] = variant  # e.g. productCatalogFailure: fail only the targeted product
        else:
            flag["defaultVariant"] = variant
    response = requests.post(FLAG_UI_URL + "/write", json={"data": flags_document}, timeout=15)
    response.raise_for_status()


def inject(name):
    incident = INCIDENTS[name]
    state = _load_state()
    kind = incident["kind"]
    if kind == "flag":
        active_flags = {i["flag"]: i["variant"] for i in (INCIDENTS[n] for n in state["active"]) if i["kind"] == "flag"}
        active_flags[incident["flag"]] = incident["variant"]
        _write_flags(active_flags)
    elif kind == "docker_stop":
        _docker("stop", incident["container"])
    elif kind == "restart_loop":
        # a detached loop that restarts the container every N seconds -> uptime keeps resetting
        loop = subprocess.Popen(
            ["bash", "-c", "while true; do docker restart -t 1 %s >/dev/null 2>&1; sleep %d; done"
             % (incident["container"], incident["every_seconds"])],
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        state.setdefault("loop_pids", []).append(loop.pid)
    elif kind == "cpu_starve":
        _docker("update", "--cpus", incident["cpus"], incident["container"])
    else:
        raise SystemExit("unknown incident kind " + kind)
    state["active"].append(name)
    state.setdefault("injected_at", {})[name] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_state(state)
    print("injected", name)


# Some flag-driven faults leave residue after the flag is turned off: adHighCpu's CPU-burning threads keep
# running (we measured ad at ~20x its normal CPU three hours after the flag went off), and leaks keep their
# memory. "Reset everything" therefore restarts those services, the way the organisers' faultctl promises to.
RESIDUE_RESTART = {"adHighCpu": "ad", "adManualGc": "ad", "recommendationCacheFailure": "recommendation",
                   "emailMemoryLeak": "email"}


def reset():
    state = _load_state()
    for name in state.get("active", []):
        incident = INCIDENTS.get(name, {})
        container = RESIDUE_RESTART.get(incident.get("flag"))
        if container:
            _docker("restart", container)
    for pid in state.get("loop_pids", []):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    _write_flags({})
    for incident in INCIDENTS.values():
        if incident["kind"] in ("docker_stop", "restart_loop"):
            _docker("start", incident["container"])
        if incident["kind"] == "cpu_starve":
            _docker("update", "--cpus", "0", incident["container"])
    _save_state({"active": []})
    print("reset: all flags off, containers started, CPU limits removed")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    if command == "list":
        for name, incident in INCIDENTS.items():
            print(name.ljust(28), incident["kind"])
    elif command == "inject":
        inject(sys.argv[2])
    elif command == "reset":
        reset()
    elif command == "status":
        print(json.dumps(_load_state(), indent=2))
    else:
        raise SystemExit("usage: faultctl.py list|inject <name>|reset|status")


if __name__ == "__main__":
    main()
