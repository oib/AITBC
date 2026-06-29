"""Tests for v0.5.19 tech-debt cleanup.

Covers:
- B1: ReputationDTO + certification refactor (no direct AgentReputation import)
- B2: dead duplicate pricing models removed from marketplace
- B3: unused pricing tables removed; PricingAuditLog wired into dynamic_pricing
- B4: fakeredis fixtures work
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# B1 — ReputationDTO + certification refactor
# ---------------------------------------------------------------------------

COORD_SRC = Path(__file__).resolve().parent.parent.parent / "apps" / "coordinator-api" / "src"
CERT_DIR = COORD_SRC / "app" / "contexts" / "certification" / "services" / "certification"


def test_reputation_dto_is_serialisable_dataclass():
    """ReputationDTO is a frozen dataclass with the expected fields."""
    from dataclasses import fields, is_dataclass

    from aitbc_shared.models import ReputationDTO

    assert is_dataclass(ReputationDTO)
    dto = ReputationDTO(agent_id="agent-1")
    assert dto.agent_id == "agent-1"
    # Defaults match AgentReputation defaults
    assert dto.trust_score == 500.0
    assert dto.reputation_level == "beginner"
    assert dto.success_rate == 0.0
    assert dto.jobs_completed == 0
    field_names = {f.name for f in fields(ReputationDTO)}
    assert {"agent_id", "trust_score", "success_rate", "jobs_completed", "specialization_tags"}.issubset(field_names)


def test_agent_reputation_to_dto_roundtrip():
    """AgentReputation.to_dto() produces an equivalent ReputationDTO."""
    from app.contexts.reputation.domain.reputation import AgentReputation, ReputationLevel
    from aitbc_shared.models import ReputationDTO

    rep = AgentReputation(
        agent_id="agent-xyz",
        trust_score=750.0,
        reputation_level=ReputationLevel.EXPERT,
        performance_rating=4.5,
        reliability_score=88.0,
        success_rate=92.0,
        jobs_completed=42,
        transaction_count=50,
        total_earnings=123.45,
        specialization_tags=["ml", "nlp"],
        certifications=["cert_a"],
    )
    dto = rep.to_dto()
    assert isinstance(dto, ReputationDTO)
    assert dto.agent_id == "agent-xyz"
    assert dto.trust_score == 750.0
    assert dto.reputation_level == "expert"
    assert dto.performance_rating == 4.5
    assert dto.reliability_score == 88.0
    assert dto.success_rate == 92.0
    assert dto.jobs_completed == 42
    assert dto.transaction_count == 50
    assert dto.total_earnings == 123.45
    assert dto.specialization_tags == ["ml", "nlp"]
    assert dto.certifications == ["cert_a"]


@pytest.mark.parametrize(
    "filename",
    ["badge_system.py", "certification_system.py", "partnership_manager.py"],
)
def test_certification_files_do_not_import_agent_reputation(filename: str):
    """No certification service imports the ORM model AgentReputation directly."""
    source = (CERT_DIR / filename).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "AgentReputation", f"{filename} still imports AgentReputation"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "AgentReputation" not in alias.name, f"{filename} still imports AgentReputation"


def test_certification_files_import_reputation_dto():
    """All three certification services import ReputationDTO from the shared package."""
    for filename in ["badge_system.py", "certification_system.py", "partnership_manager.py"]:
        source = (CERT_DIR / filename).read_text()
        tree = ast.parse(source)
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.name)
        assert "ReputationDTO" in imported_names, f"{filename} does not import ReputationDTO"


def test_reputation_service_get_dto_returns_none_for_missing_agent():
    """ReputationService.get_reputation_dto returns None when no profile exists."""
    from unittest.mock import MagicMock

    from app.contexts.reputation.services.reputation_service import ReputationService

    session = MagicMock()
    # Simulate a query that returns no row
    session.execute.return_value.first.return_value = None
    svc = ReputationService(session)
    assert svc.get_reputation_dto("no-such-agent") is None


def test_reputation_service_get_dto_returns_dto_for_existing_agent():
    """ReputationService.get_reputation_dto returns a DTO when a profile exists."""
    from unittest.mock import MagicMock

    from app.contexts.reputation.domain.reputation import AgentReputation, ReputationLevel
    from app.contexts.reputation.services.reputation_service import ReputationService
    from aitbc_shared.models import ReputationDTO

    rep = AgentReputation(
        agent_id="agent-1",
        trust_score=600.0,
        reputation_level=ReputationLevel.ADVANCED,
    )
    session = MagicMock()
    session.execute.return_value.first.return_value = rep
    svc = ReputationService(session)
    dto = svc.get_reputation_dto("agent-1")
    assert isinstance(dto, ReputationDTO)
    assert dto.agent_id == "agent-1"
    assert dto.trust_score == 600.0
    assert dto.reputation_level == "advanced"


# ---------------------------------------------------------------------------
# B2 — dead duplicate pricing models removed from marketplace
# ---------------------------------------------------------------------------

MARKETPLACE_GPU = COORD_SRC / "app" / "contexts" / "marketplace" / "domain" / "gpu_marketplace.py"


def test_marketplace_gpu_no_duplicate_pricing_models():
    """gpu_marketplace.py no longer defines MarketMetrics or PriceForecast (trading is canonical)."""
    source = MARKETPLACE_GPU.read_text()
    tree = ast.parse(source)
    class_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert "MarketMetrics" not in class_names, "MarketMetrics duplicate still present in marketplace"
    assert "PriceForecast" not in class_names, "PriceForecast duplicate still present in marketplace"


# ---------------------------------------------------------------------------
# B3 — unused pricing tables removed; PricingAuditLog wired
# ---------------------------------------------------------------------------

PRICING_MODELS = COORD_SRC / "app" / "contexts" / "trading" / "domain" / "pricing_models.py"


def test_pricing_models_removed_unused_tables():
    """PricingOptimization, PricingAlert, PricingRule are no longer defined."""
    source = PRICING_MODELS.read_text()
    tree = ast.parse(source)
    class_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert "PricingOptimization" not in class_names
    assert "PricingAlert" not in class_names
    assert "PricingRule" not in class_names
    # PricingAuditLog is retained
    assert "PricingAuditLog" in class_names


def test_pricing_models_all_exports_clean():
    """__all__ in pricing_models.py no longer references removed classes."""
    source = PRICING_MODELS.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    names = {elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)}
                    assert "PricingOptimization" not in names
                    assert "PricingAlert" not in names
                    assert "PricingRule" not in names
                    assert "PricingAuditLog" in names
                    return
    pytest.fail("__all__ not found in pricing_models.py")


def test_dynamic_pricing_imports_pricing_audit_log():
    """dynamic_pricing.py imports and uses PricingAuditLog for the audit trail."""
    dp = COORD_SRC / "app" / "contexts" / "trading" / "services" / "trading_marketplace" / "dynamic_pricing.py"
    source = dp.read_text()
    assert "PricingAuditLog" in source
    # The audit log is written in _persist_price_point and _persist_provider_strategy
    assert "PricingAuditLog(" in source


def test_alembic_migration_drops_unused_tables():
    """The drop_unused_pricing_tables migration exists and drops the right tables."""
    migration = COORD_SRC.parent / "alembic" / "versions" / "drop_unused_pricing_tables.py"
    assert migration.exists(), "drop_unused_pricing_tables migration not found"
    source = migration.read_text()
    assert "pricing_optimizations" in source
    assert "pricing_alerts" in source
    assert "pricing_rules" in source
    assert "price_forecast" in source  # singular marketplace leftover


# ---------------------------------------------------------------------------
# B4 — fakeredis fixtures
# ---------------------------------------------------------------------------


def test_fakeredis_sync_fixture(fakeredis_client):
    """The fakeredis_client fixture provides a working sync Redis fake."""
    fakeredis_client.set("v0519", "ok")
    assert fakeredis_client.get("v0519") == "ok"


@pytest.mark.asyncio
async def test_fakeredis_async_fixture(fakeredis_async_client):
    """The fakeredis_async_client fixture provides a working async Redis fake."""
    await fakeredis_async_client.set("v0519_async", "ok")
    assert await fakeredis_async_client.get("v0519_async") == "ok"


def test_fakeredis_isolation_between_tests(fakeredis_client):
    """Each fakeredis_client instance starts empty (no leakage between tests)."""
    assert fakeredis_client.get("v0519") is None  # set by the other test, but isolated
