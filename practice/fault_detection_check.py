# practice/fault_detection_check.py: does the TOOL LAYER detect each injectable fault? No LLM involved.
#
# For every incident: inject, wait for the metrics, run the tools the investigation policy would use, check that
# the expected signal appears on the expected component, reset, settle. This proves the evidence the agent needs
# actually exists for each fault class, independently of any model, so it costs no LLM tokens.
#
#   python practice/fault_detection_check.py                      # every incident with a check
#   python practice/fault_detection_check.py currency-frozen ...  # some
import datetime
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import tools  # noqa: E402

FAULTCTL = [sys.executable, str(HERE / "faultctl.py")]
WAIT_SECONDS = 130
SETTLE_SECONDS = 60


def _health(service):
    rows = {r["service"]: r for r in tools.get_service_health(5)["services"]}
    return rows.get(service, {}).get("status_hint", "absent"), [n for n, _ in tools.last_deviation_ranking[:3]]


def _containers():
    return {r["container"]: r["problems"] for r in tools.get_container_health(15)["containers_with_problems"]}


def _dependencies():
    return {(p["service"], p["problem"]) for p in tools.get_dependency_health(10)["problems"]}


def _trace_signatures(service):
    found = tools.search_traces(service, only_errors=True, limit=5, window_minutes=5)
    return " | ".join(line for t in found["traces"] for line in t["deepest_failing"])


def _log_signatures(service):
    return tools.search_logs(service, None, 5, 15, "WARN").get("error_signatures", {})


# incident -> (P-level and fault class, function returning (detected: bool, what was seen: str))
CHECKS = {
    "payment-failure": ("P0 application error", lambda: (lambda h: (h[0].startswith("ERRORS"), "payment %s; top %s" % h))(_health("payment"))),
    "cart-cache-down": ("P0 dependency unavailable / P1 cache", lambda: (lambda c, d: (
        any(p.startswith("NOT_RUNNING") for p in c.get("valkey-cart", [])) and ("valkey-cart", "CACHE_DOWN") in d,
        "valkey-cart %s; deps %s" % (c.get("valkey-cart"), sorted(d))))(_containers(), _dependencies())),
    "currency-stopped": ("P0 container stopped", lambda: (lambda h: (h[0].startswith("NOT_REPORTING: DOWN"), "currency %s; top %s" % h))(_health("currency"))),
    "shipping-restart-loop": ("P0 container restarting", lambda: (lambda c: (
        any(p.startswith(("RESTART_LOOP", "JUST_RESTARTED", "CRASHED")) for p in c.get("shipping", [])), "shipping %s" % c.get("shipping")))(_containers())),
    "checkout-cpu-starved": ("P0 CPU starvation", lambda: (lambda c: (
        any(p.startswith("CPU_LIMITED") for p in c.get("checkout", [])), "checkout %s" % c.get("checkout")))(_containers())),
    "ad-high-cpu": ("P0 CPU saturation", lambda: (lambda c, h: (
        any(p.startswith(("CPU_SPIKE", "CPU_ABOVE")) for p in c.get("ad", [])) or "ad" in h[1][:1],
        "ad %s; top %s" % (c.get("ad"), h[1])))(_containers(), _health("ad"))),
    "email-memory-leak": ("P0 memory exhaustion", lambda: (lambda c: (
        any(p.startswith(("MEMORY", "OOM", "CRASHED", "RESTART")) for p in c.get("email", [])), "email %s" % c.get("email")))(_containers())),
    "recommendation-memory-starved": ("P0 memory exhaustion (infra)", lambda: (lambda c: (
        any(p.startswith(("MEMORY", "OOM", "CRASHED", "RESTART", "JUST_RESTARTED", "NOT_RUNNING")) for p in c.get("recommendation", [])),
        "recommendation %s" % c.get("recommendation")))(_containers())),
    "shipping-slow-dependency": ("P0 slow dependency", lambda: (lambda h: (
        h[0].startswith(("SLOW", "SLOWER")) or "shipping" in h[1][:2], "shipping %s; top %s" % h))(_health("shipping"))),
    "kafka-consumer-dead": ("P0 consumer failure", lambda: (lambda d: (
        ("fraud-detection", "CONSUMER_GROUP_EMPTY") in d or ("fraud-detection", "QUEUE_BACKLOG") in d, "deps %s" % sorted(d)))(_dependencies())),
    # at this stack's ~0.06 orders/s a 3 s-per-message consumer never builds lag: the signal is its slow processing
    "kafka-queue-problems": ("P0 queue backlog / slow consumer", lambda: (lambda d, h: (
        ("fraud-detection", "QUEUE_BACKLOG") in d or h[0].startswith(("SLOW", "SLOWER")),
        "deps %s; fraud-detection %s; top %s" % (sorted(d), h[0][:90], h[1])))(_dependencies(), _health("fraud-detection"))),
    "homepage-flood": ("P0 traffic surge", lambda: (lambda h: (
        "TRAFFIC_SURGE" in h[0], "frontend-proxy %s; top %s" % h))(_health("frontend-proxy"))),
    "product-catalog-db-lock": ("P1 slow queries / locks", lambda: (lambda h: (
        h[0].startswith(("SLOW", "SLOWER", "ERRORS")) or "product-catalog" in h[1][:2], "product-catalog %s; top %s" % h))(_health("product-catalog"))),
    "ad-gc-pauses": ("P2 GC pauses", lambda: (lambda h, c: (
        "ad" in h[1][:2] or bool(c.get("ad")), "ad %s / %s; top %s" % (h[0], c.get("ad"), h[1])))(_health("ad"), _containers())),
    "currency-frozen": ("P2 hung service / partition", lambda: (lambda c: (
        any(p.startswith("PAUSED") for p in c.get("currency", [])), "currency %s" % c.get("currency")))(_containers())),
    "payment-network-partition": ("P1 network / DNS failure", lambda: (lambda c, t: (
        any(p.startswith("NETWORK_DISCONNECTED") for p in c.get("payment", [])),
        "payment %s; checkout traces: %s" % (c.get("payment"), t[:160])))(_containers(), _trace_signatures("checkout"))),
    "deploy-then-payment-failure": ("P1 recent deployment", lambda: (lambda history, h: (
        any(ch["service"] == "payment" for ch in history) and h[0].startswith("ERRORS"),
        "changes %s; payment %s" % ([(ch["service"], ch["change"]) for ch in history][:3], h[0])))(
        tools.get_deploy_history(15)["changes"], _health("payment"))),
    "multi-fault-payment-and-cache": ("P2 multiple faults", lambda: (lambda h, d: (
        h[0].startswith("ERRORS") and ("valkey-cart", "CACHE_DOWN") in d, "payment %s; deps %s" % (h[0], sorted(d))))(
        _health("payment"), _dependencies())),
}


def main():
    names = sys.argv[1:] or list(CHECKS)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    out = HERE.parent / "reports" / ("fault-detection-" + stamp + ".md")
    rows = []
    for name in names:
        level, check = CHECKS[name]
        print("\n=== %s (%s): inject, wait %ds" % (name, level, WAIT_SECONDS), flush=True)
        subprocess.run(FAULTCTL + ["reset"], check=True)
        subprocess.run(FAULTCTL + ["inject", name], check=True)
        time.sleep(WAIT_SECONDS)
        try:
            tools.reset_evidence_registry()
            detected, seen = check()
        except Exception as error:  # a broken check must not stop the matrix
            detected, seen = False, "CHECK ERROR: %s: %s" % (type(error).__name__, str(error)[:120])
        finally:
            subprocess.run(FAULTCTL + ["reset"], check=True)
        rows.append({"incident": name, "class": level, "detected": detected, "seen": seen})
        print(json.dumps(rows[-1]), flush=True)
        lines = ["# Fault detection check (tool layer, no LLM): %s" % stamp, "",
                 "| incident | fault class | detected by the tools | what the tools reported |", "|---|---|---|---|"]
        lines += ["| %s | %s | %s | %s |" % (r["incident"], r["class"], "✅" if r["detected"] else "❌",
                                              r["seen"].replace("|", "/")[:220]) for r in rows]
        lines += ["", "Detected %d of %d." % (sum(r["detected"] for r in rows), len(rows))]
        out.write_text("\n".join(lines) + "\n")
        if name != names[-1]:
            time.sleep(SETTLE_SECONDS)
    print("\nwrote", out)


if __name__ == "__main__":
    main()
