"""Tests for v0.5.19 tech-debt cleanup.

Covers:
- B1: ReputationDTO + certification refactor (no direct AgentReputation import)
- B2: dead duplicate pricing models removed from marketplace
- B3: unused pricing tables removed; PricingAuditLog wired into dynamic_pricing
- B4: fakeredis fixtures work
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# B1 — ReputationDTO + certification refactor
# ---------------------------------------------------------------------------

COORD_SRC = Path(__file__).resolve().parent.parent.parent / "apps" / "coordinator-api" / "src"
CERT_DIR = COORD_SRC / "coordinator_api" / "contexts" / "certification" / "services" / "certification"

REPO_ROOT = COORD_SRC.parent.parent.parent
COORD_ALEMBIC = REPO_ROOT / "apps" / "coordinator-api"
ALEMBIC_BIN = Path(sys.executable).with_name("alembic")


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


# ---------------------------------------------------------------------------
# B2 — dead duplicate pricing models removed from marketplace
# ---------------------------------------------------------------------------

MARKETPLACE_GPU = COORD_SRC / "coordinator_api" / "contexts" / "marketplace" / "domain" / "gpu_marketplace.py"


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

PRICING_MODELS = COORD_SRC / "coordinator_api" / "contexts" / "trading" / "domain" / "pricing_models.py"


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
    dp = COORD_SRC / "coordinator_api" / "contexts" / "trading" / "services" / "trading_marketplace" / "dynamic_pricing.py"
    source = dp.read_text()
    assert "PricingAuditLog" in source
    # The audit log is written in _persist_price_point and _persist_provider_strategy
    assert "PricingAuditLog(" in source


# ---------------------------------------------------------------------------
# B4 — fakeredis fixtures
# ---------------------------------------------------------------------------


def test_fakeredis_sync_fixture(fakeredis_client):
    """The fakeredis_client fixture provides a working sync Redis fake."""
    fakeredis_client.set("v0519", "ok")
    assert fakeredis_client.get("v0519") == "ok"


def test_fakeredis_isolation_between_tests(fakeredis_client):
    """Each fakeredis_client instance starts empty (no leakage between tests)."""
    assert fakeredis_client.get("v0519") is None  # set by the other test, but isolated
