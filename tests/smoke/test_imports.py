"""
Smoke tests: verify all production apps can be imported in a fresh process.
These tests spawn subprocesses to avoid import-time side effects (e.g., SQLModel
metadata pollution) from leaking between tests.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_MODULES = [
    "aitbc.caching",
    "aitbc.async_tasks",
    "aitbc.security.validators",
    "aitbc.security.audit",
    "aitbc.security.rate_limiter",
    "aitbc.agent_registry.src.discovery",
    "aitbc.agent_registry.src.health",
    "aitbc.agent_registry.src.metadata",
    "aitbc.queues.task",
    "aitbc.queues.scheduler",
    "aitbc.queues.worker",
    "aitbc.queues.decorators",
]

COORDINATOR_MODULES = [
    "app.config",
    "app.auth.jwt_auth",
    "app.auth.dependencies",
    "app.auth.security_matrix",
    "app.core.lifecycle",
    "app.core.middleware",
    "app.storage.db",
]

BLOCKCHAIN_MODULES = [
    "aitbc_chain.main",
    "aitbc_chain.consensus",
    "aitbc_chain.sync",
]

ALL_MODULES = PRODUCTION_MODULES + COORDINATOR_MODULES + BLOCKCHAIN_MODULES


def _can_import(module: str) -> tuple[bool, str]:
    """Try importing a module in a fresh subprocess."""
    code = f"import {module}"
    pp = [
        str(REPO_ROOT),
        str(REPO_ROOT / "apps/coordinator-api/src"),
        str(REPO_ROOT / "apps/blockchain-node/src"),
    ]
    env = {
        "PYTHONPATH": ":".join(pp),
        "DEBUG": "false",
        "APP_ENV": "testing",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=30,
    )
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip()


@pytest.mark.smoke
@pytest.mark.parametrize("module", ALL_MODULES)
def test_module_imports(module: str) -> None:
    """Verify {module} can be imported without errors."""
    success, stderr = _can_import(module)
    if not success:
        pytest.fail(f"Failed to import {module}: {stderr}")
