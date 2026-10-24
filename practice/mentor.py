# practice/mentor.py: play the mentor. Breaks the shop with a RANDOM fault you do not know, the way a mentor would
# (a feature flag through the Flag UI, or a plain docker command on a random service), keeps the answer sealed,
# then scores the agent's diagnosis against it.
#
#   python practice/mentor.py inject      # pick and inject a secret fault; prints only the alert
#   (wait 2 minutes, then run the agent: the command is printed)
#   python practice/mentor.py reveal      # what was broken, what the agent said, CORRECT / ESCALATED / WRONG
#   python practice/mentor.py undo        # put the shop back exactly as it was
#
# Never imported by the agent: the answer lives in practice/.mentor_secret.json (git-ignored) until you reveal it.
import datetime
import json
import pathlib
import random
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import faultctl  # noqa: E402  (its Flag UI writer and docker helpers: the same tools a mentor has)

SECRET = HERE / ".mentor_secret.json"
REPORTS = HERE.parent / "reports" / "mentor"
ALERT = "Users report errors or slowness in the shop; the on-call alert fired on the frontend"

# application faults: the demo's own fault flags (a mentor flips these in the Flag UI at localhost:8080/feature)
FLAG_FAULTS = [
    # flag, variant, services that count as the right answer
    ("adFailure", "on", ["ad"]),                               # never practised
    ("paymentFailure", "50%", ["payment"]),
    ("paymentUnreachable", "on", ["payment"]),
    ("cartFailure", "50%", ["cart", "valkey-cart"]),
    ("productCatalogFailure", "on", ["product-catalog"]),
    ("productCatalogLockContention", "on", ["product-catalog", "astronomy-db"]),
    ("recommendationCacheFailure", "on", ["recommendation"]),
    ("adHighCpu", "on", ["ad"]),
    ("adManualGc", "on", ["ad"]),
    ("emailMemoryLeak", "1000x", ["email"]),
    ("kafkaQueueProblems", "3sec", ["fraud-detection", "kafka"]),
    ("kafkaConsumerDead", "on", ["fraud-detection", "kafka"]),
    ("loadGeneratorFloodHomepage", "on", ["frontend", "frontend-proxy", "load-generator"]),
    ("intlShippingSlowdown", "10sec", ["shipping"]),
]
# infrastructure faults: plain docker commands on a random victim (most of these pairs were never practised)
DOCKER_KINDS = ["stop", "pause", "cpu_starve", "network_disconnect"]
VICTIMS = ["ad", "cart", "checkout", "currency", "email", "fraud-detection", "accounting", "payment",
           "product-catalog", "quote", "recommendation", "shipping", "valkey-cart", "kafka", "astronomy-db"]


def _variant_exists(flag, variant):
    flags = json.loads(faultctl.PRISTINE_FLAGS_FILE.read_text())["flags"]
    return flag in flags and variant in flags[flag]["variants"]


def _docker_command(kind, victim):
    return {"stop": ["stop", victim], "pause": ["pause", victim], "cpu_starve": ["update", "--cpus", "0.05", victim],
            "network_disconnect": ["network", "disconnect", faultctl.DEMO_NETWORK, victim]}[kind]


def inject():
    if SECRET.exists():
        sys.exit("A secret fault is already injected. Run: python practice/mentor.py reveal   (then undo)")
    if subprocess.run(["pgrep", "-f", "run_all.py|fault_detection_check.py|demo.sh"], capture_output=True).stdout:
        sys.exit("A practice run is active and would clash. Stop it first.")
    faultctl.reset()  # start from a clean shop, like the hidden test does
    if random.random() < 0.5:
        flag, variant, accept = random.choice([f for f in FLAG_FAULTS if _variant_exists(f[0], f[1])])
        faultctl._write_flags({flag: variant})
        secret = {"how": "Flag UI: %s -> %s" % (flag, variant), "kind": "flag", "flag": flag, "accept": accept}
    else:
        kind, victim = random.choice(DOCKER_KINDS), random.choice(VICTIMS)
        command = _docker_command(kind, victim)
        result = faultctl._docker(*command)
        if result.returncode != 0:
            sys.exit("docker %s failed: %s" % (" ".join(command), result.stderr.strip()))
        secret = {"how": "docker " + " ".join(command), "kind": kind, "victim": victim,
                  "accept": [victim] + (["cart"] if victim == "valkey-cart" else [])}
    secret["injected_at"] = time.time()
    SECRET.write_text(json.dumps(secret))
    print("A secret fault has been injected (you do not know which one).\n")
    print("ALERT: \"%s\"\n" % ALERT)
    print("Wait 2 minutes for the metrics, then run the agent:")
    print("  .venv/bin/python agent.py \"%s\" --out reports/mentor\n" % ALERT)
    print("(add --no-act to only diagnose, like the hidden test)   then:  python practice/mentor.py reveal")


def _latest_diagnosis(after):
    found = [p for p in REPORTS.glob("*/diagnosis.json") if p.stat().st_mtime >= after]
    return json.loads(max(found, key=lambda p: p.stat().st_mtime).read_text()) if found else None


def reveal():
    if not SECRET.exists():
        sys.exit("Nothing injected. Run: python practice/mentor.py inject")
    secret = json.loads(SECRET.read_text())
    print("WHAT THE MENTOR BROKE: %s" % secret["how"])
    print("injected at %s; right answers: %s\n" % (
        datetime.datetime.fromtimestamp(secret["injected_at"]).strftime("%H:%M:%S"), ", ".join(secret["accept"])))
    diagnosis = _latest_diagnosis(secret["injected_at"])
    if diagnosis is None:
        print("No agent run found after the injection (it writes to reports/mentor/). Run the agent first.")
        return
    named = (diagnosis.get("root_cause") or {}).get("service")
    print("AGENT SAID: %s  (status %s, confidence %s %.2f)" % (named, diagnosis.get("status"),
                                                              diagnosis.get("confidence_label"), diagnosis.get("confidence", 0)))
    print("  summary: %s" % (diagnosis.get("root_cause") or {}).get("summary", "")[:200])
    if diagnosis.get("status") == "escalated":
        verdict = "ESCALATED: not wrong, handed to a human%s" % (" (it did point at the right service)" if named in secret["accept"] else "")
    elif named in secret["accept"]:
        verdict = "CORRECT"
    else:
        verdict = "WRONG%s" % (" (and CONFIDENTLY wrong: the worst case)" if diagnosis.get("confidence_label") == "high" else " (hedged at %s)" % diagnosis.get("confidence_label"))
    print("\nVERDICT: %s" % verdict)
    print("\nNow put the shop back:  python practice/mentor.py undo")


def undo():
    if not SECRET.exists():
        faultctl.reset()
        return
    secret = json.loads(SECRET.read_text())
    if secret["kind"] == "flag":
        faultctl._write_flags({})
        if secret["flag"] in faultctl.RESIDUE_RESTART:  # its threads or leaked memory outlive the flag
            faultctl._docker("restart", faultctl.RESIDUE_RESTART[secret["flag"]])
    else:
        victim = secret["victim"]
        {"stop": lambda: faultctl._docker("start", victim),
         "pause": lambda: faultctl._docker("unpause", victim),
         "cpu_starve": lambda: faultctl._docker("update", "--cpus", faultctl._vm_cpus(), victim),
         "network_disconnect": lambda: faultctl._docker("network", "connect", "--alias", victim,
                                                        faultctl.DEMO_NETWORK, victim)}[secret["kind"]]()
    SECRET.unlink()
    print("undone: %s reverted; the shop is back to normal (give it ~2 minutes before the next round)" % secret["how"])


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    {"inject": inject, "reveal": reveal, "undo": undo}.get(command, lambda: sys.exit(__doc__ or "inject | reveal | undo"))()
