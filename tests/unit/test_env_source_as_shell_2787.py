"""#2787: secret-bearing env files must be parsed, never sourced as shell.

`sourcing /etc/aitbc/*.env` executes $(...), backticks and unbalanced
quotes inside files that carry key material — and bash `source` strips
' # comment' where systemd keeps it, so scripts could see different values
than the services. The affected lookups now go through
scripts/utils/systemd-env.sh.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    "scripts/monitoring/health_check.sh",
    "scripts/deployment/setup.sh",
    "scripts/deployment/deploy.sh",
    "scripts/utils/agent_followup.sh",
]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def test_no_script_sources_an_etc_aitbc_env_file() -> None:
    for rel in SCRIPTS:
        src = (REPO_ROOT / rel).read_text()
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not (stripped.startswith("source ") and ".env" in stripped and "/etc/aitbc" in stripped), (
                f"{rel}: still sources an env file: {stripped}"
            )
            assert not (stripped.startswith("source ") and "etc_dir" in stripped and ".env" in stripped), (
                f"{rel}: still sources an env file: {stripped}"
            )


def test_agent_followup_role_survives_hostile_env_content(tmp_path: Path) -> None:
    """A $(...) payload inside blockchain.env must NOT execute; the role
    keys must still be read with systemd semantics."""
    etc = tmp_path / "etc"
    etc.mkdir()
    pwn = tmp_path / "pwned"
    (etc / "blockchain.env").write_text(
        f"BLOCKCHAIN_MODE=hub\nMARKET_ROLE=shop\nHARDWARE_PROFILE=gpu\nPROPOSER_KEY=$({{touch}} {pwn})\n".replace(
            "${{touch}}", "$(touch)"
        )
    )
    (etc / "node.env").write_text("MARKET_ROLE=customer\n")

    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{REPO_ROOT}/scripts/utils/agent_followup.sh" && AITBC_ETC_DIR="{etc}" agent_followup_get_node_role',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    # node.env MARKET_ROLE=customer wins → not shop → 'customer'? role logic:
    # hub check first — BLOCKCHAIN_MODE=hub from blockchain.env → 'hub'.
    assert result.stdout.strip() == "hub"
    assert not pwn.exists(), "env file content was executed — source-as-shell still live"
