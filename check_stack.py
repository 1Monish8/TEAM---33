# check_stack.py — pre-flight: is everything the agent depends on actually healthy right now?
# Operator tooling (used by run_all.py, run_day1.sh and demo.sh). The agent never imports or calls it.
#
#   python check_stack.py          # report only
#   python check_stack.py --fix    # also restart otel-collector if span metrics have frozen (seen after ~3 h uptime)
import json
import subprocess
import sys
import time

import requests

import config

DEMO_PROJECT = "opentelemetry-demo"
SPAN_METRICS_MAX_AGE = 180


def _prometheus_scalar(promql):
    try:
        rows = requests.get(config.PROMETHEUS_BASE_URL + "/api/v1/query", params={"query": promql}, timeout=10).json()["data"]["result"]
        return float(rows[0]["value"][1]) if rows else None
    except Exception:
        return None


def span_metrics_age():
    age = _prometheus_scalar("time() - max(max_over_time(timestamp(traces_span_metrics_calls_total)[10m:30s]))")
    return None if age is None else int(age)


def checks():
    results = []

    def add(name, ok, detail):
        results.append({"check": name, "ok": ok, "detail": detail})

    states = subprocess.run(["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=" + DEMO_PROJECT,
                             "--format", "{{.Names}} {{.State}}"], capture_output=True, text=True, timeout=20).stdout.split("\n")
    states = [line.split() for line in states if line.strip()]
    down = [name for name, state in states if state != "running"]
    add("demo containers running", bool(states) and not down, "%d/%d running%s" % (len(states) - len(down), len(states),
                                                                                    ("; not running: " + ", ".join(down)) if down else ""))
    try:
        code = requests.get("http://localhost:8080/", timeout=10).status_code
        add("web store (frontend-proxy :8080)", code == 200, "HTTP %d" % code)
    except Exception as error:
        add("web store (frontend-proxy :8080)", False, str(error)[:80])
    age = span_metrics_age()
    add("span metrics fresh in Prometheus", age is not None and age <= SPAN_METRICS_MAX_AGE,
        "newest sample %ss old" % age if age is not None else "NO span metrics in the last 10 min (collector export failing?)")
    container_age = _prometheus_scalar("time() - max(timestamp(container_uptime_seconds))")
    add("container metrics fresh", container_age is not None and container_age <= SPAN_METRICS_MAX_AGE,
        "newest sample %ss old" % (int(container_age) if container_age is not None else "?"))
    try:
        services = requests.get(config.JAEGER_BASE_URL + "/api/v3/services", timeout=10).json().get("services") or []
        add("Jaeger v3 API", len(services) > 5, "%d services reporting traces" % len(services))
    except Exception as error:
        add("Jaeger v3 API", False, str(error)[:80])
    try:
        indices = requests.get(config.OPENSEARCH_BASE_URL + "/_cat/indices/otel-logs-*?format=json", timeout=10).json()
        add("OpenSearch logs", bool(indices), "%s (%s)" % (config.OPENSEARCH_BASE_URL, ", ".join(i["index"] for i in indices)[:80]))
    except Exception as error:
        add("OpenSearch logs", False, "%s: %s" % (config.OPENSEARCH_BASE_URL, str(error)[:60]))
    kill_switch = config.REPO_ROOT / "KILL_SWITCH"
    add("no KILL_SWITCH file", not kill_switch.exists(), "present: the agent will refuse to act" if kill_switch.exists() else "absent")
    state_file = config.REPO_ROOT / "practice" / ".faultctl_state.json"
    active = json.loads(state_file.read_text()).get("active", []) if state_file.exists() else []
    add("no practice fault left injected", not active, ", ".join(active) if active else "none")
    add("LLM key configured", bool(config.LLM_API_KEY), "model %s, fallback %s" % (config.LLM_MODEL, config.LLM_MODEL_FALLBACK))
    return results


def ensure_span_metrics(wait_seconds=150, log=print):
    """--fix: the collector's Prometheus export has been seen to start failing after ~3 h, after which span metrics
    stop. Restarting the collector (a pipe: Jaeger and Prometheus keep their data) brings them back."""
    age = span_metrics_age()
    if age is not None and age <= SPAN_METRICS_MAX_AGE:
        return True
    log("span metrics stale (%s): restarting otel-collector" % ("none" if age is None else "%ss" % age))
    subprocess.run(["docker", "restart", "otel-collector"], capture_output=True, timeout=90)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(10)
        age = span_metrics_age()
        if age is not None and age <= SPAN_METRICS_MAX_AGE:
            log("span metrics back (newest sample %ss old)" % age)
            return True
    log("span metrics still missing after the collector restart")
    return False


def main():
    if "--fix" in sys.argv:
        ensure_span_metrics()
    results = checks()
    for result in results:
        print("%s  %-34s %s" % ("PASS" if result["ok"] else "FAIL", result["check"], result["detail"]))
    failed = [r for r in results if not r["ok"]]
    print("\n%s" % ("ALL GREEN" if not failed else "%d check(s) failing" % len(failed)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
