"""DEPLOY-VALIDATOR-SCOPE-DROP-1 — a differing signing key is never dropped.

ensure_validator_secrets_scope moved PROPOSER_KEY/VALIDATOR_KEYS out of the
shared env files into root-only validator-secrets.env. When the key already
existed there it deleted the source line unconditionally — so a *different*
value (the live key after a rotation) was destroyed silently. Differing
values now warn and keep both copies; identical duplicates are still dropped.
The function's `umask 077` also leaked into the rest of the update — it is
now scoped to the subshell doing the write.

Tests drive the real function with scratch env files via AITBC_SECRETS_ENV /
AITBC_VALIDATOR_SECRETS_ENV overrides.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "deployment" / "update.sh"


def _scope(tmp_path: Path, secrets: str, validator: str) -> subprocess.CompletedProcess[str]:
    secrets_env = tmp_path / "blockchain-secrets.env"
    validator_env = tmp_path / "validator-secrets.env"
    node_env = tmp_path / "node.env"
    blockchain_env = tmp_path / "blockchain.env"
    secrets_env.write_text(secrets)
    if validator:
        validator_env.write_text(validator)
    node_env.write_text("")
    blockchain_env.write_text("")

    script = f"""
        source {UPDATE_SH}
        AITBC_SECRETS_ENV={secrets_env}
        AITBC_VALIDATOR_SECRETS_ENV={validator_env}
        BLOCKCHAIN_ENV_FILE={blockchain_env}
        NODE_ENV_FILE={node_env}
        umask 022
        ensure_validator_secrets_scope
        rc=$?
        echo "UMASK_AFTER=$(umask)"
        exit $rc
    """
    env = {**os.environ, "AITBC_ROOT": str(REPO_ROOT)}
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)


def test_differing_key_is_never_dropped(tmp_path):
    result = _scope(
        tmp_path,
        "PROPOSER_KEY=0xLIVE\nVALIDATOR_KEYS=vk1\n",
        "PROPOSER_KEY=0xSTALE\nVALIDATOR_KEYS=vk1\n",
    )
    assert result.returncode == 0, result.stderr

    secrets = (tmp_path / "blockchain-secrets.env").read_text()
    # The differing PROPOSER_KEY survives; the identical VALIDATOR_KEYS is deduped.
    assert "0xLIVE" in secrets
    assert "VALIDATOR_KEYS" not in secrets
    assert "DIFFERS" in result.stderr

    validator = (tmp_path / "validator-secrets.env").read_text()
    assert "0xSTALE" in validator
    assert "0xLIVE" not in validator


def test_key_moves_when_validator_file_lacks_it(tmp_path):
    result = _scope(tmp_path, "PROPOSER_KEY=0xNEW\n", "")
    assert result.returncode == 0, result.stderr

    assert "PROPOSER_KEY" not in (tmp_path / "blockchain-secrets.env").read_text()
    assert "PROPOSER_KEY=0xNEW" in (tmp_path / "validator-secrets.env").read_text()


def test_umask_is_restored_after_the_function(tmp_path):
    result = _scope(tmp_path, "PROPOSER_KEY=0xNEW\n", "")
    assert result.returncode == 0, result.stderr
    assert "UMASK_AFTER=0022" in result.stdout
