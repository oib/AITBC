"""Unit tests for v0.15.2 Agent B financial regulatory compliance module."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_module(module_path: str, package_dir: Path) -> ModuleType:
    """Import a module by adding ``package_dir`` to ``sys.path``."""
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))
    return __import__(module_path, fromlist=["__name__"])


def _finance_module() -> ModuleType:
    return _import_module(
        "coordinator_api.contexts.compliance.finance",
        REPO_ROOT / "apps/coordinator-api/src",
    )


def test_glba_policy_applies_to_pii() -> None:
    from aitbc.compliance.policies import ComplianceFramework, load_policy_template

    policy = load_policy_template(ComplianceFramework.GLBA)
    assert policy.framework == ComplianceFramework.GLBA
    assert policy.require_control("GLBA-1")
