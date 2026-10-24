# docs/make_architecture_detailed.py: draws docs/architecture-detailed.svg, the data-flow map: where every piece of
# data is produced, where it is STORED, the exact endpoint the agent FETCHES it from, and every file written to disk.
#   python3 docs/make_architecture_detailed.py docs/architecture-detailed.svg
import html
import sys

W, H = 2300, 1640
out = []
FONT = "-apple-system, 'SF Pro Text', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "'SF Mono', Menlo, Consolas, monospace"
TEAL, PURPLE, ORANGE, GREEN, RED, BLUE, SLATE, PINK = ("#0c8599", "#7048e8", "#e8590c", "#2f9e44", "#e03131",
                                                       "#3b5bdb", "#475569", "#c2255c")


def esc(t):
    return html.escape(t, quote=False)


def rect(x, y, w, h, fill, stroke, r=12, sw=1.4, dash=None, extra=""):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    out.append('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s" stroke="%s" stroke-width="%s"%s %s/>'
               % (x, y, w, h, r, fill, stroke, sw, d, extra))


def text(x, y, t, size=12, color="#1f2937", weight=400, anchor="start", mono=False, italic=False):
    out.append('<text x="%g" y="%g" font-size="%s" fill="%s" font-weight="%d" text-anchor="%s" font-family="%s"%s>%s</text>'
               % (x, y, size, color, weight, anchor, MONO if mono else FONT, ' font-style="italic"' if italic else "", esc(t)))


def rich(x, y, parts, size=12):
    spans = "".join('<tspan fill="%s" font-weight="%d" font-family="%s">%s</tspan>'
                    % (c, w, MONO if m else FONT, esc(t)) for t, c, w, m in parts)
    out.append('<text x="%g" y="%g" font-size="%s">%s</text>' % (x, y, size, spans))


def box(x, y, w, h, title, color, lines, fill="#ffffff", sub=None, gap=16.5, dash=None, title_size=13.5):
    rect(x, y, w, h, fill, color, r=12, sw=1.5, dash=dash, extra='filter="url(#sh)"')
    rect(x, y, w, 30, color, color, r=12, sw=0)
    rect(x, y + 18, w, 12, color, color, r=0, sw=0)
    text(x + 12, y + 20, title, title_size, "#ffffff", 750)
    if sub:
        text(x + w - 12, y + 20, sub, 11, "#ffffffcc", 600, "end", mono=True)
    ty = y + 50
    for line in lines:
        if isinstance(line, list):
            rich(x + 12, ty, line)
        elif line.startswith("§"):
            text(x + 12, ty, line[1:], 11, "#64748b", 700)
        else:
            text(x + 12, ty, line, 12, "#334155")
        ty += gap


def zone(x, y, w, h, title, color, tint, sub=""):
    rect(x, y, w, h, tint, color, r=22, sw=2, dash="10 6")
    rect(x + 18, y - 15, len(title) * 8.6 + 28, 30, color, color, r=15, sw=0)
    text(x + 32, y + 5, title, 14, "#ffffff", 800)
    if sub:
        sx = x + len(title) * 8.6 + 54
        rect(sx - 6, y - 10, len(sub) * 6.6 + 12, 20, "#f4f6fa", "none", r=6, sw=0)
        text(sx, y + 5, sub, 12, color, 600, italic=True)


def badge(x, y, label, color):
    out.append('<circle cx="%g" cy="%g" r="11" fill="%s" stroke="#ffffff" stroke-width="2"/>' % (x, y, color))
    text(x, y + 4.5, label, 11.5, "#ffffff", 800, "middle")


def path(d, color, marker, sw=2.2, dash=None, both=False):
    ds = ' stroke-dasharray="%s"' % dash if dash else ""
    start = ' marker-start="url(#%s)"' % marker if both else ""
    out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s"%s marker-end="url(#%s)"%s stroke-linejoin="round"/>'
               % (d, color, sw, ds, marker, start))


def tag(x, y, label, color, size=11):
    w = len(label) * (size * 0.6) + 14
    rect(x - w / 2, y - 13, w, 19, "#ffffff", color, r=9, sw=1.1)
    text(x, y + 1, label, size, color, 700, "middle", mono=True)


# ------------------------------------------------------------------ canvas, title, legend
out.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (W, H, W, H))
out.append("""<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f8fafc"/><stop offset="1" stop-color="#eef2f7"/></linearGradient>
<linearGradient id="title" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0f172a"/><stop offset="1" stop-color="#1e3a8a"/></linearGradient>
<filter id="sh" x="-5%" y="-5%" width="110%" height="115%"><feDropShadow dx="0" dy="2" stdDeviation="3.5" flood-color="#0f172a" flood-opacity="0.10"/></filter>""")
for mid, col in [("t", TEAL), ("p", PURPLE), ("o", ORANGE), ("g", GREEN), ("r", RED), ("s", SLATE), ("k", PINK)]:
    out.append('<marker id="%s" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>' % (mid, col))
out.append("</defs>")
rect(0, 0, W, H, "url(#bg)", "none", r=0, sw=0)
rect(24, 18, W - 48, 74, "url(#title)", "none", r=18, sw=0, extra='filter="url(#sh)"')
text(50, 52, "Incident Zero · data-flow map", 27, "#ffffff", 800)
text(50, 78, "where every piece of data is produced, where it is STORED, the exact endpoint the agent FETCHES it from, and what is written to disk", 14, "#c7d2fe", 500)
legend = [("telemetry written", TEAL, None), ("agent fetches (read-only)", PURPLE, None), ("LLM call over HTTPS", ORANGE, None),
          ("action, after a human yes", GREEN, "7 5"), ("files written to disk", SLATE, "4 4"), ("fault injection", RED, "7 5")]
lx = 40
for label, col, dash in legend:
    path("M%d,124 L%d,124" % (lx, lx + 38), col, {TEAL: "t", PURPLE: "p", ORANGE: "o", GREEN: "g", SLATE: "s", RED: "r"}[col], 2.4, dash)
    text(lx + 48, 128, label, 12.5, "#334155", 650)
    lx += len(label) * 7.1 + 92

# ------------------------------------------------------------------ zones
zone(24, 168, 1150, 1100, "YOUR LAPTOP · Docker Compose", BLUE, "#eef3ff80", "network: opentelemetry-demo · 28 containers")
zone(1206, 168, 600, 1100, "THE AGENT · Python 3.11", ORANGE, "#fff5ec80", "repo TEAM---33 · runs on the laptop")
zone(1838, 168, 438, 270, "INTERNET", "#9c36b5", "#f8f0fc80")
zone(1838, 470, 438, 798, "FILES ON DISK", SLATE, "#f1f5f980", "inside the repo")

# ------------------------------------------------------------------ laptop: the shop
box(48, 200, 372, 432, "The shop: microservices", BLUE, [
    "§REQUEST PATH",
    [("load-generator → frontend-proxy (Envoy :8080)", "#334155", 500, False)],
    [("→ frontend → checkout → cart · product-catalog", "#334155", 500, False)],
    [("  · currency · payment · shipping(→quote) · email", "#334155", 500, False)],
    [("frontend → ad · recommendation", "#334155", 500, False)],
    "§BACKGROUND + DATA STORES",
    [("checkout → ", "#334155", 400, False), ("kafka", BLUE, 700, True), (" (topic orders) →", "#334155", 400, False)],
    [("  accounting · fraud-detection", "#334155", 400, False)],
    [("valkey-cart", BLUE, 700, True), (" Redis cache, used only by cart", "#334155", 400, False)],
    [("astronomy-db", BLUE, 700, True), (" PostgreSQL: catalog + orders", "#334155", 400, False)],
    "§EVERY SERVICE HAS AN OPENTELEMETRY SDK",
    [("sends traces + metrics + logs as ", "#334155", 400, False), ("OTLP", TEAL, 700, True)],
    [("→ otel-collector ", "#334155", 400, False), (":4317 gRPC / :4318 HTTP", TEAL, 700, True)],
    [("asks ", "#334155", 400, False), ("flagd :8013", PINK, 700, True), (" on each request:", "#334155", 400, False)],
    [("  \"is my fault flag on?\" (OpenFeature)", "#334155", 400, False)],
    "§FAULTS ARRIVE HERE",
    [("flag (via Flag UI) or docker stop/pause/…", RED, 700, False)],
], gap=21.5)

# ------------------------------------------------------------------ laptop: collector
box(458, 200, 300, 432, "otel-collector", TEAL, [
    "§RECEIVERS (what comes in)",
    [("otlp", TEAL, 700, True), ("  :4317 / :4318 from SDKs", "#334155", 400, False)],
    [("docker_stats", TEAL, 700, True), ("  docker.sock", "#334155", 400, False)],
    [("kafkametrics", TEAL, 700, True), ("  lag, members", "#334155", 400, False)],
    [("postgresql", TEAL, 700, True), ("  conns, deadlocks", "#334155", 400, False)],
    [("redis", TEAL, 700, True), ("  rejects, evictions", "#334155", 400, False)],
    [("hostmetrics", TEAL, 700, True), ("  disk /var/lib", "#334155", 400, False)],
    "§CONNECTOR",
    [("span_metrics", TEAL, 700, True), (": traces → metrics", "#334155", 400, False)],
    [("  calls_total + latency histogram", "#334155", 400, False)],
    "§EXPORTERS (where it is sent)",
    [("otlp_grpc/jaeger", TEAL, 700, True), (" → jaeger:4317", "#334155", 400, False)],
    [("otlp_http/prometheus", TEAL, 700, True)],
    [("  → prometheus:9090/api/v1/otlp", "#334155", 400, False)],
    [("opensearch", TEAL, 700, True), (" → opensearch:9200", "#334155", 400, False)],
    [("  index otel-logs-yyyy-MM-dd", "#334155", 400, False)],
], gap=22.5)

# ------------------------------------------------------------------ laptop: storage backends
box(796, 200, 360, 134, "Prometheus · metrics store", TEAL, [
    [("stored: ", "#64748b", 700, False), ("TSDB volume /prometheus", "#334155", 500, True)],
    [("kept: ", "#64748b", 700, False), ("7 days (--storage.tsdb.retention)", "#334155", 400, False)],
    [("in: ", "#64748b", 700, False), ("OTLP receiver /api/v1/otlp", "#334155", 400, False)],
    [("out: ", "#64748b", 700, False), ("http://localhost:9090/api/v1/query", PURPLE, 700, True)],
], sub=":9090", gap=19.5)
box(796, 350, 360, 134, "Jaeger 2 · trace store", TEAL, [
    [("stored: ", "#64748b", 700, False), ("IN MEMORY (max traces cap)", "#334155", 500, False)],
    [("kept: ", "#64748b", 700, False), ("until jaeger restarts → never restart it", "#334155", 400, False)],
    [("in: ", "#64748b", 700, False), ("OTLP gRPC jaeger:4317", "#334155", 400, False)],
    [("out: ", "#64748b", 700, False), (":8080/jaeger/ui/api/v3/traces", PURPLE, 700, True)],
], sub="via Envoy", gap=19.5)
box(796, 500, 360, 134, "OpenSearch · log store", TEAL, [
    [("stored: ", "#64748b", 700, False), ("index otel-logs-2026-10-24 (daily)", "#334155", 500, True)],
    [("fields: ", "#64748b", 700, False), ("body · severity · service · traceId", "#334155", 400, False)],
    [("port: ", "#64748b", 700, False), ("9200 → random host port, found by", "#334155", 400, False)],
    [("  ", "#334155", 400, False), ("docker compose port opensearch 9200", PURPLE, 700, True)],
], sub=":9200", gap=19.5)

# telemetry arrows: shop -> collector -> stores
path("M420,470 L456,470", TEAL, "t", 2.6)
tag(438, 456, "OTLP", TEAL, 10)
for y_end in (267, 417, 567):
    path("M758,%d C778,%d 776,%d 794,%d" % (y_end, y_end, y_end, y_end), TEAL, "t", 2.4)

# ------------------------------------------------------------------ laptop: flags, docker, load generator
box(48, 690, 372, 250, "Feature flags · flagd", PINK, [
    [("Flag UI ", PINK, 700, False), ("flagd-ui  :8080/feature", "#334155", 500, True)],
    [("  writes the file ↓  (POST /feature/api/write)", "#334155", 400, False)],
    [("stored: ", "#64748b", 700, False), ("src/flagd/demo.flagd.json", "#334155", 600, True)],
    [("  ↓ flagd watches the file, serves :8013", "#334155", 400, False)],
    [("services read it on every request", "#334155", 400, False)],
    "§THE AGENT",
    [("diagnosis: ", PINK, 700, False), ("NEVER reads it (rule 6)", "#334155", 600, False)],
    [("action: ", GREEN, 700, False), ("WRITES one flag, named by a human", "#334155", 600, False)],
], gap=21)
box(458, 690, 300, 250, "Docker Engine", SLATE, [
    [("socket: ", "#64748b", 700, False), ("/var/run/docker.sock", "#334155", 600, True)],
    [("knows: ", "#64748b", 700, False), ("state · exit code ·", "#334155", 400, False)],
    [("  restarts · OOMKilled · paused ·", "#334155", 400, False)],
    [("  CPU / memory limits · networks", "#334155", 400, False)],
    [("feeds ", "#64748b", 700, False), ("docker_stats → collector", TEAL, 700, False)],
    "§AGENT USES THE DOCKER CLI",
    [("read: ", PURPLE, 700, False), ("docker ps -a · docker inspect", PURPLE, 600, True)],
    [("act: ", GREEN, 700, False), ("docker restart -t 10 <svc>", GREEN, 600, True)],
], gap=21)
box(796, 690, 360, 250, "load-generator · Locust", BLUE, [
    [("simulates ", "#64748b", 700, False), ("5 shoppers (LOCUST_USERS)", "#334155", 400, False)],
    [("traffic → ", "#64748b", 700, False), ("frontend-proxy :8080", "#334155", 500, True)],
    [("web API: ", "#64748b", 700, False), (":8089 → random host port", "#334155", 400, False)],
    [("  found by ", "#334155", 400, False), ("docker compose port …8089", PURPLE, 700, True)],
    "§AGENT",
    [("before: ", PURPLE, 700, False), ("GET /stats/requests (user count)", "#334155", 500, True)],
    [("act: ", GREEN, 700, False), ("POST /swarm user_count=1", GREEN, 600, True)],
    [("undo: ", GREEN, 700, False), ("POST /swarm user_count=<captured>", "#334155", 500, True)],
], gap=21)
path("M608,690 C608,664 608,660 608,634", TEAL, "t", 2.2)   # docker_stats -> collector
tag(608, 662, "docker_stats", TEAL, 10)

# ------------------------------------------------------------------ laptop: fault injection
box(48, 990, 1108, 252, "Who breaks it · fault injection (practice and hidden test)", RED, [
    [("mentor / organisers' faultctl", RED, 700, False), (": unknown fault, injected on YOUR laptop", "#334155", 400, False)],
    [("practice/faultctl.py", RED, 700, True), (": 23 practice incidents · state in practice/.faultctl_state.json", "#334155", 400, False)],
    [("practice/mentor.py", RED, 700, True), (": random secret fault · answer sealed in practice/.mentor_secret.json", "#334155", 400, False)],
    "§HOW",
    [("application fault → ", "#64748b", 700, False), ("POST :8080/feature/api/write", RED, 700, True), ("  e.g. paymentFailure 50%, adHighCpu on, kafkaQueueProblems 3sec", "#334155", 400, False)],
    [("infrastructure fault → ", "#64748b", 700, False), ("docker stop | pause | update --cpus 0.05 | update --memory | network disconnect", RED, 700, True)],
    [("the agent is never told which one: it must find it from the telemetry alone", "#334155", 600, False)],
], fill="#fff5f5", gap=24)
path("M200,990 L200,942", RED, "r", 2.2, "7 5")
path("M540,990 L540,942", RED, "r", 2.2, "7 5")

# ------------------------------------------------------------------ agent zone
AX, AW = 1230, 552
box(AX, 200, AW, 112, "config.py · where everything is configured", ORANGE, [
    [("reads ", "#64748b", 700, False), (".env.local", ORANGE, 700, True), (" (git-ignored): API_KEY · API_KEY_BACKUP · BASE_URL · MODEL_NAME", "#334155", 400, False)],
    [("URLs: ", "#64748b", 700, False), ("prometheus :9090 · jaeger :8080/jaeger/ui · opensearch + locust ports", "#334155", 400, False)],
    [("  discovered at start with ", "#334155", 400, False), ("docker compose port", PURPLE, 700, True), ("; DEMO_DIR = the demo folder", "#334155", 400, False)],
], gap=19)
box(AX, 328, AW, 288, "tools.py · the eyes (fetch, compute, label · no AI)", PURPLE, [
    "§FETCHES (read-only)",
    [("①", PURPLE, 800, False), ("  GET  :9090/api/v1/query", PURPLE, 700, True), ("   PromQL: rates, p95, baselines,", "#334155", 400, False)],
    [("      CPU/memory, Kafka lag, Postgres, Redis, disk", "#334155", 400, False)],
    [("②", PURPLE, 800, False), ("  GET  :8080/jaeger/ui/api/v3/traces", PURPLE, 700, True), ("  OTLP JSON span trees", "#334155", 400, False)],
    [("③", PURPLE, 800, False), ("  POST <port>/otel-logs-*/_search", PURPLE, 700, True), ("  WARN+ logs of a service", "#334155", 400, False)],
    [("④", PURPLE, 800, False), ("  docker ps -a / docker inspect", PURPLE, 700, True), ("  state, restarts, OOM, limits", "#334155", 400, False)],
    "§COMPUTES IN CODE",
    [("deviation vs own 2-h baseline · deepest failing span · DOWN vs IDLE ·", "#334155", 400, False)],
    [("SLOW_TAIL · TRAFFIC_SURGE · error signatures · injection + flag redaction", "#334155", 400, False)],
    "§STORES IN MEMORY",
    [("evidence registry", PURPLE, 700, False), (": every returned fact gets ", "#334155", 400, False), ("metric-N · trace-N · log-N", PURPLE, 700, True)],
], gap=21.5)
box(AX, 632, AW, 236, "agent.py · the brain (loop + trust checks)", ORANGE, [
    [("in: ", "#64748b", 700, False), ("alert text", "#334155", 600, False), ("   (CLI  python agent.py \"<alert>\"  or  agent.diagnose())", "#334155", 400, True)],
    [("loop: ", "#64748b", 700, False), ("prompts/system_prompt.md", ORANGE, 700, True), (" + alert → LLM picks ONE tool", "#334155", 400, False)],
    [("  → tools.py runs it → result appended to history → repeat (4–8×)", "#334155", 400, False)],
    [("submit_diagnosis", ORANGE, 700, True), (" → trust checks in code:", "#334155", 400, False)],
    [("  evidence guard (refs must be in the registry) · fresh evidence only ·", "#334155", 400, False)],
    [("  calibration · consistency · reviewer LLM (grounded dispute → 0.60)", "#334155", 400, False)],
    [("checks ", "#64748b", 700, False), ("KILL_SWITCH", RED, 700, True), (" file before every step", "#334155", 400, False)],
    [("writes ", "#64748b", 700, False), ("transcript.jsonl · diagnosis.json · report.md", SLATE, 700, True)],
    [("  (validated against ", "#334155", 400, False), ("schema.json", SLATE, 700, True), (" by report.py)", "#334155", 400, False)],
], gap=21)
box(AX, 884, 268, 132, "llm.py", ORANGE, [
    [("only file that calls the LLM", "#334155", 600, False)],
    [("pacing ≤ 7,200 tokens/min", "#334155", 400, False)],
    [("waits Retry-After on 429", "#334155", 400, False)],
    [("daily cap → next route", "#334155", 400, False)],
], gap=19)
box(AX + 284, 884, 268, 132, "verify.py", GREEN, [
    [("before: snapshot from ①", "#334155", 400, False)],
    [("wait 120 s, re-read ① + ④", "#334155", 400, False)],
    [("recovered / not / can't tell", "#334155", 400, False)],
    [("not → roll back + escalate", "#334155", 400, False)],
], gap=19)
box(AX, 1032, AW, 210, "actions.py · the hands (only after a human types y)", GREEN, [
    [("allowlist: ", "#64748b", 700, False), ("restart_service · toggle_feature_flag · throttle_load", GREEN, 700, True)],
    [("protected: jaeger · prometheus · opensearch · otel-collector · flagd · load-gen", "#334155", 400, False)],
    [("Ⓐ", GREEN, 800, False), ("  docker restart -t 10 <service>", GREEN, 700, True), ("            → Docker Engine", "#334155", 400, False)],
    [("Ⓑ", GREEN, 800, False), ("  POST :8080/feature/api/write", GREEN, 700, True), ("   → demo.flagd.json", "#334155", 400, False)],
    [("Ⓒ", GREEN, 800, False), ("  POST <locust>/swarm user_count=1", GREEN, 700, True), (" → load-generator", "#334155", 400, False)],
    [("refuses if ", "#64748b", 700, False), ("KILL_SWITCH", RED, 700, True), (" exists or approved≠True · logs every attempt to", "#334155", 400, False)],
    [("action_log.jsonl", SLATE, 700, True), (" (append-only, also refusals and dry runs)", "#334155", 400, False)],
], gap=22)

# fetch arrows: stores -> tools.py (purple, numbered)
for y_src, n, y_dst in [(267, "1", 374), (417, "2", 432), (567, "3", 455)]:
    path("M1156,%d C1190,%d 1196,%d 1228,%d" % (y_src, y_src, y_dst, y_dst), PURPLE, "p", 2.3)
    badge(1188, (y_src + y_dst) / 2, n, PURPLE)
path("M740,690 L740,664 L1170,664 L1170,560 L1228,560", PURPLE, "p", 2.3)
badge(960, 664, "4", PURPLE)

# action arrows: actions.py -> Docker / Flag UI / Locust (green dashed, along the bottom gap)
path("M1230,1135 L1190,1135 L1190,964 L620,964 L620,942", GREEN, "g", 2.3, "7 5")
badge(800, 964, "A", GREEN)
path("M1230,1160 L1180,1160 L1180,975 L260,975 L260,942", GREEN, "g", 2.3, "7 5")
badge(380, 975, "B", GREEN)
path("M1230,1185 L1170,1185 L1170,955 L1000,955 L1000,942", GREEN, "g", 2.3, "7 5")
badge(1085, 955, "C", GREEN)

# ------------------------------------------------------------------ internet
box(1858, 200, 398, 220, "Groq API (OpenAI-compatible)", "#9c36b5", [
    [("POST ", "#64748b", 700, False), ("https://api.groq.com/openai/v1", "#9c36b5", 700, True)],
    [("     /chat/completions", "#9c36b5", 700, True), ("  (tools + messages)", "#334155", 400, False)],
    [("models: ", "#64748b", 700, False), ("openai/gpt-oss-120b", "#334155", 600, True)],
    [("  fallback ", "#334155", 400, False), ("openai/gpt-oss-20b", "#334155", 600, True)],
    [("limits per key+model: ", "#64748b", 700, False), ("8k tokens/min", "#334155", 400, False)],
    [("  · 200k tokens/day (≈ 6–8 investigations)", "#334155", 400, False)],
    [("route on a daily cap:", "#64748b", 700, False)],
    [("  120b primary → 120b backup → 20b → 20b", "#334155", 500, False)],
], gap=19.5)
path("M1364,1018 L1364,1025 L1822,1025 L1822,310 L1854,310", ORANGE, "o", 2.6, both=True)
tag(1822, 454, "HTTPS", ORANGE, 10.5)

# ------------------------------------------------------------------ files on disk
FX = 1858
rect(FX, 500, 398, 748, "#ffffff", SLATE, r=12, sw=1.4, extra='filter="url(#sh)"')
text(FX + 14, 526, "TEAM---33/", 14, "#0f172a", 800, mono=True)
tree = [
    (".env.local", "API keys · git-ignored", "config.py reads", ORANGE),
    ("KILL_SWITCH", "exists? → stop everything", "agent · actions · verify", RED),
    ("action_log.jsonl", "every action attempt (append)", "actions.py", GREEN),
    ("runs/<incident>/", "default output of agent.py", "agent.py", SLATE),
    ("  transcript.jsonl", "every step, tool result, model", "", SLATE),
    ("  diagnosis.json", "the answer (schema.json)", "", SLATE),
    ("  report.md", "readable report", "", SLATE),
    ("reports/demo/<run>/", "same 3 files, live demos", "demo.sh", SLATE),
    ("reports/mentor/<run>/", "blind rehearsal runs", "mentor.py", SLATE),
    ("reports/sweep-<time>/", "+ verdict.json per incident,", "run_all.py", SLATE),
    ("", "  scoring-table.md", "", SLATE),
    ("reports/fault-detection-*.md", "tool-layer detection matrix", "", SLATE),
    ("runs/*.log", "background run logs", "", SLATE),
    ("practice/.faultctl_state.json", "what faultctl injected", "faultctl", RED),
    ("practice/.mentor_secret.json", "sealed answer (ignored)", "mentor.py", RED),
    ("prompts/system_prompt.md", "the agent's instructions", "agent.py reads", ORANGE),
    ("schema.json", "output contract", "report.py reads", SLATE),
]
ty = 556
for name, desc, who, col in tree:
    if name:
        text(FX + 14, ty, name, 11.6, col, 750, mono=True)
        ty += 16
    text(FX + 28, ty, desc, 11.6, "#334155")
    if who:
        text(FX + 384, ty, who, 10.8, "#64748b", 600, "end", italic=True)
    ty += 22 if name else 22
# files arrows
path("M1782,820 C1820,820 1820,700 1856,700", SLATE, "s", 2.2, "4 4")
path("M1782,1220 C1822,1220 1822,640 1856,640", SLATE, "s", 2.0, "4 4")

# ------------------------------------------------------------------ bottom strip: one incident, step by step
by = 1300
rect(24, by, W - 48, 316, "#0f172a", "#0f172a", r=20, sw=0, extra='filter="url(#sh)"')
text(52, by + 36, "ONE INCIDENT, END TO END: what is read and written at each step", 16, "#fcd34d", 800)
steps = [
    ("1", "Fault", "flag write or docker\ncommand changes the shop", RED),
    ("2", "Telemetry", "SDKs → collector →\nPrometheus · Jaeger · OpenSearch", TEAL),
    ("3", "Alert", "python agent.py \"<alert>\"\nreads .env.local + prompt", ORANGE),
    ("4", "Investigate", "LLM picks tool → tools.py\nfetches ①②③④ → registry", PURPLE),
    ("5", "Diagnose", "trust checks + reviewer\n→ diagnosis.json, report.md", ORANGE),
    ("6", "Approve", "dry run shown · human types y\n(KILL_SWITCH checked)", "#1c7ed6"),
    ("7", "Act", "Ⓐ restart · Ⓑ flag · Ⓒ throttle\n→ action_log.jsonl", GREEN),
    ("8", "Verify", "re-read ① + ④ after 120 s\nrecovered? else roll back", GREEN),
]
sx, sw_ = 52, (W - 48 - 56) / len(steps)
for i, (n, title, desc, col) in enumerate(steps):
    x = sx + i * sw_
    rect(x, by + 58, sw_ - 18, 150, "#1e293b", col, r=14, sw=1.8)
    out.append('<circle cx="%g" cy="%g" r="17" fill="%s"/>' % (x + 30, by + 92, col))
    text(x + 30, by + 98, n, 15, "#ffffff", 800, "middle")
    text(x + 56, by + 98, title, 15.5, "#ffffff", 750)
    for j, line in enumerate(desc.split("\n")):
        text(x + 16, by + 140 + j * 21, line, 12.2, "#cbd5e1", 500)
    if i < len(steps) - 1:
        path("M%g,%g L%g,%g" % (x + sw_ - 16, by + 133, x + sw_ - 3, by + 133), "#94a3b8", "s", 2)
text(52, by + 246, "Read-only by design: the agent fetches ①–④ freely, but it can change the shop only through Ⓐ Ⓑ Ⓒ, only after a human types y, never with KILL_SWITCH present.",
     13.5, "#e2e8f0", 600)
text(52, by + 274, "Never touched: flagd for diagnosis (rule 6) · Jaeger restarts (its traces live in memory) · Prometheus / OpenSearch / collector (the instruments, not the patient).",
     13, "#94a3b8", 500)

out.append("</svg>")
open(sys.argv[1], "w").write("\n".join(out))
print("wrote", sys.argv[1])
