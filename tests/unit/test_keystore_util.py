"""UTILS-KEYSTORE-PY-KEY-NOT-DERIVED-FROM-ADDRESS-1 — the keystore must belong to the key.

scripts/utils/keystore.py used to encrypt a fresh ``secrets.token_hex(32)``
under whatever address was passed on the CLI, leak the key to stdout, write
the file before chmod 600, and stamp ``created_at`` as ``isoformat()+'Z'``
(``+00:00Z`` — an offset *and* a Z). The fix takes the private key as input,
derives the address from it (eth_account), writes the file O_EXCL 0600, and
prints no key material.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from eth_account import Account

REPO_ROOT = Path(__file__).resolve().parents[2]
KEYSTORE_PY = REPO_ROOT / "scripts" / "utils" / "keystore.py"

PRIVATE_KEY = "0x" + "ab" * 32
EXPECTED_ADDRESS = Account.from_key(PRIVATE_KEY).address


def _load_module():
    spec = importlib.util.spec_from_file_location("aitbc_keystore_util", KEYSTORE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_keystore_address_is_derived_from_the_private_key(tmp_path):
    mod = _load_module()

    out = mod.create_keystore(PRIVATE_KEY, "pw", keystore_dir=tmp_path)

    keystore = json.loads(out.read_text())
    assert keystore["address"] == EXPECTED_ADDRESS
    assert out.name == f"{EXPECTED_ADDRESS}.json"


def test_keystore_file_is_mode_600_and_refuses_to_clobber(tmp_path):
    mod = _load_module()

    out = mod.create_keystore(PRIVATE_KEY, "pw", keystore_dir=tmp_path)

    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        mod.create_keystore(PRIVATE_KEY, "pw", keystore_dir=tmp_path)


def test_created_at_is_a_single_iso_offset_not_iso_plus_z(tmp_path):
    mod = _load_module()

    out = mod.create_keystore(PRIVATE_KEY, "pw", keystore_dir=tmp_path)

    created_at = json.loads(out.read_text())["created_at"]
    assert not created_at.endswith("+00:00Z")
    assert datetime.fromisoformat(created_at).tzinfo is not None


def test_main_takes_the_key_and_never_prints_it(tmp_path, capsys):
    mod = _load_module()

    argv = [
        "keystore.py",
        "--private-key",
        PRIVATE_KEY,
        "--password",
        "pw",
        "--output-dir",
        str(tmp_path),
    ]
    old_argv = sys.argv
    try:
        sys.argv = argv
        mod.main()
    finally:
        sys.argv = old_argv

    out = capsys.readouterr().out
    assert PRIVATE_KEY not in out
    assert "ab" * 32 not in out
    assert (tmp_path / f"{EXPECTED_ADDRESS}.json").exists()


def test_main_without_a_private_key_exits(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("PRIVATE_KEY", "AITBC_PRIVATE_KEY")}
    result = subprocess.run(
        [sys.executable, str(KEYSTORE_PY), "--password", "pw", "--output-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert not list(tmp_path.iterdir())
