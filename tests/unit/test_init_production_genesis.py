"""#943: init_production_genesis pins.

The legacy seeder imported ``aitbc_chain.database`` at module top, which
builds the ``settings`` singleton from ambient env *before* ``main()`` set
``CHAIN_ID``/``DB_PATH`` — so the flag values never reached the settings
the script then used. It also silently returned an existing head instead
of refusing to overwrite. Pins: env is set before the aitbc_chain import,
block 0 goes through ``aitbc_chain.genesis_builder``, and a second run on
an already-seeded scratch chain refuses.
"""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "utils" / "init_production_genesis.py"
VENV_PY = Path("/opt/aitbc/venv/bin/python")


def _scratch_env(tmp_path: Path) -> dict:
    scratch = tmp_path / "scratch"
    env = dict(os.environ)
    env.pop("CHAIN_ID", None)
    env.pop("DB_PATH", None)
    env["AITBC_RESET_SCRATCH"] = str(scratch)
    env["AITBC_DATA_DIR"] = str(scratch / "data")
    env["PYTHONPATH"] = os.pathsep.join([str(REPO), str(REPO / "apps" / "blockchain-node" / "src"), env.get("PYTHONPATH", "")])
    return env


def _run(env: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    db_path = Path(env["AITBC_RESET_SCRATCH"]) / "data" / "refusal-test" / "chain.db"
    return subprocess.run(
        [
            str(VENV_PY),
            str(SCRIPT),
            "--chain-id",
            "refusal-test",
            "--db-path",
            str(db_path),
            "--allow-derived-keys",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
    )


def test_env_is_set_before_aitbc_chain_import():
    """main() must set CHAIN_ID/DB_PATH before aitbc_chain builds settings."""
    src = SCRIPT.read_text()
    body = src.split("def main", 1)[1]
    env_set = body.index('os.environ["CHAIN_ID"]')
    db_import = body.index("from aitbc_chain.database import")
    assert env_set < db_import, "aitbc_chain.database is imported before CHAIN_ID is set"


def test_genesis_block_goes_through_genesis_builder():
    src = SCRIPT.read_text()
    assert "genesis_builder" in src, "block 0 no longer built via aitbc_chain.genesis_builder"


def test_seeds_scratch_chain_then_refuses_overwrite(tmp_path):
    env = _scratch_env(tmp_path)
    first = _run(env, tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr

    second = _run(env, tmp_path)
    assert second.returncode != 0, "re-run on a seeded chain must refuse"
    out = (second.stdout + second.stderr).lower()
    assert "already" in out or "refus" in out
