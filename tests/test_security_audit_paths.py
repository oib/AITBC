"""Tests for the repo paths scripts/security/security_audit.py scores.

The audit looks at hard-coded repo-relative paths. When the coordinator package was
renamed from ``app`` to ``coordinator_api`` those paths went stale, and
``check_access_control`` kept reporting a critical ``no_authentication_mechanism``
for a service that has an auth package.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "security" / "security_audit.py"
PATH_ROOTS = ("apps/", "scripts/", "packages/", "contracts/", "cli/", "aitbc/", "tests/", "docs/")

COORDINATOR_AUTH = "apps/coordinator-api/src/coordinator_api/auth/__init__.py"
COORDINATOR_CONFIG = "apps/coordinator-api/src/coordinator_api/config.py"


def _repo_path_literals() -> list[str]:
    """Repo-relative path literals in the audit script (globs and absolute paths excluded)."""
    tree = ast.parse(SCRIPT.read_text())
    return sorted(
        {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith(PATH_ROOTS)
            and "*" not in node.value
        }
    )


def _touch(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture(scope="module")
def audit_module():
    spec = importlib.util.spec_from_file_location("security_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["security_audit"] = module
    spec.loader.exec_module(module)
    return module


class TestNamedPathsExist:
    def test_scan_finds_the_paths(self):
        # Guards the parametrized check below against matching nothing.
        literals = _repo_path_literals()
        assert "apps/blockchain-node/src/aitbc_chain/config.py" in literals
        assert COORDINATOR_CONFIG in literals

    @pytest.mark.parametrize("rel", _repo_path_literals())
    def test_every_repo_path_the_audit_names_exists(self, rel):
        assert (REPO_ROOT / rel).exists(), f"security_audit.py scores {rel}, which does not exist"


class TestAccessControl:
    def test_coordinator_auth_package_counts_as_authentication(self, audit_module, tmp_path):
        _touch(tmp_path, COORDINATOR_AUTH, "# role permission authorization\n")
        score, issues = audit_module.SecurityAudit(str(tmp_path)).check_access_control()
        assert issues == []
        assert score == 10

    def test_tree_without_an_auth_package_is_still_flagged(self, audit_module, tmp_path):
        _touch(tmp_path, "apps/other/app.py", "# role permission authorization\n")
        score, issues = audit_module.SecurityAudit(str(tmp_path)).check_access_control()
        assert [i["type"] for i in issues] == ["no_authentication_mechanism"]
        assert issues[0]["severity"] == "critical"
        assert score == 5


class TestNetworkSecurity:
    def test_ssl_in_the_coordinator_config_is_seen(self, audit_module, tmp_path):
        _touch(tmp_path, COORDINATOR_CONFIG, "SSL_CERT_FILE = ''\n")
        _score, issues = audit_module.SecurityAudit(str(tmp_path)).check_network_security()
        assert "no_ssl_configuration" not in [i["type"] for i in issues]

    def test_coordinator_config_without_ssl_is_flagged(self, audit_module, tmp_path):
        _touch(tmp_path, COORDINATOR_CONFIG, "DEBUG = False\n")
        _score, issues = audit_module.SecurityAudit(str(tmp_path)).check_network_security()
        assert "no_ssl_configuration" in [i["type"] for i in issues]
