"""Unit tests for v0.15.1 Agent B HIPAA compliance module."""

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


def _hipaa_module() -> ModuleType:
    return _import_module(
        "coordinator_api.contexts.compliance.hipaa",
        REPO_ROOT / "apps/coordinator-api/src",
    )


def test_hipaa_example_policy_loaded() -> None:
    from aitbc.compliance.policies import ComplianceFramework, load_policy_template

    policy = load_policy_template(ComplianceFramework.HIPAA)
    assert policy.framework == ComplianceFramework.HIPAA
    assert policy.require_control("HIPAA-3")
