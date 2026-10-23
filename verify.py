# verify.py — did the approved action actually fix it? Judged against numbers captured BEFORE acting.
#
# The brief: "Execute the approved action, then check health metrics to confirm the system recovered.
# If it did not, roll back and escalate." Verification here is a comparison, never a hope:
#   * snapshot() captures the target service's numbers before we act.
#   * confirm_recovery() waits for fresh metrics, then compares. It returns recovered=True / False, or
#     None for "cannot tell" (a service that is not reporting is not the same as one that did not recover).
import subprocess
import time

import config
import tools

# Prometheus scrapes every 60 s and the SDKs export every 60 s, so a check sooner than this reads the
# pre-action window and reports a false failure. After WAIT_SECONDS we read a 2-minute window, which by then
# holds (almost) only post-action data; a 5-minute window would still be dominated by the old errors.
WAIT_SECONDS = 120
RECHECK_SECONDS = 60
VERIFY_WINDOW_MINUTES = 2


def snapshot(service, window_minutes=5):
    """Capture the numbers we will judge recovery by. Call BEFORE acting."""
    health = tools.get_service_health(window_minutes=window_minutes)
    state = _container_state(service)
    for row in health["services"]:
        if row["service"] == service:
            return {"service": service, "reporting": not row["status_hint"].startswith("NOT_REPORTING"),
                    "error_ratio": row["error_ratio"], "p95_latency_ms": row["p95_latency_ms"],
                    "deviation_score": row["deviation_score"], "status_hint": row["status_hint"],
                    "container_state": state, "captured_at": health["window"]["to"],
                    "window_minutes": window_minutes, "pipeline_warning": health.get("pipeline_warning")}
    # not in the span metrics at all: either it is down, or it is an uninstrumented component (redis, kafka)
    return {"service": service, "reporting": False, "error_ratio": None, "p95_latency_ms": None, "deviation_score": None,
            "status_hint": "no span metrics for this service", "container_state": state,
            "captured_at": health["window"]["to"], "window_minutes": window_minutes,
            "pipeline_warning": health.get("pipeline_warning")}


def confirm_recovery(before, wait_seconds=WAIT_SECONDS, kill_switch_file=None, progress=print):
    """Wait for metrics to catch up, compare with `before`; one re-check before calling it a failure."""
    checks = []
    for attempt, wait in enumerate((wait_seconds, RECHECK_SECONDS), start=1):
        if _interruptible_sleep(wait, kill_switch_file, progress, attempt):
            return {"recovered": None, "before": before, "checks": checks,
                    "verdict": "halted: KILL_SWITCH appeared during verification, so recovery was not judged"}
        after = snapshot(before["service"], window_minutes=VERIFY_WINDOW_MINUTES)
        recovered, verdict = _judge(before, after)
        checks.append({"attempt": attempt, "after": after, "recovered": recovered, "verdict": verdict})
        progress("  verification check %d: %s" % (attempt, verdict))
        if recovered is not False:  # True, or None (cannot tell): a re-check will not change "cannot tell"
            break
    return {"recovered": checks[-1]["recovered"], "before": before, "after": checks[-1]["after"],
            "checks": checks, "verdict": checks[-1]["verdict"]}


def _judge(before, after):
    service = before["service"]
    if after.get("pipeline_warning"):
        return None, "cannot tell: span metrics are unavailable (%s)" % after["pipeline_warning"][:80]
    if after["container_state"] not in (None, "running"):
        return False, "%s container is %s after the action" % (service, after["container_state"])
    if before["deviation_score"] is None and after["deviation_score"] is None:
        # uninstrumented component (e.g. valkey-cart): all we can say is whether its container is up
        if after["container_state"] == "running" and before["container_state"] != "running":
            return True, "%s container was %s, is now running (no span metrics exist for it)" % (service, before["container_state"])
        return None, "cannot tell: %s has no span metrics, and its container state did not change" % service
    if not after["reporting"]:
        return False, "%s is still not reporting any spans" % service
    if not before["reporting"]:
        recovered = (after["error_ratio"] or 0) <= 0.05
        return recovered, "%s was not reporting; now reporting with error ratio %.4f" % (service, after["error_ratio"] or 0)
    before_dev, after_dev = before["deviation_score"] or 0, after["deviation_score"] or 0
    if before_dev < 1.0:
        return None, ("cannot tell: %s barely deviated from its baseline before acting (deviation %.2f), so there is "
                      "no symptom on it to watch disappear" % (service, before_dev))
    recovered = after_dev <= max(before_dev * 0.3, 0.5)
    return recovered, ("deviation from its own baseline %.2f -> %.2f (error ratio %s -> %s, p95 %s -> %s ms)"
                       % (before_dev, after_dev, _fmt(before["error_ratio"]), _fmt(after["error_ratio"]),
                          before["p95_latency_ms"], after["p95_latency_ms"]))


def _fmt(value):
    return "n/a" if value is None else "%.4f" % value


def _interruptible_sleep(seconds, kill_switch_file, progress, attempt):
    progress("  waiting %ds for fresh metrics before verification check %d (Prometheus lags up to ~2 min)" % (seconds, attempt))
    deadline = time.time() + seconds
    while time.time() < deadline:
        if kill_switch_file is not None and kill_switch_file.exists():
            return True
        time.sleep(1)
    return False


def _container_state(name):
    try:
        output = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", name],
                                capture_output=True, text=True, timeout=15, cwd=config.REPO_ROOT).stdout.strip()
        return output or None
    except Exception:
        return None
