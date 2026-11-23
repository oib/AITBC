"""Unit tests for the shadow-mode spot-check service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coordinator_api.contexts.infrastructure.domain import Job
from coordinator_api.contexts.infrastructure.services.spot_check import SpotCheckService


def _make_job(session, *, deterministic: bool = True) -> Job:
    job = Job(
        client_id="client-1",
        state="COMPLETED",
        payload={"type": "inference", "prompt": "hello", "model": "llama3.2:3b"},
        constraints={"deterministic_decoding": deterministic} if deterministic else {},
        ttl_seconds=900,
        requested_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(seconds=900),
        result={"result": {"status": "completed", "output": "world"}},
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def test_spot_check_scheduled_for_deterministic_job(db_session):
    original = _make_job(db_session)
    svc = SpotCheckService(db_session)
    shadow = svc.schedule_if_eligible(original)
    assert shadow is not None
    assert shadow.constraints["shadow_mode"] is True
    assert shadow.constraints["spot_check_for"] == original.id
    assert shadow.constraints["deterministic_decoding"] is True
    assert shadow.payment_id is None


def test_spot_check_not_scheduled_for_non_deterministic_job(db_session):
    original = _make_job(db_session, deterministic=False)
    svc = SpotCheckService(db_session)
    assert svc.schedule_if_eligible(original) is None


def test_spot_check_not_scheduled_for_shadow_job(db_session):
    original = _make_job(db_session)
    svc = SpotCheckService(db_session)
    shadow = svc.schedule_if_eligible(original)
    assert svc.schedule_if_eligible(shadow) is None


def test_spot_check_match(db_session):
    original = _make_job(db_session)
    svc = SpotCheckService(db_session)
    shadow = svc.schedule_if_eligible(original)
    # Simulate completion of the shadow job with the exact same output.
    shadow.result = {"result": {"status": "completed", "output": "world"}}
    shadow.state = "COMPLETED"
    record = svc.complete_spot_check(shadow)
    assert record["match"] is True


def test_spot_check_mismatch(db_session):
    original = _make_job(db_session)
    svc = SpotCheckService(db_session)
    shadow = svc.schedule_if_eligible(original)
    shadow.result = {"result": {"status": "completed", "output": "different"}}
    shadow.state = "COMPLETED"
    record = svc.complete_spot_check(shadow)
    assert record["match"] is False


def test_spot_check_flat_result_shape(db_session):
    """submit_result stores job.result flat ({status, output}); the check
    must read that shape, not only the nested fixture form (#2690)."""
    original = _make_job(db_session)
    original.result = {"status": "completed", "output": "world", "latency_ms": 12}
    db_session.add(original)
    db_session.commit()

    svc = SpotCheckService(db_session)
    shadow = svc.schedule_if_eligible(original)
    shadow.result = {"status": "completed", "output": "world"}
    shadow.state = "COMPLETED"
    record = svc.complete_spot_check(shadow)
    assert record["match"] is True

    shadow2 = svc.schedule_if_eligible(original)
    shadow2.result = {"status": "completed", "output": "tampered"}
    shadow2.state = "COMPLETED"
    record2 = svc.complete_spot_check(shadow2)
    assert record2["match"] is False


def test_spot_check_empty_output_fails_closed(db_session):
    """Missing output on either side must not report a match (#2690)."""
    original = _make_job(db_session)
    original.result = {"status": "completed"}  # no output key at all
    db_session.add(original)
    db_session.commit()

    svc = SpotCheckService(db_session)
    shadow = svc.schedule_if_eligible(original)
    shadow.result = {"status": "completed"}
    shadow.state = "COMPLETED"
    record = svc.complete_spot_check(shadow)
    assert record["match"] is False
