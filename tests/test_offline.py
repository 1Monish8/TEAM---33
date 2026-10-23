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


if __name__ == "__main__":
    for test_name, test in list(globals().items()):
        if test_name.startswith("test_"):
            test()
            print("ok", test_name)
