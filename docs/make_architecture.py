# docs/make_architecture.py: draws docs/architecture.svg (render to PNG with headless Chrome, see README).
#   python3 docs/make_architecture.py docs/architecture.svg
import html
import sys

W, H = 1840, 1250
out = []
FONT = "-apple-system, 'SF Pro Text', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "'SF Mono', Menlo, Consolas, monospace"


def esc(t):
    return html.escape(t, quote=False)


def rect(x, y, w, h, fill, stroke, r=14, sw=1.5, dash=None, extra=""):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="%s" stroke="%s" stroke-width="%s"%s %s/>'
               % (x, y, w, h, r, fill, stroke, sw, d, extra))


def text(x, y, t, size=12.5, color="#1f2937", weight=400, anchor="start", mono=False, italic=False):
    out.append('<text x="%d" y="%d" font-size="%s" fill="%s" font-weight="%d" text-anchor="%s" font-family="%s"%s>%s</text>'
               % (x, y, size, color, weight, anchor, MONO if mono else FONT, ' font-style="italic"' if italic else "", esc(t)))


def rich(x, y, parts, size=12.5):
    # parts: [(text, color, weight, mono)]
    spans = "".join('<tspan fill="%s" font-weight="%d" font-family="%s">%s</tspan>'
                    % (c, w, MONO if m else FONT, esc(t)) for t, c, w, m in parts)
    out.append('<text x="%d" y="%d" font-size="%s">%s</text>' % (x, y, size, spans))


def column(x, w, color, tint, number, title, subtitle, y=118, h=800):
    rect(x, y, w, h, tint, color, r=20, sw=1.6)
    rect(x, y, w, 62, color, color, r=20, sw=0)
    rect(x, y + 40, w, 22, color, color, r=0, sw=0)
    out.append('<circle cx="%d" cy="%d" r="15" fill="#ffffff" opacity="0.95"/>' % (x + 30, y + 31))
    text(x + 30, y + 36, number, 15, color, 800, "middle")
    text(x + 54, y + 28, title, 16.5, "#ffffff", 750)
    text(x + 54, y + 48, subtitle, 11.5, "#ffffffdd", 500)


def card(x, y, w, h, title, lines, color, fill="#ffffff", title_size=13, line_gap=17, dash=None, icon=None):
    rect(x, y, w, h, fill, color + "66", r=12, sw=1.2, dash=dash)
    ty = y + 22
    if title:
        text(x + 14, ty, title, title_size, color, 700)
        ty += line_gap + 3
    for line in lines:
        if isinstance(line, list):
            rich(x + 14, ty, line)
        else:
            text(x + 14, ty, line, 12, "#374151")
        ty += line_gap


def chip(x, y, label, color, fill, mono=True, size=11):
    w = int(len(label) * (6.9 if mono else 6.6)) + 16
    rect(x, y, w, 22, fill, color + "88", r=11, sw=1)
    text(x + w / 2, y + 15, label, size, color, 650, "middle", mono=mono)
    return w


def arrow(x1, y1, x2, y2, color="#475569", label=None, lx=None, ly=None, marker="a", sw=2, dash=None, path=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    if path:
        out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s"%s marker-end="url(#%s)"/>' % (path, color, sw, d, marker))
    else:
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="%s"%s marker-end="url(#%s)"/>'
                   % (x1, y1, x2, y2, color, sw, d, marker))
    if label:
        lx = lx if lx is not None else (x1 + x2) / 2
        ly = ly if ly is not None else (y1 + y2) / 2 - 6
        w = len(label) * 6.4 + 14
        rect(lx - w / 2, ly - 13, w, 19, "#ffffff", color + "88", r=9, sw=1)
        text(lx, ly + 1, label, 11, color, 650, "middle")


def svc(x, y, name, w=104, color="#3b5bdb", fill="#ffffff", bold=False):
    rect(x, y, w, 24, fill, color + "99", r=7, sw=1.1)
    text(x + w / 2, y + 16, name, 11, color, 700 if bold else 600, "middle", mono=True)


# ---------------------------------------------------------------- canvas
out.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (W, H, W, H))
out.append("""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f8fafc"/><stop offset="1" stop-color="#eef2f7"/></linearGradient>
<linearGradient id="title" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0f172a"/><stop offset="1" stop-color="#1e3a8a"/></linearGradient>
<filter id="sh" x="-5%" y="-5%" width="110%" height="115%"><feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#0f172a" flood-opacity="0.10"/></filter>""")
for mid, col in [("a", "#475569"), ("r", "#e03131"), ("g", "#2f9e44"), ("v", "#7048e8"), ("o", "#e8590c"), ("b", "#3b5bdb"), ("t", "#0c8599")]:
    out.append('<marker id="%s" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>' % (mid, col))
out.append("</defs>")
rect(0, 0, W, H, "url(#bg)", "none", r=0, sw=0)

# ---------------------------------------------------------------- title
rect(24, 20, W - 48, 76, "url(#title)", "none", r=18, sw=0, extra='filter="url(#sh)"')
text(52, 56, "Incident Zero · AI On-Call Engineer", 27, "#ffffff", 800)
text(52, 81, "TEAM-33 · complete architecture: from a broken shop to a verified, human-approved fix", 14, "#c7d2fe", 500)
for i, (label, col) in enumerate([("1  Evidence or nothing", "#a5b4fc"), ("2  Honest confidence", "#fcd34d"), ("3  Safe hands", "#86efac")]):
    bx = 1180 + i * 210
    rect(bx, 40, 196, 36, "#ffffff14", col, r=18, sw=1.4)
    text(bx + 98, 63, label, 13.5, col, 700, "middle")

# ---------------------------------------------------------------- columns
COLS = {
    "shop": (24, 372, "#3b5bdb", "#eef3ff", "1", "THE SHOP", "OpenTelemetry Demo · Docker Compose · 28 containers"),
    "tel": (418, 232, "#0c8599", "#e8f9fb", "2", "TELEMETRY", "metrics · traces · logs"),
    "eyes": (672, 364, "#7048e8", "#f4f1ff", "3", "THE EYES · tools.py", "8 tools · no AI · all maths in code"),
    "brain": (1100, 344, "#e8590c", "#fff5ec", "4", "THE BRAIN · agent.py", "LLM investigation loop + trust checks"),
    "hands": (1466, 350, "#2f9e44", "#eefbf1", "5", "THE HANDS · act & verify", "actions.py · verify.py · 4 safety gates"),
}
for key, (x, w, col, tint, n, title, sub) in COLS.items():
    out.append('<g filter="url(#sh)">')
    column(x, w, col, tint, n, title, sub)
    out.append("</g>")

# ---------------------------------------------------------------- 1. shop
B = "#3b5bdb"
x0 = 40
text(x0, 206, "REQUEST PATH", 11, "#64748b", 700)
svc(x0, 216, "load-generator", 116, "#64748b")
svc(x0 + 136, 216, "frontend-proxy", 116)
arrow(x0 + 116, 228, x0 + 134, 228, "#94a3b8", marker="a", sw=1.4)
svc(x0 + 136, 256, "frontend", 116, bold=True)
arrow(x0 + 194, 240, x0 + 194, 255, "#94a3b8", sw=1.4)
svc(x0 + 268, 236, "ad", 70)
svc(x0 + 268, 266, "recommend.", 70)
arrow(x0 + 252, 268, x0 + 266, 250, "#94a3b8", sw=1.2)
arrow(x0 + 252, 270, x0 + 266, 278, "#94a3b8", sw=1.2)
svc(x0 + 136, 296, "checkout", 116, bold=True)
arrow(x0 + 194, 280, x0 + 194, 295, "#94a3b8", sw=1.4)
for i, name in enumerate(["cart", "product-catalog", "currency"]):
    svc(x0 + i * 114, 340, name, 106)
for i, name in enumerate(["payment", "shipping", "email"]):
    svc(x0 + i * 114, 372, name, 106)
svc(x0 + 114, 404, "quote", 106)
arrow(x0 + 194, 320, x0 + 194, 338, "#94a3b8", sw=1.4)
text(x0, 448, "QUEUE · BACKGROUND", 11, "#64748b", 700)
svc(x0, 458, "kafka", 106, "#0b7285", "#e3fafc", bold=True)
svc(x0 + 114, 458, "accounting", 106)
svc(x0 + 228, 458, "fraud-detect.", 106)
arrow(x0 + 106, 470, x0 + 112, 470, "#94a3b8", sw=1.2)
text(x0, 506, "DATA STORES", 11, "#64748b", 700)
svc(x0, 516, "valkey-cart", 106, "#0b7285", "#e3fafc", bold=True)
svc(x0 + 114, 516, "astronomy-db", 106, "#0b7285", "#e3fafc", bold=True)
svc(x0 + 228, 516, "flagd (flags)", 106, "#c2255c", "#fff0f6", bold=True)
text(x0, 560, "cache for cart · PostgreSQL · fault switches", 11, "#64748b", 500, italic=True)

card(36, 576, 348, 112, "Faults are injected HERE", [
    "mentor / faultctl / practice/mentor.py:",
    [("flags", "#c2255c", 700, True), (" paymentFailure, adHighCpu, kafka…", "#374151", 400, False)],
    [("docker", "#c2255c", 700, True), (" stop · pause · cpus · memory · network", "#374151", 400, False)],
    "the agent is never told which one",
], "#e03131", fill="#fff5f5", dash="6 4")
card(36, 700, 348, 74, "Instrumented with OpenTelemetry", [
    "every service emits traces · metrics · logs",
    "15 services, 7+ languages (Go, Java, .NET, Rust…)",
], B)
card(36, 786, 348, 118, "Fixes land here (only after a human yes)", [
    [("docker restart ", "#2f9e44", 700, True), ("<service>", "#374151", 400, True)],
    [("write flag ", "#2f9e44", 700, True), ("<name the human typed>", "#374151", 400, True)],
    [("throttle ", "#2f9e44", 700, True), ("load-generator users", "#374151", 400, True)],
    "never: observability, flagd, load-gen restart",
], "#2f9e44", fill="#f4fcf5", dash="6 4")

# ---------------------------------------------------------------- 2. telemetry
T = "#0c8599"
tx, tw = 432, 204
card(tx, 196, tw, 96, "OTel Collector", ["span metrics connector", "docker_stats · kafka", "postgresql · redis · host"], T)
card(tx, 304, tw, 152, "Prometheus", ["span calls + latency", "histograms", "container CPU / memory", "Kafka lag · group members", "Postgres conns · deadlocks", "Redis rejects · disk"], T)
card(tx, 468, tw, 78, "Jaeger 2 · traces", ["v3 API · OTLP JSON", "spans with parent/child"], T)
card(tx, 558, tw, 78, "OpenSearch · logs", ["otel-logs-* indices", "severity · traceId · body"], T)
card(tx, 648, tw, 96, "Docker Engine", ["state · restarts · OOM", "CPU / memory limits", "networks · paused"], T)
card(tx, 756, tw, 148, "Never read for diagnosis", [
    [("flagd", "#c2255c", 700, True), (" / Flag UI", "#374151", 400, False)],
    "feature-flag text in",
    "telemetry is redacted",
    "before the model sees it",
    "(rule 6: no answer key)",
], "#c2255c", fill="#fff0f6", dash="5 4")

# ---------------------------------------------------------------- 3. eyes
V = "#7048e8"
ex, ew = 686, 336
tools = [
    ("get_service_health", "vs its OWN 2-h normal"),
    ("", "→ deviation_score ranking (top = suspect)"),
    ("get_container_health", "stopped · OOM · restarts"),
    ("", "CPU_SPIKE · CPU_LIMITED · MEMORY_CLIMBING"),
    ("get_dependency_health", "Kafka · DB · cache · disk"),
    ("search_traces · get_trace", "deepest failing span"),
    ("search_logs", "WARN+ lines + error signature"),
    ("get_deploy_history", "what changed just before"),
    ("list_services", "orientation"),
]
lines = []
for name, desc in tools:
    lines.append([(name + "  ", V, 700, True), (desc, "#374151", 400, False)] if name else [("   " + desc, "#5f3dc4", 500, False)])
card(ex, 196, ew, 196, "8 tools the model can call", lines, V, line_gap=16.5)
card(ex, 404, ew, 132, "Computed in code, never guessed", [
    [("deepest failing span", V, 700, False), (": walk the span tree;", "#374151", 400, False)],
    "  the culprit's own children did not fail",
    [("twin rule", V, 700, False), (": no errors → the service that", "#374151", 400, False)],
    "  moved most from its OWN normal",
    [("baselines", V, 700, False), (": median of last 2 h, minus 10 min", "#374151", 400, False)],
], V, line_gap=16.5)
rect(ex, 548, ew, 132, "#ffffff", V + "66", r=12, sw=1.2)
text(ex + 14, 570, "Labels the model reads", 13, V, 700)
cx, cy = ex + 14, 578
for label in ["ERRORS", "SLOW", "SLOWER 4x", "SLOW_TAIL", "DOWN", "IDLE", "PAUSED", "TRAFFIC_SURGE", "RETRY_STORM?",
              "QUEUE_BACKLOG", "CACHE_DOWN", "TELEMETRY_GAP", "pipeline_warning"]:
    w = int(len(label) * 6.9) + 16
    if cx + w > ex + ew - 10:
        cx, cy = ex + 14, cy + 25
    chip(cx, cy, label, V, "#f3f0ff")
    cx += w + 6
card(ex, 692, ew, 106, "Guards on the data", [
    [("error signatures", V, 700, False), (": dns · timeout · OOM · db pool", "#374151", 400, False)],
    [("prompt injection", V, 700, False), (" in logs → redacted", "#374151", 400, False)],
    [("clock skew", V, 700, False), (" warning · ", "#374151", 400, False), ("stale metrics", V, 700, False), (" warning", "#374151", 400, False)],
    [("flag text", V, 700, False), (" → redacted (never seen by the model)", "#374151", 400, False)],
], V, line_gap=17)
rect(ex, 810, ew, 94, "#5f3dc4", "#5f3dc4", r=12, sw=0)
text(ex + 16, 834, "EVIDENCE REGISTRY", 13, "#ffffff", 800)
text(ex + 16, 856, "every fact a tool returns gets an ID:", 12, "#e5dbff", 500)
cx = ex + 16
for label in ["metric-3", "trace-7", "log-12"]:
    cx += chip(cx, 868, label, "#ffffff", "#7950f2") + 8
text(cx + 4, 884, "citable refs", 11.5, "#e5dbff", 500, italic=True)

# ---------------------------------------------------------------- 4. brain
O = "#e8590c"
bx, bw = 1114, 316
rect(bx, 196, bw, 50, "#fff4e6", O, r=12, sw=1.6)
text(bx + 14, 217, "ALERT IN", 11.5, O, 800)
text(bx + 14, 236, "\"Checkout error rate is high\"", 13, "#7c2d12", 600, italic=True)
card(bx, 258, bw, 116, "Tool-calling loop", [
    "system prompt ≈ 2k tokens: map, steps, rules",
    [("model picks ", "#374151", 400, False), ("ONE tool at a time", O, 700, False)],
    "next step depends on what it just learned",
    "4–8 calls · ~3–4 min · history compacted",
], O)
card(bx, 386, bw, 118, "LLM · Groq (OpenAI-compatible API)", [
    [("gpt-oss-120b", O, 700, True), (" primary", "#374151", 400, False)],
    [("daily cap → ", "#374151", 400, False), ("backup key 120b", O, 700, True), (" → ", "#374151", 400, False), ("20b", O, 700, True)],
    "pacing under 8k tokens/min · Retry-After",
    "bad tool call → fed back, run continues",
], O)
rect(bx, 516, bw, 50, "#ffffff", O + "66", r=12, sw=1.2)
text(bx + 14, 537, "submit_diagnosis", 13, O, 750, mono=True)
text(bx + 14, 556, "root cause · refs · confidence · one action", 11.5, "#374151")
# trust checks
rect(bx, 578, bw, 326, "#fff0f6", "#d6336c", r=14, sw=1.6)
text(bx + 14, 602, "TRUST CHECKS · in code, after the answer", 12.5, "#c2255c", 800)
checks = [
    ("Evidence guard", "a ref no tool returned → REJECTED;", "model must resubmit (demo: trace-9999)"),
    ("Fresh evidence only", "older than the incident window", "does not count toward confidence"),
    ("Calibration", "high needs 2 evidence kinds + a", "top-ranked service · escalate ≤ 0.45"),
    ("Consistency", "a stopped / crashed container must", "be named or explained away"),
    ("Reviewer LLM", "a second call tries to DISPROVE it;", "a grounded dispute caps it at 0.60"),
]
cy = 630
for title_, l1, l2 in checks:
    out.append('<circle cx="%d" cy="%d" r="8" fill="#d6336c"/>' % (bx + 22, cy - 4))
    text(bx + 22, cy, "✓", 11, "#ffffff", 800, "middle")
    text(bx + 38, cy, title_, 12.5, "#a61e4d", 750)
    text(bx + 38, cy + 16, l1, 11.8, "#374151")
    text(bx + 38, cy + 31, l2, 11.8, "#374151")
    cy += 56

# ---------------------------------------------------------------- 5. hands
G = "#2f9e44"
hx, hw = 1480, 322
flow = [
    ("Confident? (≥ 0.50)", "no → escalate to a human, no action", "#fff9db", "#f08c00"),
    ("Dry run", "exactly what would change + undo", "#ffffff", G),
    ("GATE · human types y", "n / no answer → nothing changes", "#e7f5ff", "#1c7ed6"),
    ("GATE · allowlist (actions.py)", "restart · write flag · throttle load", "#e7f5ff", "#1c7ed6"),
    ("Execute + log", "every attempt → action_log.jsonl", "#ffffff", G),
    ("Verify (verify.py)", "snapshot before → wait 120 s → compare", "#ffffff", G),
]
fy = 196
for i, (t1, t2, fill, col) in enumerate(flow):
    rect(hx, fy, hw, 56, fill, col, r=11, sw=1.5)
    text(hx + 14, fy + 23, t1, 13, col, 750)
    text(hx + 14, fy + 42, t2, 11.5, "#374151")
    if i < len(flow) - 1:
        arrow(hx + hw / 2, fy + 56, hx + hw / 2, fy + 70, "#475569", sw=1.8)
    fy += 72
# outcome diamond row
dy = fy + 2
out.append('<polygon points="%d,%d %d,%d %d,%d %d,%d" fill="#ffffff" stroke="%s" stroke-width="1.6"/>'
           % (hx + hw / 2, dy, hx + hw / 2 + 74, dy + 26, hx + hw / 2, dy + 52, hx + hw / 2 - 74, dy + 26, G))
text(hx + hw / 2, dy + 31, "Recovered?", 12.5, G, 750, "middle")
arrow(hx + hw / 2, dy - 14, hx + hw / 2, dy - 1, "#475569", sw=1.8)
rect(hx, dy + 70, 151, 52, "#ebfbee", G, r=11, sw=1.5)
text(hx + 75, dy + 92, "yes ✓", 13, G, 800, "middle")
text(hx + 75, dy + 110, "report + numbers", 11.5, "#374151", 500, "middle")
rect(hx + hw - 151, dy + 70, 151, 52, "#fff5f5", "#e03131", r=11, sw=1.5)
text(hx + hw - 75, dy + 92, "no ✗", 13, "#e03131", 800, "middle")
text(hx + hw - 75, dy + 110, "roll back + escalate", 11.5, "#374151", 500, "middle")
arrow(hx + hw / 2 - 40, dy + 40, hx + 75, dy + 68, G, marker="g", sw=1.8)
arrow(hx + hw / 2 + 40, dy + 40, hx + hw - 75, dy + 68, "#e03131", marker="r", sw=1.8)
# kill switch bar
ky = dy + 136
rect(hx, ky, hw, 64 + 0, "#e03131", "#e03131", r=12, sw=0, extra='filter="url(#sh)"')
text(hx + 16, ky + 25, "GATE · KILL_SWITCH", 14, "#ffffff", 800)
text(hx + 16, ky + 46, "touch KILL_SWITCH → stops at the next step,", 11.5, "#ffe3e3", 500)
text(hx + 16, ky + 60, "before acting, and every second of verify", 11.5, "#ffe3e3", 500)

# ---------------------------------------------------------------- cross-column arrows
arrow(397, 300, 431, 300, T, marker="t")
arrow(651, 340, 685, 340, V, marker="v")
# brain asks the tools (left), the tools answer with facts + refs (right)
arrow(1098, 302, 1039, 302, O, marker="o")
arrow(1039, 336, 1098, 336, V, marker="v")
for (cy_, l1, l2, col) in [(258, "tool", "← call", O), (346, "facts +", "refs →", V)]:
    rect(1040, cy_, 58, 36, "#ffffff", col + "aa", r=9, sw=1)
    text(1069, cy_ + 15, l1, 10.5, col, 750, "middle")
    text(1069, cy_ + 29, l2, 10.5, col, 750, "middle")
# brain -> hands: the proposal
arrow(0, 0, 0, 0, G, path="M1431,541 C1452,541 1452,224 1478,224", marker="g")
rect(1424, 372, 62, 36, "#ffffff", "#2f9e44aa", r=9, sw=1)
text(1455, 387, "proposal", 10.5, G, 700, "middle")
text(1455, 400, "+ dry run", 10.5, G, 700, "middle")
# hands execute -> fixes land in the shop (between the columns and the bottom band)
arrow(0, 0, 0, 0, G, path="M1480,512 L1456,512 L1456,929 L210,929 L210,922", marker="g", sw=2, dash="7 5")
rect(760, 919, 330, 21, "#ffffff", "#2f9e44aa", r=10, sw=1)
text(925, 933, "approved action, through the allowlist only", 11.5, G, 700, "middle")

# ---------------------------------------------------------------- bottom band
by = 952
rect(24, by, 600, 230, "#ffffff", "#334155", r=18, sw=1.4, extra='filter="url(#sh)"')
text(48, by + 32, "6  OUTPUTS · every run", 16, "#0f172a", 800)
outputs = [("diagnosis.json", "root cause, evidence refs, confidence, action (JSON schema)"),
           ("report.md", "readable report: evidence, reviewer, action loop, timeline"),
           ("transcript.jsonl", "every step, every tool result, which model answered"),
           ("action_log.jsonl", "every attempt, refusal, dry run and approval (append-only)")]
oy = by + 64
for name, desc in outputs:
    chip(48, oy - 15, name, "#334155", "#f1f5f9")
    text(48 + len(name) * 6.9 + 28, oy, desc, 12.5, "#374151")
    oy += 38

rect(644, by, 640, 230, "#ffffff", "#334155", r=18, sw=1.4, extra='filter="url(#sh)"')
text(668, by + 32, "7  PROOF & TESTING", 16, "#0f172a", 800)
proofs = [("faultctl.py", "23 practice incidents: application + infrastructure faults"),
          ("mentor.py", "blind test: random secret fault → agent → reveal + score"),
          ("fault_detection_check", "does each fault show up in the tools? (no LLM)"),
          ("run_all + calibration", "sweeps: stated confidence vs actual accuracy"),
          ("34 tests · 18 proofs", "offline tests + prove_three_ideas.py, PASS/FAIL"),
          ("run_everything.sh", "the whole project, live, in one command")]
oy = by + 62
for name, desc in proofs:
    rich(668, oy, [(name + "  ", "#334155", 750, True), (desc, "#374151", 400, False)])
    oy += 27

rect(1304, by, 512, 230, "#0f172a", "#0f172a", r=18, sw=0, extra='filter="url(#sh)"')
text(1328, by + 32, "THE RULES THAT MAKE IT SAFE", 15, "#fcd34d", 800)
rules = [("Diagnosis never reads feature flags.", "#ffffff"),
         ("Actions only write the one flag a human names.", "#ffffff"),
         ("Nothing changes without a human typing y.", "#ffffff"),
         ("Every claim cites evidence a tool returned.", "#ffffff"),
         ("Not sure → escalate. Didn't recover → roll back.", "#ffffff")]
oy = by + 64
for rule, col in rules:
    out.append('<circle cx="%d" cy="%d" r="4" fill="#fcd34d"/>' % (1334, oy - 4))
    text(1346, oy, rule, 13, col, 600)
    oy += 27
text(1328, by + 208, "Python 3.11 · OpenAI SDK → Groq · Prometheus · Jaeger 2 · OpenSearch · Docker", 11.2, "#94a3b8", 500)

out.append("</svg>")
pathlib_out = sys.argv[1]
open(pathlib_out, "w").write("\n".join(out))
print("wrote", pathlib_out)
