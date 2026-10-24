# ui_server.py: the control room. A local web UI over the REAL project (python standard library only).
#
#   .venv/bin/python ui_server.py            then open http://localhost:8765
#
# It does not re-implement anything: it runs agent.py, faultctl.py, mentor.py, check_stack.py, the tests and the proof
# as subprocesses and streams what they print. Approve / Reject in the browser is typed into agent.py's own y/N
# prompt, so the UI goes through exactly the same four safety gates as the terminal. Health and evaluation views
# call the same read-only functions the agent uses. Listens on 127.0.0.1 only.
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "practice"))
import calibration  # noqa: E402
import mentor  # noqa: E402
import tools  # noqa: E402

PY = sys.executable
PORT = int(os.environ.get("UI_PORT", "8765"))
UI_DIR = REPO / "ui"
UI_RUNS = REPO / "reports" / "ui"
SCORES = UI_RUNS / "mentor_scores.jsonl"
KILL_SWITCH = REPO / "KILL_SWITCH"
FAULT_STATE = REPO / "practice" / ".faultctl_state.json"
INCIDENTS = json.loads((REPO / "practice" / "incidents.json").read_text())["incidents"]
ANSI = re.compile(r"\x1b\[[0-9;]*m")
REF = re.compile(r'"(?:ref|reference)":\s*"((?:trace|log|metric)-\d+)"')
try:  # the repo owner, even when this server was started without a login environment
    import pwd
    OPERATOR = pwd.getpwuid(REPO.stat().st_uid).pw_name
except Exception:
    OPERATOR = os.environ.get("USER") or "operator"

state = {"fault": None}          # what the UI last injected: {"label", "secret", "injected_at"}
jobs = {}
jobs_lock = threading.Lock()
health_lock = threading.Lock()
health_cache = {"at": 0, "data": None}


# ---------------------------------------------------------------- jobs: a subprocess whose output is streamed
class Job:
    def __init__(self, kind, command, transcript=None, out_dir=None, incident_id=None, stream_stdout=True):
        self.id = "%s-%d" % (kind, int(time.time() * 1000))
        self.kind, self.command, self.transcript, self.out_dir, self.incident_id = kind, command, transcript, out_dir, incident_id
        self.events, self.lock, self.returncode, self.started = [], threading.Lock(), None, time.time()
        self.stdout_text = []
        # the action log records who approved: the person at this laptop, through the control room
        operator = "%s (control room)" % OPERATOR
        self.proc = subprocess.Popen(command, cwd=REPO, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=dict(os.environ, PYTHONUNBUFFERED="1", LOGNAME=operator, USER=operator))
        threading.Thread(target=self._read, args=(self.proc.stderr, True), daemon=True).start()
        threading.Thread(target=self._read, args=(self.proc.stdout, stream_stdout), daemon=True).start()
        if transcript:
            threading.Thread(target=self._tail_transcript, daemon=True).start()
        threading.Thread(target=self._wait, daemon=True).start()

    def emit(self, kind, **data):
        with self.lock:
            data.update(seq=len(self.events), type=kind, t=round(time.time() - self.started, 1))
            self.events.append(data)

    def _read(self, pipe, stream):
        partial = ""
        while True:
            chunk = os.read(pipe.fileno(), 4096)
            if not chunk:
                break
            text = chunk.decode("utf-8", "replace")
            if not stream:
                self.stdout_text.append(text)
                continue
            partial += text
            *lines, partial = partial.split("\n")
            for line in lines:
                self.emit("log", text=ANSI.sub("", line))
            # agent.py asks without a newline: detect its prompts in the unfinished line
            if "Approve this action? [y/N]" in partial:
                self.emit("prompt", prompt="approve", text=partial.strip())
                partial = ""
            elif "Name the flag to set for" in partial:
                self.emit("prompt", prompt="flag", text=partial.strip())
                partial = ""
        if partial.strip() and stream:
            self.emit("log", text=ANSI.sub("", partial))

    def _tail_transcript(self):
        position, path = 0, pathlib.Path(self.transcript)
        while True:
            alive = self.proc.poll() is None
            if path.exists():
                with path.open() as handle:
                    handle.seek(position)
                    for line in handle:
                        if not line.endswith("\n"):
                            break
                        position += len(line.encode("utf-8"))
                        try:
                            self.emit("step", **_compact_step(json.loads(line)))
                        except ValueError:
                            pass
            if not alive:
                return
            time.sleep(0.4)

    def _wait(self):
        self.returncode = self.proc.wait()
        time.sleep(0.9)  # let the readers and the transcript tail drain
        diagnosis = None
        if self.out_dir and self.incident_id:
            path = pathlib.Path(self.out_dir) / self.incident_id / "diagnosis.json"
            if path.exists():
                diagnosis = json.loads(path.read_text())
        self.emit("done", returncode=self.returncode, diagnosis=diagnosis)

    def answer(self, text):
        if self.proc.poll() is None:
            self.proc.stdin.write((text + "\n").encode())
            self.proc.stdin.flush()
            self.emit("answer", text=text or "(blank)")

    def running(self):
        return self.proc.poll() is None


def _compact_step(entry):
    kind = entry.get("event")
    if kind == "tool":
        result = json.dumps(entry.get("result"), default=str)
        return {"step": "tool", "iteration": entry.get("iteration"), "tool": entry.get("tool"),
                "arguments": entry.get("arguments"), "refs": sorted(set(REF.findall(result)), key=lambda r: (r.split("-")[0], int(r.split("-")[1]))),
                "result": result[:6000], "truncated": len(result) > 6000}
    if kind == "llm_reply":
        return {"step": "llm", "iteration": entry.get("iteration"), "model": entry.get("model"),
                "tokens": (entry.get("usage") or {}).get("total_tokens"), "tool_calls": entry.get("tool_calls"),
                "text": (entry.get("text") or "")[:600]}
    if kind == "submit":
        arguments = entry.get("arguments") or {}
        return {"step": "submit", "iteration": entry.get("iteration"), "accepted": entry["result"].get("accepted"),
                "reason": entry["result"].get("reason"), "root": arguments.get("root_cause_service"),
                "status": arguments.get("status"), "confidence": arguments.get("confidence"),
                "refs": [e.get("ref") for e in arguments.get("evidence") or []]}
    if kind in ("review", "action_loop", "diagnosis", "alert", "kill_switch", "tool_call_rejected"):
        return dict(entry, step=kind)
    return {"step": kind or "other"}


def start_job(kind, command, **options):
    with jobs_lock:
        busy = [j for j in jobs.values() if j.kind == kind and j.running()]
        if busy:
            raise RuntimeError("a %s is already running" % kind)
        job = Job(kind, command, **options)
        jobs[job.id] = job
        return job


# ---------------------------------------------------------------- faults
def _run(command, timeout=180):
    done = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=timeout)
    return {"ok": done.returncode == 0, "output": ANSI.sub("", (done.stdout + done.stderr).strip())}


def fault_state():
    active = []
    if FAULT_STATE.exists():
        active = json.loads(FAULT_STATE.read_text()).get("active", [])
    secret = mentor.SECRET.exists()
    return {"known_active": active, "secret_active": secret, "ui": state["fault"]}


def inject_known(name):
    if name not in INCIDENTS:
        raise ValueError("unknown incident " + name)
    if mentor.SECRET.exists():
        _run([PY, "practice/mentor.py", "undo"])
    result = _run([PY, "practice/faultctl.py", "inject", name])
    if result["ok"]:
        state["fault"] = {"label": name, "secret": False, "injected_at": time.time(), "alert": INCIDENTS[name]["alert"]}
    return result


def inject_secret():
    _run([PY, "practice/faultctl.py", "reset"])
    result = _run([PY, "practice/mentor.py", "inject"])
    if result["ok"]:
        state["fault"] = {"label": "unknown (sealed)", "secret": True, "injected_at": time.time(), "alert": mentor.ALERT}
    return result


def reset_all():
    outputs = []
    if mentor.SECRET.exists():
        outputs.append(_run([PY, "practice/mentor.py", "undo"])["output"])
    outputs.append(_run([PY, "practice/faultctl.py", "reset"])["output"])
    state["fault"] = None
    return {"ok": True, "output": "\n".join(outputs)}


def reveal_secret():
    if not mentor.SECRET.exists():
        raise ValueError("no secret fault is injected")
    secret = json.loads(mentor.SECRET.read_text())
    candidates = [p for p in REPO.glob("reports/*/*/diagnosis.json") if p.stat().st_mtime >= secret["injected_at"]]
    candidates += [p for p in REPO.glob("runs/*/diagnosis.json") if p.stat().st_mtime >= secret["injected_at"]]
    result = {"how": secret["how"], "accept": secret["accept"], "injected_at": secret["injected_at"], "diagnosis": None}
    if candidates:
        # a blind test counts the FIRST answer after the injection; later runs cannot replace it
        latest = min(candidates, key=lambda p: p.stat().st_mtime)
        diagnosis = json.loads(latest.read_text())
        named = (diagnosis.get("root_cause") or {}).get("service")
        if diagnosis.get("status") == "escalated":
            verdict = "ESCALATED"
        elif named in secret["accept"]:
            verdict = "CORRECT"
        elif diagnosis.get("confidence_label") == "high":
            verdict = "CONFIDENTLY WRONG"
        else:
            verdict = "WRONG"
        result.update(diagnosis={"service": named, "status": diagnosis.get("status"), "confidence": diagnosis.get("confidence"),
                                 "label": diagnosis.get("confidence_label"), "path": str(latest.relative_to(REPO)),
                                 "summary": (diagnosis.get("root_cause") or {}).get("summary")}, verdict=verdict)
        scored = SCORES.exists() and any(json.loads(l).get("injected_at") == secret["injected_at"] for l in SCORES.read_text().splitlines() if l.strip())
        if not scored:
            UI_RUNS.mkdir(parents=True, exist_ok=True)
            with SCORES.open("a") as handle:
                handle.write(json.dumps({"injected_at": secret["injected_at"], "how": secret["how"], "accept": secret["accept"],
                                         "said": named, "verdict": verdict, "confidence": diagnosis.get("confidence"),
                                         "at": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
    return result


# ---------------------------------------------------------------- read-only views
def health(force=False):
    with health_lock:
        if not force and health_cache["data"] and time.time() - health_cache["at"] < 8:
            return health_cache["data"]
        tools.reset_evidence_registry()
        service = tools.get_service_health(5)
        containers = tools.get_container_health(15)
        dependencies = tools.get_dependency_health(10)
        data = {"at": time.strftime("%H:%M:%S"), "services": service.get("services", []),
                "pipeline_warning": service.get("pipeline_warning"),
                "containers": containers.get("containers_with_problems", []),
                "dependencies": dependencies.get("problems", []),
                "kafka": dependencies.get("kafka"), "database": dependencies.get("database")}
        health_cache.update(at=time.time(), data=data)
        return data


def runs_list():
    found = list(REPO.glob("reports/*/*/diagnosis.json")) + list(REPO.glob("runs/*/diagnosis.json"))
    rows = []
    for path in sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)[:200]:
        try:
            d = json.loads(path.read_text())
        except ValueError:
            continue
        rows.append({"path": str(path.relative_to(REPO)), "folder": path.parent.parent.name, "incident": path.parent.name,
                     "time": time.strftime("%m-%d %H:%M", time.localtime(path.stat().st_mtime)), "status": d.get("status"),
                     "service": (d.get("root_cause") or {}).get("service"), "confidence": d.get("confidence"),
                     "label": d.get("confidence_label"), "outcome": (d.get("action_loop") or {}).get("outcome")})
    return rows


def run_detail(relative):
    path = (REPO / relative).resolve()
    if REPO not in path.parents or path.name != "diagnosis.json":
        raise ValueError("not a diagnosis file")
    report = path.with_name("report.md")
    return {"diagnosis": json.loads(path.read_text()), "report": report.read_text() if report.exists() else ""}


def calibration_view():
    sweeps = sorted(str(p) for p in (REPO / "reports").glob("sweep-*") if p.is_dir())
    rows = calibration.collect(sweeps)
    bands = []
    for name, low, high in calibration.BANDS:
        band = [r for r in rows if low <= r["confidence"] < high]
        correct, escalated = sum(r["correct"] for r in band), sum(r["escalated"] for r in band)
        claimed = len(band) - escalated
        bands.append({"band": name, "range": "%s–%s" % (low, min(high, 1.0)), "runs": len(band), "correct": correct,
                      "escalated": escalated, "wrong": claimed - correct,
                      "accuracy": round(100.0 * correct / claimed) if claimed else None})
    confident_wrong = [r for r in rows if r["confidence"] >= 0.75 and not r["correct"] and not r["escalated"]]
    return {"bands": bands, "rows": rows, "confidently_wrong": len(confident_wrong), "sweeps": [pathlib.Path(s).name for s in sweeps]}


def detection_view():
    latest = {}
    for report in sorted((REPO / "reports").glob("fault-detection-*.md")):
        for line in report.read_text().splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 4 and cells[2] in ("✅", "❌"):
                latest[cells[0]] = {"incident": cells[0], "class": cells[1], "detected": cells[2] == "✅",
                                    "seen": cells[3], "report": report.name}
    return {"rows": list(latest.values())}


def action_log():
    path = REPO / "action_log.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return [{"time": r.get("logged_at"), "incident": r.get("incident_id"), "purpose": r.get("purpose"), "action": r.get("action"),
             "target": r.get("target"), "parameters": r.get("parameters"), "approved": r.get("approved"),
             "approved_by": r.get("approved_by"), "ok": (r.get("result") or {}).get("ok"),
             "reason": (r.get("result") or {}).get("reason")} for r in reversed(rows[-150:])]


def scores():
    if not SCORES.exists():
        return []
    return [json.loads(l) for l in SCORES.read_text().splitlines() if l.strip()][::-1]


def incident_list():
    def category(kind):
        return "application" if kind == "flag" else "combined" if kind == "combo" else "infrastructure"
    return [{"name": name, "kind": i["kind"], "category": category(i["kind"]), "alert": i.get("alert"),
             "expected": i.get("expected_service"), "priority": i.get("priority"),
             "detail": i.get("flag") and "%s → %s" % (i["flag"], i.get("variant")) or i.get("container") or ""}
            for name, i in INCIDENTS.items() if not name.startswith("simulate-")]


# ---------------------------------------------------------------- HTTP
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, (UI_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            routes = {
                "/api/state": lambda: {"kill_switch": KILL_SWITCH.exists(), "fault": fault_state(),
                                       "jobs": [{"id": j.id, "kind": j.kind, "running": j.running()} for j in jobs.values()][-10:]},
                "/api/incidents": incident_list,
                "/api/health": lambda: health(query.get("force") == "1"),
                "/api/runs": runs_list,
                "/api/run": lambda: run_detail(query["path"]),
                "/api/calibration": calibration_view,
                "/api/detection": detection_view,
                "/api/actionlog": action_log,
                "/api/scores": scores,
            }
            if url.path in routes:
                return self._send(200, routes[url.path]())
            match = re.fullmatch(r"/api/job/([\w-]+)/events", url.path)
            if match and match.group(1) in jobs:
                job, since = jobs[match.group(1)], int(query.get("since", 0))
                with job.lock:
                    events = job.events[since:]
                return self._send(200, {"events": events, "running": job.running(), "kind": job.kind,
                                        "incident_id": job.incident_id})
            self._send(404, {"error": "not found"})
        except Exception as error:
            self._send(500, {"error": "%s: %s" % (type(error).__name__, error)})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        try:
            body = self._body()
            if url.path == "/api/fault/inject":
                return self._send(200, inject_known(body["name"]))
            if url.path == "/api/fault/secret":
                return self._send(200, inject_secret())
            if url.path == "/api/fault/reset":
                return self._send(200, reset_all())
            if url.path == "/api/fault/reveal":
                return self._send(200, reveal_secret())
            if url.path == "/api/killswitch":
                if body.get("on"):
                    KILL_SWITCH.write_text("created from the control room at %s\n" % time.strftime("%H:%M:%S"))
                elif KILL_SWITCH.exists():
                    KILL_SWITCH.unlink()
                return self._send(200, {"kill_switch": KILL_SWITCH.exists()})
            if url.path == "/api/agent/run":
                incident_id = "ui-" + time.strftime("%Y%m%d-%H%M%S")
                command = [PY, "-u", "agent.py", body.get("alert") or "Error rate is elevated on the frontend",
                           "--incident-id", incident_id, "--out", str(UI_RUNS)]
                mode = body.get("mode", "act")
                command += {"act": [], "dry_run": ["--dry-run"], "no_act": ["--no-act"]}[mode]
                if not body.get("review", True):
                    command.append("--no-review")
                if body.get("hallucination"):
                    command.append("--demo-hallucination")
                job = start_job("agent", command, transcript=UI_RUNS / incident_id / "transcript.jsonl",
                                out_dir=UI_RUNS, incident_id=incident_id, stream_stdout=False)
                return self._send(200, {"job": job.id, "incident_id": incident_id})
            if url.path == "/api/agent/answer":
                jobs[body["job"]].answer(body.get("text", ""))
                return self._send(200, {"ok": True})
            if url.path == "/api/job/stop":
                job = jobs[body["job"]]
                if job.running():
                    job.proc.terminate()
                return self._send(200, {"ok": True})
            if url.path == "/api/task":
                commands = {"tests": [PY, "-u", "tests/test_offline.py"], "proof": [PY, "-u", "prove_three_ideas.py"],
                            "preflight": [PY, "-u", "check_stack.py", "--fix"]}
                job = start_job("task-" + body["name"], commands[body["name"]])
                return self._send(200, {"job": job.id})
            self._send(404, {"error": "not found"})
        except Exception as error:
            self._send(400, {"error": "%s: %s" % (type(error).__name__, error)})


if __name__ == "__main__":
    UI_RUNS.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("Incident Zero control room: http://localhost:%d   (Ctrl+C to stop)" % PORT, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
