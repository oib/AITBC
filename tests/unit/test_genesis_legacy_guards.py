"""#859/#860/#861: the legacy genesis tools carry the #290 hard stop.

Every script refuses outside a declared AITBC_RESET_SCRATCH root (and a
live chain id) before it writes. The refusal test runs each script with
AITBC_DATA_DIR pointed at a scratch dir but WITHOUT the scratch marker —
on base the script proceeded to scratch writes (or worse, the live
defaults); now it must exit non-zero with a refusal. Scratch-only envs
throughout — no real /var or /etc path is touched.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VENV_PY = Path("/opt/aitbc/venv/bin/python")

GUARDED = [
    "scripts/utils/init_production_genesis.py",
    "scripts/utils/genesis-init.py",
    "apps/blockchain-node/create_genesis.py",
    "apps/blockchain-node/init_genesis.py",
    "apps/blockchain-node/scripts/create_genesis_wallet.py",
]


def test_each_legacy_script_calls_the_reset_guard():
    for rel in GUARDED:
        src = (REPO / rel).read_text()
        assert "reset_guard" in src, f"{rel} lost its #290 guard"


def _env_for(tmp_path):
    env = dict(os.environ)
    env.pop("AITBC_RESET_SCRATCH", None)
    env["AITBC_DATA_DIR"] = str(tmp_path / "data")
    env["PYTHONPATH"] = os.pathsep.join([str(REPO), str(REPO / "apps" / "blockchain-node" / "src"), env.get("PYTHONPATH", "")])
    return env


@pytest.mark.parametrize(
    "rel,args",
    [
        ("scripts/utils/init_production_genesis.py", ["--chain-id", "refusal-test"]),
        ("scripts/utils/genesis-init.py", ["--chain-id", "refusal-test", "--proposer", "0x" + "ab" * 20]),
        ("apps/blockchain-node/create_genesis.py", []),
        ("apps/blockchain-node/init_genesis.py", []),
        ("apps/blockchain-node/scripts/create_genesis_wallet.py", []),
    ],
    ids=lambda v: Path(v if isinstance(v, str) else "x").stem,
)
def test_refuses_without_scratch_marker(tmp_path, rel, args):
    """Unmarked run must refuse non-zero — and write nothing."""
    result = subprocess.run(
        [str(VENV_PY), str(REPO / rel), *args],
        env=_env_for(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert "refused" in (result.stdout + result.stderr).lower() or "AITBC_RESET_SCRATCH" in (result.stdout + result.stderr)


def test_wallet_writes_o_excl_0600_and_refuses_overwrite(tmp_path):
    """#860: with a scratch root + KEYSTORE_DIR, the first write succeeds at
    mode 0600 and a second run refuses instead of overwriting."""
    env = _env_for(tmp_path)
    scratch = tmp_path / "scratch"
    env["AITBC_RESET_SCRATCH"] = str(scratch)
    env["KEYSTORE_DIR"] = str(scratch / "keystore")
    script = REPO / "apps/blockchain-node/scripts/create_genesis_wallet.py"

    first = subprocess.run([str(VENV_PY), str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stdout + first.stderr
    ks = scratch / "keystore" / "genesis.json"
    pw = scratch / "keystore" / ".genesis_password"
    assert ks.is_file() and pw.is_file()
    assert (ks.stat().st_mode & 0o777) == 0o600
    assert (pw.stat().st_mode & 0o777) == 0o600

    second = subprocess.run([str(VENV_PY), str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert second.returncode != 0
    assert "refused" in (second.stdout + second.stderr).lower()
