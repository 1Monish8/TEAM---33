"""Container health and log tools for the on-call agent.

Reads only Docker state and container logs. The flag services are blocked,
so the agent can never read feature-flag settings to diagnose.
"""
import json
import subprocess

BLOCKED = {"flagd", "flagd-ui"}


def _run(cmd, timeout=30):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def _is_problem(status: str) -> bool:
    s = status.lower()
    return ("unhealthy" in s or "exited" in s or "restarting" in s
            or "dead" in s or "paused" in s)


def container_health():
    """Status, restarts, OOM kills, CPU and memory for each container.
    Problem containers come first. Returns a list of short dicts."""
    ps_lines = _run(["docker", "ps", "-a", "--format", "{{json .}}"]).splitlines()
    stats_lines = _run(["docker", "stats", "--no-stream",
                        "--format", "{{json .}}"]).splitlines()

    stats = {}
    for line in stats_lines:
        if line.strip().startswith("{"):
            s = json.loads(line)
            stats[s["Name"]] = s

    rows = []
    for line in ps_lines:
        if not line.strip().startswith("{"):
            continue
        c = json.loads(line)
        name = c["Names"]
        if name in BLOCKED:
            continue
        info = _run(["docker", "inspect", "-f",
                     "{{.RestartCount}} {{.State.OOMKilled}}", name]).split()
        s = stats.get(name, {})
        rows.append({
            "service": name,
            "status": c["Status"],
            "problem": _is_problem(c["Status"]),
            "restarts": info[0] if info else "?",
            "oom_killed": info[1] if len(info) > 1 else "?",
            "cpu": s.get("CPUPerc", "-"),
            "mem": s.get("MemPerc", "-"),
        })
    rows.sort(key=lambda r: (not r["problem"], r["service"]))
    return rows


def service_logs(service: str, tail: int = 200):
    """Last error-like log lines for one service (at most 25 lines)."""
    if service in BLOCKED:
        return ["access to this service is not allowed"]
    out = _run(["docker", "logs", "--tail", str(tail), service])
    keys = ("error", "fail", "exception", "warn", "timeout", "refused", "panic")
    hits = [l.strip()[:300] for l in out.splitlines()
            if any(k in l.lower() for k in keys)]
    return hits[-25:] or [f"no error lines in the last {tail} log lines"]


if __name__ == "__main__":
    print(json.dumps(container_health()[:5], indent=2))
    print(service_logs("checkout")[:5])