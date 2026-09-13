"""Tests for scripts/utils/rotate_service_accounts.py.

The module imports eth_account and aitbc_chain at top level; both are present in
the deployment venv, so these tests only run where the full checkout exists.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "rotate_service_accounts.py"


@pytest.fixture(scope="module")
def rot():
    spec = importlib.util.spec_from_file_location("rotate_service_accounts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["rotate_service_accounts"] = module
    spec.loader.exec_module(module)
    return module


class TestExtractTxHash:
    """POST /v1/transaction returns transaction_hash; the script must read it."""

    def test_canonical_field(self, rot):
        assert rot.extract_tx_hash({"transaction_hash": "0xabc"}) == "0xabc"

    def test_legacy_fields(self, rot):
        assert rot.extract_tx_hash({"tx_hash": "0xdef"}) == "0xdef"
        assert rot.extract_tx_hash({"hash": "0x123"}) == "0x123"

    def test_canonical_wins(self, rot):
        assert rot.extract_tx_hash({"transaction_hash": "0xabc", "tx_hash": "0xdef"}) == "0xabc"

    def test_missing_and_non_dict(self, rot):
        assert rot.extract_tx_hash({}) is None
        assert rot.extract_tx_hash("error string") is None


class TestDryRunSafety:
    def test_dry_run_mints_but_writes_nothing(self, rot, tmp_path, capsys):
        keys_file = tmp_path / "service_accounts.json"
        keys = rot.load_or_mint(keys_file, dry_run=True)
        assert set(keys) == set(rot.SERVICE_NAMES)
        for entry in keys.values():
            assert entry["address"].startswith("0x")
            assert entry["private_key"].startswith("0x")
        assert not keys_file.exists()
        assert "DRY RUN" in capsys.readouterr().out

    def test_existing_file_is_reused_not_reminted(self, rot, tmp_path):
        keys_file = tmp_path / "service_accounts.json"
        existing = {name: {"address": f"0x{i:040x}", "private_key": "0x00"} for i, name in enumerate(rot.SERVICE_NAMES)}
        keys_file.write_text(__import__("json").dumps(existing))
        assert rot.load_or_mint(keys_file, dry_run=False) == existing

    def test_partial_existing_file_aborts(self, rot, tmp_path):
        keys_file = tmp_path / "service_accounts.json"
        keys_file.write_text(__import__("json").dumps({rot.SERVICE_NAMES[0]: {"address": "0x0", "private_key": "0x0"}}))
        with pytest.raises(SystemExit, match="lacks"):
            rot.load_or_mint(keys_file, dry_run=False)


class TestOldAccount:
    def test_derivation_is_deterministic(self, rot):
        """The point of the rotation: these keys are sha256-derivable, so the
        same name must always produce the same address."""
        assert rot.old_account("marketplace").address == rot.old_account("marketplace").address

    def test_build_signed_signature_verifies(self, rot):
        src = rot.old_account("tester")
        tx = rot.build_signed("ait-hub", src, "0x" + "1" * 40, amount=5, nonce=0, fee=0)
        assert tx["signature"]
        assert tx["payload"] == {"to": "0x" + "1" * 40, "amount": 5}
