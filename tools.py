# tools.py — the telemetry tools and the evidence registry. Pure Python, no LLM imports.
# Every tool returns small, flat, already-summarised data, and registers each item it returns
# in the evidence registry so the agent can only cite things a tool actually showed it.
#
# Debug any tool from the shell without spending an LLM call:
#   python tools.py get_service_health
#   python tools.py search_traces checkout
#   python tools.py get_trace <trace_id>
import datetime
import json
import re
import subprocess
import time

import requests

import config

# ---------------------------------------------------------------------------
# Evidence registry: one run of the agent owns one registry.
# reference token -> the exact item a tool returned. Checked in code, not in the prompt.
# ---------------------------------------------------------------------------
evidence_registry = {}


def reset_evidence_registry():
    evidence_registry.clear()


def register_evidence_item(kind, item):
    reference_token = kind + "-" + str(len(evidence_registry) + 1)
    evidence_registry[reference_token] = dict(item, reference=reference_token, kind=kind)
    return reference_token


def check_cited_evidence(cited_tokens):
    # returns the tokens the agent made up; an empty list means every citation is genuine
    return [token for token in cited_tokens if token not in evidence_registry]


# ---------------------------------------------------------------------------
# Rule 6 hygiene: diagnosis must come from telemetry, never from feature-flag settings.
# We never call flagd / the flag UI, we hide the flag services, and we strip anything in
# telemetry that names a feature flag, until a mentor confirms that is allowed.
# ---------------------------------------------------------------------------
HIDDEN_SERVICES = {"flagd", "flagd-ui", "jaeger", "jaeger-all-in-one", "otel-collector", "otelcol-contrib", "opensearch",
                   "prometheus", "grafana", "telemetry-docs", "opamp-server"}
# load generators / browser instrumentation measure end-to-end time, so they are never "the slow service"
CLIENT_SERVICES = {"load-generator", "frontend-web"}
_FLAG_MENTION = re.compile(r"feature[\s_.-]?flag|flagd|openfeature", re.IGNORECASE)
REDACTED = "[redacted by tool layer: text referenced a feature flag]"


def _clean_text(text, limit=None):
    if text is None:
        return None
    text = str(text)
    if _FLAG_MENTION.search(text):
        return REDACTED
    return text[: limit or config.MAX_TEXT_CHARS]


def _is_flag_key(key):
    return bool(_FLAG_MENTION.search(key))


def _now_iso(seconds=None):
    moment = datetime.datetime.fromtimestamp(seconds if seconds is not None else time.time(), datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _window(window_minutes):
    end = time.time()
    return {"from": _now_iso(end - window_minutes * 60), "to": _now_iso(end), "minutes": window_minutes}


# ---------------------------------------------------------------------------
# Prometheus (metrics + container health)
# ---------------------------------------------------------------------------
def run_prometheus_query(promql_query_string):
    # one place where Prometheus is called, so there is one place to debug
    response = requests.get(
        config.PROMETHEUS_BASE_URL + "/api/v1/query", params={"query": promql_query_string}, timeout=15
    )
    response.raise_for_status()
    return response.json()["data"]["result"]


_error_status_literal = None


def _error_status_code():
    # STATUS_CODE_ERROR vs Error differs by collector version: ask Prometheus once
    global _error_status_literal
    if _error_status_literal is None:
        try:
            values = requests.get(
                config.PROMETHEUS_BASE_URL + "/api/v1/label/status_code/values", timeout=10
            ).json()["data"]
            _error_status_literal = next((v for v in values if "ERROR" in v.upper()), "STATUS_CODE_ERROR")
        except Exception:
            _error_status_literal = "STATUS_CODE_ERROR"
    return _error_status_literal


def get_service_health(window_minutes=5):
    """Error ratio, request rate and p95 latency per service, worst first.
    Also flags services that reported in the last hour but have gone silent (likely DOWN)."""
    window_minutes = max(2, int(window_minutes))
    window = str(window_minutes) + "m"
    error_code = _error_status_code()
    queries = {
        "error_ratio": (
            'sum by (service_name) (rate(traces_span_metrics_calls_total{status_code="' + error_code + '"}[' + window + "]))"
            " / sum by (service_name) (rate(traces_span_metrics_calls_total[" + window + "]))"
        ),
        "requests_per_second": "sum by (service_name) (rate(traces_span_metrics_calls_total[" + window + "]))",
        "p95_latency_ms": (
            "histogram_quantile(0.95, sum by (service_name, le) "
            "(rate(traces_span_metrics_duration_milliseconds_bucket[" + window + "])))"
        ),
        "seen_last_hour": "max by (service_name) (max_over_time(traces_span_metrics_calls_total[60m]))",
    }
    rows = {}
    timestamps = {}
    for field, promql in queries.items():
        for result_row in run_prometheus_query(promql):
            service_name = result_row["metric"].get("service_name", "unknown")
            if service_name in HIDDEN_SERVICES:
                continue
            value = float(result_row["value"][1])
            if value != value:  # NaN: no traffic, not an error
                value = None
            row = rows.setdefault(service_name, {"service": service_name, "error_ratio": 0.0,
                                                 "requests_per_second": 0.0, "p95_latency_ms": None})
            if field == "seen_last_hour":
                continue
            if value is not None:
                row[field] = round(value, 4 if field == "error_ratio" else 2)
            timestamps[service_name] = _now_iso(float(result_row["value"][0]))

    for row in rows.values():
        if row["requests_per_second"] == 0.0:
            row["status_hint"] = "NOT_REPORTING (seen in last hour, no spans now: likely down)"
        elif row["service"] in CLIENT_SERVICES:
            # traffic generators: their errors/latency only mirror downstream services (~5% errors even when healthy)
            row["status_hint"] = "ok (client: its errors and latency reflect downstream services, never the root cause)"
        elif row["error_ratio"] >= 0.05:
            row["status_hint"] = "ERRORS"
        elif row["p95_latency_ms"] and row["p95_latency_ms"] >= 1000:
            row["status_hint"] = "SLOW"
        else:
            row["status_hint"] = "ok"

    ordered = sorted(rows.values(), key=_health_sort_key, reverse=True)
    for row in ordered[: config.MAX_ITEMS_PER_TOOL_RESULT]:
        if row["status_hint"].startswith("ok"):
            continue  # only unhealthy rows are worth citing; keeps the registry small
        metric_name = "error_ratio" if row["status_hint"] == "ERRORS" else (
            "p95_latency_ms" if row["status_hint"] == "SLOW" else "requests_per_second")
        row["ref"] = register_evidence_item("metric", {
            "service": row["service"],
            "metric": metric_name,
            "value": row[metric_name],
            "promql": queries[metric_name],
            "timestamp": timestamps.get(row["service"], _now_iso()),
        })
    return {"window": _window(window_minutes), "services": ordered[: config.MAX_ITEMS_PER_TOOL_RESULT * 2]}


def _health_sort_key(row):
    # down first, then by error ratio, then by latency
    return (row["status_hint"].startswith("NOT_REPORTING"), row["error_ratio"], row["p95_latency_ms"] or 0)


# container metric names vary by collector version; resolve them once from Prometheus
_container_metric_names = None


def _container_metrics():
    global _container_metric_names
    if _container_metric_names is None:
        all_names = requests.get(config.PROMETHEUS_BASE_URL + "/api/v1/label/__name__/values", timeout=10).json()["data"]

        def first(*candidates):
            return next((name for name in candidates if name in all_names), None)

        _container_metric_names = {
            "cpu": first("container_cpu_utilization_ratio", "container_cpu_utilization", "container_cpu_percent"),
            "memory": first("container_memory_usage_total_bytes", "container_memory_usage_total"),
            "memory_limit": first("container_memory_usage_limit_bytes", "container_memory_usage_limit"),
            "memory_percent": first("container_memory_percent_ratio", "container_memory_percent"),
            "uptime": first("container_uptime_seconds", "container_uptime"),
            "restarts": first("container_restarts_total", "container_restarts"),
        }
    return _container_metric_names


DEMO_COMPOSE_PROJECT = "opentelemetry-demo"


def _docker_containers():
    # the Docker engine's view of the demo's containers (only this compose project, not other apps on the laptop)
    names = subprocess.run(
        ["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=" + DEMO_COMPOSE_PROJECT, "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=20,
    ).stdout.split()
    if not names:
        return []
    return json.loads(subprocess.run(["docker", "inspect", *names], capture_output=True, text=True, timeout=30).stdout or "[]")


def get_container_health(window_minutes=15):
    """Per-container state and resources: docker state (stopped / exit code / OOM-killed / restart count / CPU limit)
    plus CPU, memory vs limit and uptime resets from the collector's docker_stats metrics.
    Catches infrastructure faults that never show up in traces."""
    window_minutes = max(2, int(window_minutes))
    window = str(window_minutes) + "m"
    names = _container_metrics()
    metrics_by_container = {}
    used_queries = {}

    def collect(field, promql):
        used_queries[field] = promql
        for result_row in run_prometheus_query(promql):
            container = result_row["metric"].get("container_name") or "unknown"
            value = float(result_row["value"][1])
            if value == value:  # skip NaN
                metrics_by_container.setdefault(container, {})[field] = round(value, 3)
                metrics_by_container[container]["_ts"] = _now_iso(float(result_row["value"][0]))

    if names["cpu"]:
        collect("cpu_cores_used", "max by (container_name) (avg_over_time(" + names["cpu"] + "[2m]))")
    if names["memory"] and names["memory_limit"]:
        collect("memory_pct_of_limit",
                "max by (container_name) (" + names["memory"] + ") / max by (container_name) (" + names["memory_limit"] + ") * 100")
    if names["uptime"]:
        collect("uptime_resets_in_window", "max by (container_name) (resets(" + names["uptime"] + "[" + window + "]))")

    now = time.time()
    containers = _docker_containers()
    recently_started = [c for c in containers if now - _parse_docker_time(c["State"].get("StartedAt", "")[:19]) < window_minutes * 60]
    stack_restart = len(containers) > 0 and len(recently_started) > len(containers) / 2

    rows = []
    for container in containers:
        name = container["Name"].lstrip("/")
        if name in HIDDEN_SERVICES:
            continue
        state = container["State"]
        metrics = metrics_by_container.get(name, {})
        started_epoch = _parse_docker_time(state.get("StartedAt", "")[:19])
        nano_cpus = container["HostConfig"].get("NanoCpus") or 0
        row = {
            "container": name,
            "state": state.get("Status"),
            "uptime_seconds": int(now - started_epoch) if state.get("Running") else 0,
            "restart_count": container.get("RestartCount", 0),
            "cpu_limit_cores": round(nano_cpus / 1e9, 3) if nano_cpus else None,
            "cpu_cores_used": metrics.get("cpu_cores_used"),
            "memory_pct_of_limit": metrics.get("memory_pct_of_limit"),
            "uptime_resets_in_window": metrics.get("uptime_resets_in_window"),
        }
        problems = []
        if not state.get("Running"):
            problems.append("NOT_RUNNING (state=%s exit_code=%s since %s)" % (state.get("Status"), state.get("ExitCode"), state.get("FinishedAt", "")[:19] + "Z"))
        if state.get("OOMKilled"):
            problems.append("OOM_KILLED")
        if (metrics.get("uptime_resets_in_window") or 0) >= 2 or row["restart_count"] >= 2:
            problems.append("RESTART_LOOP")
        elif state.get("Running") and row["uptime_seconds"] < 120 and not stack_restart:
            problems.append("JUST_RESTARTED (uptime %ds)" % row["uptime_seconds"])
        if (row["memory_pct_of_limit"] or 0) >= 98:  # JVMs (kafka) idle at ~95%
            problems.append("MEMORY_NEAR_LIMIT")
        if row["cpu_limit_cores"] is not None and row["cpu_limit_cores"] < 0.5:
            problems.append("CPU_LIMITED (limit %.2f cores)" % row["cpu_limit_cores"])
        row["problems"] = problems
        if problems:
            source_query = "docker inspect " + name
            value = row["state"]
            if problems[0].startswith(("RESTART_LOOP", "JUST_RESTARTED")):
                source_query, value = used_queries.get("uptime_resets_in_window", source_query), row["uptime_resets_in_window"]
            elif problems[0] == "MEMORY_NEAR_LIMIT":
                source_query, value = used_queries.get("memory_pct_of_limit", source_query), row["memory_pct_of_limit"]
            elif problems[0].startswith("CPU_LIMITED"):
                value = row["cpu_limit_cores"]
            row["ref"] = register_evidence_item("metric", {
                "service": name,
                "metric": "container." + problems[0].split(" ")[0].lower(),
                "value": value,
                "promql": source_query,
                "timestamp": metrics.get("_ts", _now_iso()),
            })
        rows.append(row)

    rows.sort(key=lambda row: (len(row["problems"]), row["cpu_cores_used"] or 0), reverse=True)
    result = {
        "window": _window(window_minutes),
        "containers_checked": len(rows),
        "containers_with_problems": [row for row in rows if row["problems"]],
        "busiest_cpu": [{"container": r["container"], "cpu_cores_used": r["cpu_cores_used"]} for r in rows if not r["problems"]][:5],
        "note": "cpu_cores_used is in cores (1.0 = one full core). A tiny cpu_limit_cores with high latency = CPU starvation.",
    }
    if stack_restart:
        result["stack_restart"] = ("%d of %d containers started within the window: the whole stack was restarted, "
                                   "so a single uptime reset is NOT evidence of a fault." % (len(recently_started), len(containers)))
    return result


# ---------------------------------------------------------------------------
# Jaeger (traces). Jaeger 2.x in this demo only serves the v3 API (/api/v3/...), which returns
# OTLP JSON: resourceSpans -> scopeSpans -> spans, status.code 2 = ERROR, exceptions in events.
# The v3 search ignores attribute filters, so "only errors" is filtered here, client side.
# ---------------------------------------------------------------------------
def _jaeger_v3(path, params=None):
    response = requests.get(config.JAEGER_BASE_URL + "/api/v3" + path, params=params, timeout=30)
    if response.status_code == 404 and "No traces found" in response.text:
        return {"result": {"resourceSpans": []}}
    response.raise_for_status()
    return response.json()


def list_services():
    """Names of every service that has sent traces."""
    names = _jaeger_v3("/services").get("services") or []
    return sorted(name for name in names if name not in HIDDEN_SERVICES)


def _otlp_value(value):
    # OTLP JSON wraps every attribute value: {"stringValue": ...} / {"intValue": "3"} / {"boolValue": true}
    for kind in ("stringValue", "boolValue", "intValue", "doubleValue"):
        if kind in value:
            return value[kind]
    return None


def _attributes(attribute_list):
    return {a["key"]: _otlp_value(a.get("value", {})) for a in attribute_list or [] if not _is_flag_key(a["key"])}


def _spans_by_trace(v3_body):
    # flatten OTLP resourceSpans into {trace_id: [flat span, ...]}
    traces = {}
    for resource_spans in (v3_body.get("result") or {}).get("resourceSpans", []):
        service = _attributes(resource_spans.get("resource", {}).get("attributes")).get("service.name", "unknown")
        for scope_spans in resource_spans.get("scopeSpans", []):
            for raw_span in scope_spans.get("spans", []):
                attributes = _attributes(raw_span.get("attributes"))
                status = raw_span.get("status") or {}
                has_error = status.get("code") in (2, "STATUS_CODE_ERROR") or attributes.get("error") in (True, "true")
                exception_message = None
                for event in raw_span.get("events", []):
                    event_attributes = _attributes(event.get("attributes"))
                    if event_attributes.get("exception.message"):
                        exception_message = event_attributes["exception.message"]
                        break
                exception_message = (exception_message or status.get("message") or attributes.get("error.message")
                                     or attributes.get("exception.message"))
                start_ns = int(raw_span["startTimeUnixNano"])
                traces.setdefault(raw_span["traceId"], []).append({
                    "span_id": raw_span["spanId"],
                    "parent_span_id": raw_span.get("parentSpanId") or None,
                    "service": service,
                    "operation": raw_span["name"],
                    "start_us": start_ns // 1000,
                    "duration_ms": round((int(raw_span["endTimeUnixNano"]) - start_ns) / 1_000_000.0, 1),
                    "has_error": bool(has_error),
                    "exception": _clean_text(exception_message),
                    "peer": attributes.get("rpc.service") or attributes.get("server.address") or attributes.get("net.peer.name"),
                })
    return traces


def find_deepest_failing_spans(flattened_spans):
    # A failing span whose own children did not fail is where the problem starts;
    # everything above it is just propagating the error upward. Deterministic, so done in code.
    span_ids_with_failing_child = {s["parent_span_id"] for s in flattened_spans if s["has_error"] and s["parent_span_id"]}
    candidates = [s for s in flattened_spans if s["has_error"] and s["span_id"] not in span_ids_with_failing_child]
    # Proxies (envoy) and load generators can break the parent links, so a span high in the tree may
    # look "childless". Rank by real depth, then prefer spans that carry an exception message.
    by_id = {s["span_id"]: s for s in flattened_spans}

    def depth(span):
        steps, cursor = 0, span
        while cursor.get("parent_span_id") in by_id and steps < 100:
            cursor = by_id[cursor["parent_span_id"]]
            steps += 1
        return steps

    return sorted(candidates, key=lambda s: (depth(s), s.get("exception") is not None), reverse=True)


def _self_time_hotspot(flattened_spans):
    # the span with the most time not explained by its children = where latency is actually spent
    child_time = {}
    for span in flattened_spans:
        if span["parent_span_id"]:
            child_time[span["parent_span_id"]] = child_time.get(span["parent_span_id"], 0) + span["duration_ms"]
    best = None
    for span in flattened_spans:
        if span["service"] in CLIENT_SERVICES:
            continue
        self_time = span["duration_ms"] - child_time.get(span["span_id"], 0)
        if best is None or self_time > best[0]:
            best = (self_time, span)
    return (best[1], round(best[0], 1)) if best else (None, 0)


def _span_label(span):
    text = span["service"] + " " + span["operation"]
    if span.get("peer") and span["peer"] not in text:
        text += " -> " + str(span["peer"])
    return text


def search_traces(service, only_errors=True, min_duration_ms=None, limit=10, window_minutes=15):
    """Recent traces through `service`. Each result names the deepest failing span and the self-time hotspot."""
    only_errors = only_errors in (True, "true", "True", "1", 1)
    end = time.time()
    params = {
        "query.service_name": service,
        "query.start_time_min": _now_iso(end - int(window_minutes) * 60),
        "query.start_time_max": _now_iso(end + 5),
        # errors are filtered client side, so look at more traces than we will return
        "query.search_depth": 100 if only_errors else min(int(limit), 20),
    }
    if min_duration_ms:
        params["query.duration_min"] = str(float(min_duration_ms) / 1000.0) + "s"
    traces = _spans_by_trace(_jaeger_v3("/traces", params))
    scanned = len(traces)
    summaries = []
    for trace_id, spans in sorted(traces.items(), key=lambda kv: -max(s["start_us"] for s in kv[1])):
        deepest = find_deepest_failing_spans(spans)
        if only_errors and not deepest:
            continue
        root = min(spans, key=lambda s: s["start_us"])
        hotspot, hotspot_self_ms = _self_time_hotspot(spans)
        culprit = deepest[0] if deepest else hotspot
        summaries.append({
            "trace_id": trace_id,
            "start": _now_iso(root["start_us"] / 1_000_000),
            "root": root["service"] + " " + root["operation"],
            "duration_ms": round((max(s["start_us"] + s["duration_ms"] * 1000 for s in spans) - root["start_us"]) / 1000.0, 1),
            "span_count": len(spans),
            "services_with_errors": sorted({s["service"] for s in spans if s["has_error"]}),
            "deepest_failing": [_span_label(d) + (" :: " + d["exception"] if d["exception"] else "") for d in deepest[:3]],
            "slowest_self_time": (_span_label(hotspot) + " (" + str(hotspot_self_ms) + " ms self)") if hotspot else None,
            "ref": register_evidence_item("trace", {
                "trace_id": trace_id, "service": culprit["service"], "span_name": culprit["operation"],
                "duration_ms": culprit["duration_ms"], "status": "ERROR" if culprit["has_error"] else "OK",
                "exception": culprit["exception"],
            }),
        })
        if len(summaries) >= min(int(limit), config.MAX_ITEMS_PER_TOOL_RESULT):
            break
    return {"window": _window(int(window_minutes)), "service": service, "only_errors": only_errors,
            "traces_scanned": scanned, "count": len(summaries), "traces": summaries}


def get_trace(trace_id):
    """One trace as a flattened span list (one line per span, NOT raw Jaeger JSON),
    with the deepest failing spans and the latency hotspot computed for you."""
    spans = _spans_by_trace(_jaeger_v3("/traces/" + trace_id)).get(trace_id, [])
    if not spans:
        return {"trace_id": trace_id, "error": "trace not found (expired from Jaeger's in-memory store, or wrong id)"}
    deepest = find_deepest_failing_spans(spans)
    hotspot, hotspot_self_ms = _self_time_hotspot(spans)

    deepest_out = []
    for span in deepest[:5]:
        deepest_out.append({
            "service": span["service"], "operation": span["operation"], "peer": span.get("peer"),
            "duration_ms": span["duration_ms"], "exception": span["exception"],
            "ref": register_evidence_item("trace", {
                "trace_id": trace_id, "service": span["service"], "span_name": span["operation"],
                "duration_ms": span["duration_ms"], "status": "ERROR", "exception": span["exception"],
            }),
        })
    hotspot_out = None
    if hotspot:
        hotspot_out = {
            "service": hotspot["service"], "operation": hotspot["operation"], "self_time_ms": hotspot_self_ms,
            "duration_ms": hotspot["duration_ms"],
            "ref": register_evidence_item("trace", {
                "trace_id": trace_id, "service": hotspot["service"], "span_name": hotspot["operation"],
                "duration_ms": hotspot["duration_ms"], "status": "ERROR" if hotspot["has_error"] else "OK",
                "exception": hotspot["exception"],
            }),
        }

    # keep error spans and their ancestors first, then the slowest others; cap at 30 lines
    by_id = {s["span_id"]: s for s in spans}
    keep = []
    for span in deepest:
        cursor = span
        while cursor and cursor not in keep:
            keep.append(cursor)
            cursor = by_id.get(cursor["parent_span_id"])
    for span in sorted(spans, key=lambda s: s["duration_ms"], reverse=True):
        if len(keep) >= 30:
            break
        if span not in keep:
            keep.append(span)
    lines = []
    for span in sorted(keep, key=lambda s: s["start_us"]):
        parent = by_id.get(span["parent_span_id"])
        lines.append(
            _span_label(span) + " | " + str(span["duration_ms"]) + "ms | " + ("ERROR" if span["has_error"] else "ok")
            + " | parent=" + (parent["service"] if parent else "-")
            + (" | " + span["exception"] if span["exception"] else "")
        )
    return {
        "trace_id": trace_id,
        "span_count": len(spans),
        "spans_shown": len(lines),
        "spans": lines,
        "deepest_failing_spans": deepest_out,
        "latency_hotspot": hotspot_out,
    }


# ---------------------------------------------------------------------------
# OpenSearch (logs)
# ---------------------------------------------------------------------------
LOG_INDEX = "otel-logs-*"


def _first_present(document, *dotted_paths):
    # OpenSearch exporters nest fields differently by version: try each candidate path
    for dotted in dotted_paths:
        cursor = document
        for part in dotted.split("|"):
            if isinstance(cursor, dict) and part in cursor:
                cursor = cursor[part]
            else:
                cursor = None
                break
        if cursor not in (None, "", {}):
            return cursor
    return None


# Field names verified against this stack's otel-logs-* documents (runbook step 6):
# message = body, service = resource."service.name" (flat dotted key), time = @timestamp,
# severity = severity.text / severity.number, trace = traceId
SERVICE_FIELD = "resource.service.name"


def _service_field_name():
    return SERVICE_FIELD


def search_logs(service=None, contains=None, window_minutes=15, limit=15, min_severity=None):
    """Log records filtered by service, time window and optional text, newest first.
    min_severity='WARN' or 'ERROR' keeps only warnings/errors."""
    window_minutes = int(window_minutes)
    filters = [{"range": {"@timestamp": {"gte": "now-" + str(window_minutes) + "m"}}}]
    if service:
        filters.append({"bool": {"should": [
            {"term": {field: service}} for field in [_service_field_name(), _service_field_name() + ".keyword"]
        ] + [{"match_phrase": {_service_field_name(): service}}], "minimum_should_match": 1}})
    if contains:
        filters.append({"match_phrase": {"body": contains}})
    if min_severity:
        threshold = {"WARN": 13, "WARNING": 13, "ERROR": 17, "FATAL": 21}.get(str(min_severity).upper(), 1)
        filters.append({"bool": {"should": [
            {"range": {"severityNumber": {"gte": threshold}}},
            {"range": {"severity.number": {"gte": threshold}}},
        ], "minimum_should_match": 1}})
    query = {
        "size": 100,  # headroom: redacted rows and repeated lines are dropped before returning
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {"bool": {"filter": filters}},
    }
    response = requests.post(config.OPENSEARCH_BASE_URL + "/" + LOG_INDEX + "/_search", json=query, timeout=20)
    response.raise_for_status()
    hits = response.json()["hits"]["hits"]
    items = []
    seen_messages = {}
    redacted_count = 0
    for hit in hits:
        source = hit["_source"]
        message = _clean_text(_first_present(source, "body", "Body", "message"))
        if message == REDACTED:
            redacted_count += 1
            continue
        record_service = _first_present(source, "resource|service.name", "resource|attributes|service.name",
                                        "resource|attributes|service@name", "resource|service|name") or service
        item = {
            "timestamp": _first_present(source, "@timestamp", "time", "observedTimestamp"),
            "service": record_service,
            "severity": _first_present(source, "severity|text", "severityText", "severity_text") or "",
            "message": message,
        }
        trace_id = _first_present(source, "traceId", "trace_id")
        if trace_id:
            item["trace_id"] = trace_id
        repeat_key = (record_service, item["severity"], message)
        if repeat_key in seen_messages:  # identical line again: count it instead of spending tokens on it
            seen_messages[repeat_key]["repeats_in_results"] = seen_messages[repeat_key].get("repeats_in_results", 1) + 1
            continue
        item["ref"] = register_evidence_item("log", item)
        seen_messages[repeat_key] = item
        items.append(item)
        if len(items) >= min(int(limit), config.MAX_ITEMS_PER_TOOL_RESULT):
            break
    result = {"window": _window(window_minutes), "service": service, "contains": contains,
              "count": len(items), "logs": items}
    if redacted_count:
        result["redacted_records"] = redacted_count
    return result


# ---------------------------------------------------------------------------
# Deploy history (STAND-IN until the organisers' deploy-history source is known)
# ---------------------------------------------------------------------------
def get_deploy_history(window_minutes=60):
    """Recent changes to running containers: image, when each was created/started, restart count.
    Source: `docker inspect` (stand-in until the organisers' deploy history is known)."""
    inspected = [c for c in _docker_containers() if c["Name"].lstrip("/") not in HIDDEN_SERVICES]
    if not inspected:
        return {"changes": [], "note": "docker not reachable"}
    cutoff = time.time() - int(window_minutes) * 60
    changes = []
    for container in inspected:
        state = container["State"]
        started = state.get("StartedAt", "")[:19]
        started_epoch = _parse_docker_time(started)
        if state.get("Running") and started_epoch < cutoff and container.get("RestartCount", 0) == 0:
            continue  # unchanged and healthy: not interesting
        changes.append({
            "service": container["Name"].lstrip("/"),
            "image": container["Config"]["Image"].split("/")[-1],
            "state": state.get("Status"),
            "started_at": started + "Z",
            "finished_at": (state.get("FinishedAt", "")[:19] + "Z") if not state.get("Running") else None,
            "restart_count": container.get("RestartCount", 0),
            "cpu_limit_nano": container["HostConfig"].get("NanoCpus", 0) or None,
        })
    changes.sort(key=lambda change: change["started_at"], reverse=True)
    result = {"window": _window(int(window_minutes)), "changes": changes[: config.MAX_ITEMS_PER_TOOL_RESULT],
              "note": "Lists containers started/stopped/restarted or re-limited in the window. Empty = no recent changes."}
    if len(changes) > len(inspected) / 2:
        result["stack_restart"] = "%d of %d containers changed in the window: a stack-wide restart, not a targeted change." % (
            len(changes), len(inspected))
    return result


def _parse_docker_time(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return 0


if __name__ == "__main__":
    import sys

    function_name = sys.argv[1]
    function_arguments = sys.argv[2:]
    function_to_call = globals()[function_name]
    print(json.dumps(function_to_call(*function_arguments), indent=2, default=str))
    if evidence_registry:
        print("# registered evidence:", ", ".join(evidence_registry), file=sys.stderr)
