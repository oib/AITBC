"""Unit tests for aitbc_shared.models.reputation.ReputationDTO (v0.5.19 §A2).

The DTO is a read-only cross-context projection of `AgentReputation`.
These tests verify:
- default field values match `AgentReputation` defaults
- explicit construction with all fields
- frozen/immutability contract
- list defaults are not shared across instances
- the field set is a superset of every attribute the certification
  context reads (guards against drift if `AgentReputation` adds a field
  that certification starts using without updating the DTO).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from aitbc_shared import ReputationDTO


def test_defaults_match_agent_reputation() -> None:
    """A freshly-created DTO mirrors AgentReputation's documented defaults."""
    dto = ReputationDTO(agent_id="agent-1")
    assert dto.agent_id == "agent-1"
    assert dto.trust_score == 500.0
    assert dto.reputation_level == "beginner"
    assert dto.performance_rating == 3.0
    assert dto.reliability_score == 50.0
    assert dto.community_rating == 3.0
    assert dto.total_earnings == 0.0
    assert dto.transaction_count == 0
    assert dto.success_rate == 0.0
    assert dto.dispute_count == 0
    assert dto.dispute_won_count == 0
    assert dto.jobs_completed == 0
    assert dto.jobs_failed == 0
    assert dto.average_response_time == 0.0
    assert dto.uptime_percentage == 0.0
    assert dto.community_contributions == 0
    assert dto.geographic_region == ""
    assert dto.service_categories == []
    assert dto.specialization_tags == []
    assert dto.certifications == []
    assert dto.created_at is None
    assert dto.updated_at is None
    assert dto.last_activity is None


def test_explicit_construction() -> None:
    """Every field can be supplied explicitly."""
    now = datetime.now(UTC)
    dto = ReputationDTO(
        agent_id="agent-2",
        trust_score=900.0,
        reputation_level="expert",
        performance_rating=4.8,
        reliability_score=98.0,
        community_rating=4.5,
        total_earnings=12_345.6,
        transaction_count=42,
        success_rate=95.0,
        dispute_count=2,
        dispute_won_count=1,
        jobs_completed=40,
        jobs_failed=2,
        average_response_time=120.5,
        uptime_percentage=99.9,
        community_contributions=7,
        geographic_region="us-east",
        service_categories=["compute", "storage"],
        specialization_tags=["gpu", "inference"],
        certifications=["iso-27001"],
        created_at=now,
        updated_at=now,
        last_activity=now,
    )
    assert dto.agent_id == "agent-2"
    assert dto.trust_score == 900.0
    assert dto.reputation_level == "expert"
    assert dto.performance_rating == 4.8
    assert dto.reliability_score == 98.0
    assert dto.community_rating == 4.5
    assert dto.total_earnings == 12_345.6
    assert dto.transaction_count == 42
    assert dto.success_rate == 95.0
    assert dto.dispute_count == 2
    assert dto.dispute_won_count == 1
    assert dto.jobs_completed == 40
    assert dto.jobs_failed == 2
    assert dto.average_response_time == 120.5
    assert dto.uptime_percentage == 99.9
    assert dto.community_contributions == 7
    assert dto.geographic_region == "us-east"
    assert dto.service_categories == ["compute", "storage"]
    assert dto.specialization_tags == ["gpu", "inference"]
    assert dto.certifications == ["iso-27001"]
    assert dto.created_at == now
    assert dto.updated_at == now
    assert dto.last_activity == now


def test_is_frozen() -> None:
    """DTO is immutable — assignment must raise FrozenInstanceError."""
    dto = ReputationDTO(agent_id="agent-3")
    with pytest.raises(dataclasses.FrozenInstanceError):
        dto.trust_score = 100.0  # type: ignore[misc]


def test_list_defaults_not_shared() -> None:
    """default_factory lists must be independent per instance."""
    a = ReputationDTO(agent_id="a")
    b = ReputationDTO(agent_id="b")
    a.specialization_tags.append("x")
    a.service_categories.append("y")
    a.certifications.append("z")
    assert b.specialization_tags == []
    assert b.service_categories == []
    assert b.certifications == []


def test_equality_is_structural() -> None:
    """Frozen dataclass equality is structural — same field values are equal."""
    a = ReputationDTO(agent_id="agent-4")
    b = ReputationDTO(agent_id="agent-4")
    assert a == b
    assert a != ReputationDTO(agent_id="agent-5")
    # list fields participate in equality
    assert a != ReputationDTO(agent_id="agent-4", specialization_tags=["x"])


def test_not_hashable_due_to_list_fields() -> None:
    """The DTO carries list fields, so it is intentionally not hashable.

    A frozen dataclass is only hashable when all its fields are hashable;
    `list` is not. This is acceptable for a DTO that is passed by value
    rather than used as a dict key. Confirm the contract so a future
    change to hashable field types is a conscious decision.
    """
    dto = ReputationDTO(agent_id="agent-4")
    with pytest.raises(TypeError, match="unhashable"):
        hash(dto)


def test_field_set_covers_certification_reads() -> None:
    """Guard: every attribute the certification context reads must exist on the DTO.

    This is the regression guard called out in the v0.5.19 plan — if a
    future change to certification starts reading a new AgentReputation
    field, this test forces the DTO to be updated too.
    """
    # Attributes accessed via `reputation.<attr>` in the three certification
    # service files (badge_system.py, certification_system.py,
    # partnership_manager.py) as of v0.5.19.
    certification_read_attrs = {
        "agent_id",
        "trust_score",
        "specialization_tags",
        "reliability_score",
        "success_rate",
        "performance_rating",
        "average_response_time",
        "total_earnings",
        "transaction_count",
        "geographic_region",
        "created_at",
        "jobs_completed",
        "dispute_count",
        "community_contributions",
        "certifications",
    }
    dto_fields = {f.name for f in dataclasses.fields(ReputationDTO)}
    missing = certification_read_attrs - dto_fields
    assert not missing, f"ReputationDTO is missing fields read by certification: {missing}"
