# config.py — the only place URLs, ports and model names are written down.
# Every other file imports from here. If the stack restarts and a port changes, change one line.
import os
import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent
DEMO_DIR = pathlib.Path(os.environ.get("DEMO_DIR", REPO_ROOT.parent / "opentelemetry-demo"))


def _load_dotenv():
    # tiny .env / .env.local reader (accepts `export KEY="value"` lines); never overrides a real env var
    for env_file in (REPO_ROOT / ".env", REPO_ROOT / ".env.local"):
        if not env_file.exists():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _discover_port(service, container_port, fallback):
    # OpenSearch / Jaeger publish on ephemeral host ports: ask docker compose instead of hard-coding
    try:
        output = subprocess.run(
            ["docker", "compose", "port", service, str(container_port)],
            cwd=DEMO_DIR, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if output:
            return "http://localhost:" + output.rsplit(":", 1)[1]
    except Exception:
        pass
    return fallback


JAEGER_BASE_URL = os.environ.get("JAEGER_BASE_URL", "http://localhost:8080/jaeger/ui")
PROMETHEUS_BASE_URL = os.environ.get("PROMETHEUS_BASE_URL", "http://localhost:9090")
OPENSEARCH_BASE_URL = os.environ.get("OPENSEARCH_BASE_URL") or _discover_port("opensearch", 9200, "http://localhost:9200")

# Locust UI of the load generator (throttle_load acts here). Its port is ephemeral, like OpenSearch's;
# Envoy also routes it at /loadgen on this demo version, which is the fallback.
LOADGEN_BASE_URL = os.environ.get("LOADGEN_BASE_URL") or _discover_port("load-generator", 8089, "http://localhost:8080/loadgen")

# team .env.local uses API_KEY / BASE_URL / MODEL_NAME; GROQ_API_KEY / LLM_* also accepted
LLM_API_KEY = os.environ.get("API_KEY") or os.environ.get("GROQ_API_KEY")
LLM_BASE_URL = os.environ.get("BASE_URL") or os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.environ.get("MODEL_NAME") or os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")

# Fallback when the primary is rate limited beyond its retries (e.g. a daily cap during the hidden test).
# Groq limits are per model, so by default we fall back to a different model on the same key;
# API_KEY_FALLBACK (a key from another account) is used instead when it is set.
LLM_API_KEY_FALLBACK = os.environ.get("API_KEY_FALLBACK") or LLM_API_KEY
LLM_BASE_URL_FALLBACK = os.environ.get("BASE_URL_FALLBACK") or LLM_BASE_URL
LLM_MODEL_FALLBACK = os.environ.get("MODEL_NAME_FALLBACK") or "openai/gpt-oss-20b"

DEFAULT_WINDOW_MINUTES = 15
MAX_ITEMS_PER_TOOL_RESULT = 15
MAX_TEXT_CHARS = 300
MAX_AGENT_ITERATIONS = 14
