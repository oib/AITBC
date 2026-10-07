"""Tests for scripts/ops/register_bridge_validators.py key/address binding.

A ``*_SOURCE`` env var name resolves per host (``PROPOSER_KEY`` is hub's key on hub and
node2's own validator key on node2), so a key reached that way must be bound to a
declared address or the script stops. Keys here are throwaway test values.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("eth_keys")
from eth_keys import keys  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "register_bridge_validators.py"

ENV_PREFIXES = ("BRIDGE_ADMIN_", "BRIDGE_VALIDATOR_")
ENV_NAMES = ("PROPOSER_KEY", "GENESIS_PRIVATE_KEY", "HUB1_VALIDATOR_KEY")


def _key(seed: int) -> tuple[str, str]:
    """Return (private key hex without 0x, checksummed address) for a throwaway seed."""
    private = keys.PrivateKey(bytes([seed]) * 32)
    return private.to_hex().removeprefix("0x"), str(private.public_key.to_checksum_address())


@pytest.fixture(scope="module")
def reg():
    spec = importlib.util.spec_from_file_location("register_bridge_validators", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["register_bridge_validators"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    import os

    for name in list(os.environ):
        if name.startswith(ENV_PREFIXES) or name in ENV_NAMES:
            monkeypatch.delenv(name)


class TestAdminBinding:
    def test_source_without_declared_address_is_refused(self, reg, monkeypatch, capsys):
        priv, addr = _key(1)
        monkeypatch.setenv("PROPOSER_KEY", priv)
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_SOURCE", "PROPOSER_KEY")
        with pytest.raises(SystemExit):
            reg._get_admin_private_key()
        err = capsys.readouterr().err
        assert "BRIDGE_ADMIN_ADDRESS" in err
        assert addr in err
        assert priv not in err

    def test_source_with_matching_address_resolves(self, reg, monkeypatch):
        priv, addr = _key(1)
        monkeypatch.setenv("PROPOSER_KEY", priv)
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_SOURCE", "PROPOSER_KEY")
        monkeypatch.setenv("BRIDGE_ADMIN_ADDRESS", addr.lower())
        assert reg._get_admin_private_key() == priv

    def test_checksummed_and_lowercase_declarations_are_equivalent(self, reg, monkeypatch):
        priv, addr = _key(2)
        monkeypatch.setenv("PROPOSER_KEY", priv)
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_SOURCE", "PROPOSER_KEY")
        for spelling in (addr, addr.lower(), addr.removeprefix("0x")):
            monkeypatch.setenv("BRIDGE_ADMIN_ADDRESS", spelling)
            assert reg._get_admin_private_key() == priv

    def test_fallback_to_proposer_key_is_bound_too(self, reg, monkeypatch):
        priv, addr = _key(3)
        monkeypatch.setenv("PROPOSER_KEY", priv)
        with pytest.raises(SystemExit):
            reg._get_admin_private_key()
        monkeypatch.setenv("BRIDGE_ADMIN_ADDRESS", addr)
        assert reg._get_admin_private_key() == priv

    def test_literal_key_needs_no_declaration(self, reg, monkeypatch):
        priv, _ = _key(4)
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY", "0x" + priv)
        assert reg._get_admin_private_key() == priv

    def test_literal_key_with_wrong_declaration_is_refused(self, reg, monkeypatch, capsys):
        priv, _ = _key(4)
        _, other = _key(5)
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY", priv)
        monkeypatch.setenv("BRIDGE_ADMIN_ADDRESS", other)
        with pytest.raises(SystemExit):
            reg._get_admin_private_key()
        assert priv not in capsys.readouterr().err

    def test_key_file_resolves(self, reg, monkeypatch, tmp_path):
        """keys/bridge_admin.key custody: one file, one key, read by path."""
        priv, _ = _key(6)
        key_file = tmp_path / "bridge_admin.key"
        key_file.write_text("0x" + priv + "\n")
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(key_file))
        assert reg._get_admin_private_key() == priv

    def test_key_file_with_matching_declaration_binds(self, reg, monkeypatch, tmp_path):
        priv, addr = _key(6)
        key_file = tmp_path / "bridge_admin.key"
        key_file.write_text(priv)
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(key_file))
        monkeypatch.setenv("BRIDGE_ADMIN_ADDRESS", addr.lower())
        assert reg._get_admin_private_key() == priv
        _, other = _key(7)
        monkeypatch.setenv("BRIDGE_ADMIN_ADDRESS", other)
        with pytest.raises(SystemExit):
            reg._get_admin_private_key()

    def test_missing_key_file_is_refused(self, reg, monkeypatch, capsys):
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", "/nonexistent/bridge_admin.key")
        with pytest.raises(SystemExit):
            reg._get_admin_private_key()
        err = capsys.readouterr().err
        assert "BRIDGE_ADMIN_PRIVATE_KEY_FILE" in err or "bridge_admin.key" in err

    def test_key_file_beats_source_and_literal_beats_file(self, reg, monkeypatch, tmp_path):
        file_priv, _ = _key(8)
        literal_priv, _ = _key(9)
        source_priv, _ = _key(10)
        key_file = tmp_path / "bridge_admin.key"
        key_file.write_text(file_priv)
        monkeypatch.setenv("PROPOSER_KEY", source_priv)
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_SOURCE", "PROPOSER_KEY")
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(key_file))
        assert reg._get_admin_private_key() == file_priv  # file wins over source
        monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY", literal_priv)
        assert reg._get_admin_private_key() == literal_priv  # literal wins over file


class TestValidatorBinding:
    def test_same_declaration_on_two_hosts_catches_the_wrong_one(self, reg, monkeypatch, capsys):
        """The hub/node2 case: one env file, two hosts, PROPOSER_KEY differs per host."""
        hub_priv, hub_addr = _key(10)
        node2_priv, _ = _key(11)
        monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1", "PROPOSER_KEY")
        monkeypatch.setenv("BRIDGE_VALIDATOR_ADDRESS_1", hub_addr)

        monkeypatch.setenv("PROPOSER_KEY", hub_priv)  # on hub
        assert reg._collect_validator_private_keys() == [("validator-1", hub_priv)]

        monkeypatch.setenv("PROPOSER_KEY", node2_priv)  # same file on node2
        with pytest.raises(SystemExit):
            reg._collect_validator_private_keys()
        err = capsys.readouterr().err
        assert "BRIDGE_VALIDATOR_ADDRESS_1" in err
        assert node2_priv not in err and hub_priv not in err

    def test_source_without_declared_address_is_refused(self, reg, monkeypatch):
        priv, _ = _key(12)
        monkeypatch.setenv("PROPOSER_KEY", priv)
        monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1", "PROPOSER_KEY")
        with pytest.raises(SystemExit):
            reg._collect_validator_private_keys()

    def test_each_slot_is_bound_to_its_own_address(self, reg, monkeypatch):
        priv1, addr1 = _key(13)
        priv2, addr2 = _key(14)
        monkeypatch.setenv("HUB1_VALIDATOR_KEY", priv1)
        monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1", "HUB1_VALIDATOR_KEY")
        monkeypatch.setenv("BRIDGE_VALIDATOR_ADDRESS_1", addr1)
        monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_2", "0x" + priv2)
        monkeypatch.setenv("BRIDGE_VALIDATOR_ADDRESS_2", addr2)
        assert reg._collect_validator_private_keys() == [("validator-1", priv1), ("validator-2", priv2)]

        # Slot 2's declaration must not be satisfied by slot 1's address.
        monkeypatch.setenv("BRIDGE_VALIDATOR_ADDRESS_2", addr1)
        with pytest.raises(SystemExit):
            reg._collect_validator_private_keys()

    def test_literal_validator_key_needs_no_declaration(self, reg, monkeypatch):
        priv, _ = _key(15)
        monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_1", priv)
        assert reg._collect_validator_private_keys() == [("validator-1", priv)]

    def test_numbering_stops_at_first_missing_slot(self, reg, monkeypatch):
        priv1, _ = _key(16)
        priv3, _ = _key(17)
        monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_1", priv1)
        monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_3", priv3)
        assert reg._collect_validator_private_keys() == [("validator-1", priv1)]
