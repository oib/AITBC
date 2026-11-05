"""#1161: sync_cli must load chain env files (e.g. blockchain-island.env's
VALIDATOR_SET) via --env-file before aitbc_chain.config snapshots its env
file list at import time.
"""

import os
import subprocess
import sys

import pytest

from aitbc_chain.sync_cli import _apply_env_files


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AITBC_CHAIN_ENV_FILE", raising=False)
    yield
    monkeypatch.delenv("AITBC_CHAIN_ENV_FILE", raising=False)


def test_env_files_append_after_default(monkeypatch):
    _apply_env_files(["/etc/aitbc/blockchain-island.env", "/etc/aitbc/node-island.env"])
    assert os.environ["AITBC_CHAIN_ENV_FILE"] == (
        "/etc/aitbc/blockchain.env,/etc/aitbc/blockchain-island.env,/etc/aitbc/node-island.env"
    )


def test_existing_env_file_var_is_preserved_and_extended(monkeypatch):
    monkeypatch.setenv("AITBC_CHAIN_ENV_FILE", "/custom/base.env")
    _apply_env_files(["/etc/aitbc/blockchain-island.env"])
    assert os.environ["AITBC_CHAIN_ENV_FILE"] == "/custom/base.env,/etc/aitbc/blockchain-island.env"


def test_no_env_files_leaves_var_unset(monkeypatch):
    _apply_env_files([])
    assert "AITBC_CHAIN_ENV_FILE" not in os.environ


def test_empty_string_existing_var_is_treated_as_no_files(monkeypatch):
    # AITBC_CHAIN_ENV_FILE="" means "load no env file" per config.py — the
    # --env-file paths must still apply, and the implicit default must not
    # sneak back in.
    monkeypatch.setenv("AITBC_CHAIN_ENV_FILE", "")
    _apply_env_files(["/etc/aitbc/blockchain-island.env"])
    assert os.environ["AITBC_CHAIN_ENV_FILE"] == "/etc/aitbc/blockchain-island.env"


def test_sync_cli_import_does_not_pull_config():
    """The lazy-import invariant: importing sync_cli must not import
    aitbc_chain.config, or --env-file could never take effect."""
    code = "import sys; import aitbc_chain.sync_cli; sys.exit(0 if 'aitbc_chain.config' not in sys.modules else 1)"
    env = dict(os.environ)
    env.pop("AITBC_CHAIN_ENV_FILE", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, result.stderr
