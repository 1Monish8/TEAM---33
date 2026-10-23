# Offline tests: no stack, no LLM. Run with  python -m pytest tests  or  python tests/test_offline.py
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import agent  # noqa: E402
import report  # noqa: E402
import tools  # noqa: E402


def _run():
    return {"incident_id": "t-1", "alert": "test alert", "log": [{"tool": "get_service_health"}],
            "started": 0, "started_iso": "2026-10-23T00:00:00Z"}


def _seed_registry():
    tools.reset_evidence_registry()
    metric = tools.register_evidence_item("metric", {"service": "payment", "metric": "error_ratio", "value": 0.5,
                                                     "promql": "x", "timestamp": "2026-10-23T00:00:00Z"})
    trace = tools.register_evidence_item("trace", {"trace_id": "abc", "service": "payment", "span_name": "Charge",
                                                   "duration_ms": 3.0, "status": "ERROR", "exception": "boom"})
    log = tools.register_evidence_item("log", {"timestamp": "2026-10-23T00:00:01Z", "service": "payment",
                                               "severity": "ERROR", "message": "Payment request failed"})
    return metric, trace, log


def _args(evidence, confidence=0.9, status="diagnosed"):
    return {"status": status, "root_cause_service": "payment", "fault_type": "application_error",
            "root_cause_summary": "payment Charge fails with an exception.", "confidence": confidence,
            "evidence": [{"ref": r} for r in evidence], "action": "restart_service", "action_target": "payment",
            "action_reason": "test"}


def test_invented_evidence_is_rejected():
    _seed_registry()
    diagnosis, problem = agent.build_diagnosis(_args(["trace-2", "trace-99"]), _run())
    assert diagnosis is None and "trace-99" in problem


def test_two_sources_allow_high_confidence_and_valid_schema():
    metric, trace, log = _seed_registry()
    diagnosis, problem = agent.build_diagnosis(_args([metric, trace, log]), _run())
    assert problem is None, problem
    assert diagnosis["confidence_label"] == "high"
    assert report.schema_errors(diagnosis) == []


def test_single_source_caps_confidence_at_medium():
    _, trace, _ = _seed_registry()
    diagnosis, _ = agent.build_diagnosis(_args([trace]), _run())
    assert diagnosis["confidence_label"] == "medium"
    assert diagnosis["investigation"]["calibration_notes"]


def test_escalation_forces_low_confidence_and_escalate_action():
    metric, _, _ = _seed_registry()
    diagnosis, _ = agent.build_diagnosis(_args([metric], confidence=0.8, status="escalated"), _run())
    assert diagnosis["confidence_label"] == "low"
    assert diagnosis["proposed_action"]["action"] == "escalate_to_human"


def test_diagnosed_without_evidence_on_root_service_is_rejected():
    tools.reset_evidence_registry()
    other = tools.register_evidence_item("metric", {"service": "frontend", "metric": "error_ratio", "value": 0.3,
                                                    "promql": "x", "timestamp": "t"})
    diagnosis, problem = agent.build_diagnosis(_args([other]), _run())
    assert diagnosis is None and "payment" in problem


def test_stale_evidence_does_not_count_toward_confidence():
    import time
    tools.reset_evidence_registry()
    old_trace = tools.register_evidence_item("trace", {"trace_id": "old", "service": "cart", "span_name": "EmptyCart",
                                                       "duration_ms": 1.0, "status": "ERROR", "exception": "redis",
                                                       "timestamp": "2026-10-23T00:00:00Z"})
    old_log = tools.register_evidence_item("log", {"timestamp": "2026-10-23T00:00:01Z", "service": "cart",
                                                   "severity": "Error", "message": "Wasn't able to connect to redis"})
    run = dict(_run(), started=time.time())
    arguments = dict(_args([old_trace, old_log]), root_cause_service="cart")
    diagnosis, problem = agent.build_diagnosis(arguments, run)
    assert diagnosis is None and "CURRENT" in problem  # only stale evidence -> cannot claim diagnosed


def test_deepest_failing_span_is_the_callee_not_the_frontend():
    spans = [
        {"span_id": "1", "parent_span_id": None, "service": "frontend", "has_error": True},
        {"span_id": "2", "parent_span_id": "1", "service": "checkout", "has_error": True},
        {"span_id": "3", "parent_span_id": "2", "service": "payment", "has_error": True},
        {"span_id": "4", "parent_span_id": "2", "service": "currency", "has_error": False},
    ]
    assert [s["service"] for s in tools.find_deepest_failing_spans(spans)] == ["payment"]


def test_feature_flag_text_is_redacted():
    assert tools._clean_text("Feature Flag adManualGc enabled, performing a manual gc now") == tools.REDACTED
    assert tools._clean_text("Warning: FeatureFlag 'kafkaQueueProblems' is activated") == tools.REDACTED
    assert tools._is_flag_key("demo.feature_flag.recommendation_cache")
    assert tools._clean_text("Payment request failed. Invalid token.") == "Payment request failed. Invalid token."


# ---------------------------------------------------------------------------
# Day 2: the no-error branch (baselines) and the act-and-verify loop's safety gates
# ---------------------------------------------------------------------------
def _health_row(**overrides):
    row = {"service": "accounting", "error_ratio": 0.0, "error_ratio_baseline": None, "requests_per_second": 1.0, "p95_latency_ms": 15000.0,
           "p95_baseline_ms": 15000.0, "status_hint": "ok"}
    row.update(overrides)
    return row


def test_missing_baseline_fails_closed_and_chronic_latency_scores_zero():
    # Day 1's three confident-wrong answers: accounting at its NORMAL 15 s was called SLOW
    assert tools._is_slower_than_baseline(_health_row(p95_baseline_ms=None)) is False
    assert tools._deviation_score(_health_row()) == 0.0
    # a service whose latency tripled IS slow, and a newly failing one outranks it
    assert tools._is_slower_than_baseline(_health_row(service="ad", p95_latency_ms=900.0, p95_baseline_ms=300.0))
    slower = tools._deviation_score(_health_row(service="ad", p95_latency_ms=900.0, p95_baseline_ms=300.0))
    failing = tools._deviation_score(_health_row(service="payment", error_ratio=0.5, p95_latency_ms=5.0, p95_baseline_ms=5.0))
    assert failing > slower > 0


def test_down_vs_idle_vs_low_traffic_errors():
    # Two bugs found in live tests: (1) payment at ~0.04 req/s was rounded to 0.0 and called IDLE despite 57%
    # errors; (2) services silent only because their caller failed were ranked as "down" above the real cause.
    rows = {  # field -> {service: value}, as Prometheus would return them
        "error_ratio": {"payment": 0.57, "currency": 0.0, "fraud-detection": 0.0},
        "requests_per_second": {"payment": 0.04, "currency": 0.3, "fraud-detection": 0.0},
        "p95_latency_ms": {"payment": 5.0, "currency": 2.0},
        "seen_last_hour": {"payment": 1, "currency": 1, "fraud-detection": 1},
        "error_ratio_baseline": {"payment": 0.03},
        "p95_baseline_ms": {"payment": 5.0, "currency": 2.0, "fraud-detection": 90.0},
    }
    saved = (tools.run_prometheus_query, tools._docker_containers, tools._span_metrics_age_seconds)

    def fake_query(promql):
        # route each PromQL query to the field it computes
        if "quantile_over_time" in promql and "STATUS_CODE_ERROR" in promql:
            field = "error_ratio_baseline"
        elif "quantile_over_time" in promql:
            field = "p95_baseline_ms"
        elif "max_over_time" in promql:
            field = "seen_last_hour"
        elif "histogram_quantile" in promql:
            field = "p95_latency_ms"
        elif "/ sum by" in promql:
            field = "error_ratio"
        else:
            field = "requests_per_second"
        return [{"metric": {"service_name": service}, "value": [0, str(value)]} for service, value in rows[field].items()]

    tools.run_prometheus_query = fake_query
    tools._span_metrics_age_seconds = lambda: 30
    tools._docker_containers = lambda: [{"Name": "/payment", "State": {"Status": "running"}},
                                        {"Name": "/currency", "State": {"Status": "exited"}},
                                        {"Name": "/fraud-detection", "State": {"Status": "running"}}]
    tools._error_status_literal = "STATUS_CODE_ERROR"
    try:
        tools.reset_evidence_registry()
        health = {row["service"]: row for row in tools.get_service_health(5)["services"]}
        assert health["payment"]["status_hint"] == "ERRORS"                       # low traffic, but failing
        assert health["currency"]["status_hint"].startswith("NOT_REPORTING: DOWN")  # container exited
        assert health["fraud-detection"]["status_hint"].startswith("IDLE")         # a victim, not the cause
        ranking = [name for name, _ in tools.last_deviation_ranking]
        assert ranking[0] == "currency" and ranking.index("payment") < ranking.index("fraud-detection")
    finally:
        tools.run_prometheus_query, tools._docker_containers, tools._span_metrics_age_seconds = saved


def test_a_rejected_tool_call_never_crashes_the_run():
    # Found in the Day 2 sweep: Groq answered HTTP 400 "Tool call validation failed" and the run crashed.
    import json
    import types
    import llm
    calls = {"n": 0}
    submit = {"status": "escalated", "root_cause_service": None, "fault_type": "unknown",
              "root_cause_summary": "Not enough evidence to name a component.", "confidence": 0.3, "evidence": [],
              "action": "escalate_to_human", "action_target": None, "action_reason": "not confident"}

    def fake_chat(messages, tools=None, tool_choice="auto", temperature=0.0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise llm.ToolCallRejected("Tool call validation failed: parameter action_parameters must be object")
        call = types.SimpleNamespace(id="c1", function=types.SimpleNamespace(name="submit_diagnosis", arguments=json.dumps(submit)))
        return types.SimpleNamespace(content="", tool_calls=[call])

    saved = llm.chat
    llm.chat = fake_chat
    try:
        diagnosis = agent.run_investigation("test alert", "t-400", review_enabled=False)
    finally:
        llm.chat = saved
    assert calls["n"] == 2 and diagnosis["status"] == "escalated" and report.schema_errors(diagnosis) == []


import tempfile  # noqa: E402

import actions  # noqa: E402


def _with_temp_action_log(test):
    # every action test writes to a throwaway log and kill-switch path, never the real ones
    def wrapper():
        saved = (actions.ACTION_LOG, actions.KILL_SWITCH_FILE, agent.KILL_SWITCH_FILE, actions.capture_state, actions._run,
                 agent.verify.snapshot, agent.verify.confirm_recovery)
        with tempfile.TemporaryDirectory() as folder:
            actions.ACTION_LOG = pathlib.Path(folder) / "action_log.jsonl"
            actions.KILL_SWITCH_FILE = agent.KILL_SWITCH_FILE = pathlib.Path(folder) / "KILL_SWITCH"
            try:
                test()
            finally:
                (actions.ACTION_LOG, actions.KILL_SWITCH_FILE, agent.KILL_SWITCH_FILE, actions.capture_state, actions._run,
                 agent.verify.snapshot, agent.verify.confirm_recovery) = saved
    wrapper.__name__ = test.__name__
    return wrapper


def _diagnosis(confidence=0.8, status="diagnosed"):
    return {"incident_id": "t-act", "status": status, "confidence": confidence, "confidence_label": agent._label_for(confidence),
            "root_cause": {"service": "frontend", "fault_type": "traffic_surge", "summary": "flood of requests"},
            "evidence": [], "proposed_action": {"action": "throttle_load", "target": "load-generator",
                                                "parameters": {"user_count": 1}, "reason": "test", "requires_approval": True}}


def _stub_loop(recovered, executed):
    # stand-ins for docker and Prometheus, so the safety logic is tested on its own
    agent.verify.snapshot = lambda service, window_minutes=5: {"service": service}
    agent.verify.confirm_recovery = lambda before, **kw: {"recovered": recovered, "verdict": "stub", "checks": []}
    actions.capture_state = lambda action, target, parameters=None: {"user_count": 7}
    actions._run = lambda action, target, parameters: executed.append((action, target, dict(parameters))) or {"ok": True}


QUIET = {"progress": lambda text: None}


@_with_temp_action_log
def test_execute_refuses_without_approval_and_under_kill_switch():
    assert actions.execute("throttle_load", "load-generator", {"user_count": 1})["ok"] is False
    actions.KILL_SWITCH_FILE.write_text("stop")
    assert "KILL_SWITCH" in actions.execute("throttle_load", "load-generator", {"user_count": 1}, approved=True)["reason"]
    assert len(actions.read_log()) == 2  # refusals are logged too
    assert actions.describe("scale_service", "payment")["ok"] is False  # honest: Kubernetes only
    assert actions.describe("rm_rf", "payment")["ok"] is False          # not allowlisted


@_with_temp_action_log
def test_human_no_means_nothing_changes():
    executed = []
    _stub_loop(True, executed)
    loop = agent.act_on_diagnosis(_diagnosis(), ask=lambda question: "n", **QUIET)
    assert executed == [] and loop["approved"] is False and "rejected" in loop["outcome"]


@_with_temp_action_log
def test_low_confidence_and_escalation_never_act():
    executed = []
    _stub_loop(True, executed)
    yes = lambda question: "y"  # noqa: E731
    assert "below" in agent.act_on_diagnosis(_diagnosis(confidence=0.4), ask=yes, **QUIET)["outcome"]
    assert "escalated" in agent.act_on_diagnosis(_diagnosis(status="escalated"), ask=yes, **QUIET)["outcome"]
    assert executed == []


@_with_temp_action_log
def test_kill_switch_stops_the_loop_before_acting():
    executed = []
    _stub_loop(True, executed)
    actions.KILL_SWITCH_FILE.write_text("stop")
    loop = agent.act_on_diagnosis(_diagnosis(), ask=lambda question: "y", **QUIET)
    assert executed == [] and "KILL_SWITCH" in loop["outcome"]


@_with_temp_action_log
def test_dry_run_changes_nothing():
    executed = []
    _stub_loop(True, executed)
    loop = agent.act_on_diagnosis(_diagnosis(), dry_run=True, **QUIET)
    assert executed == [] and loop["outcome"].startswith("dry run")


@_with_temp_action_log
def test_verified_recovery_and_rollback_on_failure():
    executed = []
    _stub_loop(True, executed)
    ok = agent.act_on_diagnosis(_diagnosis(), ask=lambda question: "y", **QUIET)
    assert ok["outcome"].startswith("recovered and verified")
    assert executed == [("throttle_load", "load-generator", {"user_count": 1})]
    executed.clear()
    _stub_loop(False, executed)
    failed = agent.act_on_diagnosis(_diagnosis(), ask=lambda question: "y", **QUIET)
    # it acted, recovery was not confirmed, so the load generator goes back to its captured 7 users and a human is called
    assert executed == [("throttle_load", "load-generator", {"user_count": 1}),
                        ("throttle_load", "load-generator", {"user_count": 7})]
    assert "rolled back" in failed["outcome"] and failed["rollback"]["ok"]


def test_hallucination_demo_is_rejected_by_the_guard():
    import os
    metric, trace, log = _seed_registry()
    os.environ["DEMO_HALLUCINATION"] = "1"
    try:
        run = _run()
        diagnosis, problem = agent.build_diagnosis(_args([metric, trace, log]), run)
        assert diagnosis is None and "trace-9999" in problem          # planted once: rejected
        diagnosis, problem = agent.build_diagnosis(_args([metric, trace, log]), run)
        assert problem is None and diagnosis["status"] == "diagnosed"  # resubmitted with real refs: accepted
    finally:
        del os.environ["DEMO_HALLUCINATION"]


if __name__ == "__main__":
    for test_name, test in list(globals().items()):
        if test_name.startswith("test_"):
            test()
            print("ok", test_name)
