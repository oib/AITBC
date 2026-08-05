"""Unit tests for v0.15.1 §A3 audit log and retention helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aitbc.compliance import (
    AuditLog,
    AuditOutcome,
    DataClassification,
    RetentionAction,
    RetentionEngine,
    RetentionPolicy,
    RetentionSchedule,
    apply_retention,
    build_audit_event,
    verify_audit_log,
)


def test_audit_log_chain_verifies() -> None:
    log = AuditLog(log_id="log-1")
    event = build_audit_event(
        event_id="ev-1",
        actor="agent-a",
        resource="blob-1",
        action="read",
        classification="phi",
        outcome="allowed",
        policy_id="hipaa-v1",
    )
    log.append(event)
    assert log.verify() is True
    assert verify_audit_log(log) is True


def test_audit_log_detects_tampering() -> None:
    log = AuditLog(log_id="log-1")
    event = build_audit_event(
        event_id="ev-1",
        actor="agent-a",
        resource="blob-1",
        action="read",
        classification="phi",
        outcome="allowed",
        policy_id="hipaa-v1",
    )
    log.append(event)
    log.events[0].outcome = AuditOutcome.DENIED
    assert log.verify() is False


def test_audit_log_chain_links_events() -> None:
    log = AuditLog(log_id="log-1")
    first = build_audit_event(
        event_id="ev-1",
        actor="agent-a",
        resource="blob-1",
        action="read",
        classification="phi",
        outcome="allowed",
    )
    second = build_audit_event(
        event_id="ev-2",
        actor="agent-b",
        resource="blob-2",
        action="delete",
        classification="pii",
        outcome="denied",
    )
    first_hash = log.append(first)
    second_hash = log.append(second)
    assert first_hash != second_hash
    assert log.verify() is True


def test_retention_engine_evaluates_expired() -> None:
    schedule = RetentionSchedule(
        rules={
            DataClassification.PII: RetentionPolicy(
                classification="pii",
                duration_days=30,
                action=RetentionAction.DELETE,
            ),
        },
        default_action=RetentionAction.REVIEW,
    )
    engine = RetentionEngine(schedule)
    created = datetime.now(UTC) - timedelta(days=40)
    action = engine.evaluate("pii", created)
    assert action == RetentionAction.DELETE


def test_retention_engine_default_action_for_unknown() -> None:
    schedule = RetentionSchedule(rules={})
    engine = RetentionEngine(schedule)
    created = datetime.now(UTC) - timedelta(days=100)
    action = engine.evaluate("public", created)
    assert action == RetentionAction.REVIEW


def test_apply_retention_not_expired() -> None:
    policy = RetentionPolicy(
        classification="pii",
        duration_days=30,
        action=RetentionAction.DELETE,
    )
    created = datetime.now(UTC) - timedelta(days=5)
    assert apply_retention(policy, created) == RetentionAction.ARCHIVE


def test_apply_retention_expired() -> None:
    policy = RetentionPolicy(
        classification="pii",
        duration_days=30,
        action=RetentionAction.DELETE,
    )
    created = datetime.now(UTC) - timedelta(days=31)
    assert apply_retention(policy, created) == RetentionAction.DELETE


def test_batch_evaluate() -> None:
    schedule = RetentionSchedule(
        rules={
            DataClassification.PHI: RetentionPolicy(
                classification="phi",
                duration_days=90,
                action=RetentionAction.ARCHIVE,
            ),
        },
    )
    engine = RetentionEngine(schedule)
    now = datetime.now(UTC)
    records = [
        ("r1", now - timedelta(days=100), DataClassification.PHI),
        ("r2", now - timedelta(days=5), DataClassification.PHI),
    ]
    results = engine.batch_evaluate(records, now=now)
    assert results["r1"] == RetentionAction.ARCHIVE
    assert results["r2"] == RetentionAction.REVIEW
