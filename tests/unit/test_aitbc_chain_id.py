"""Tests for aitbc.utils.chain_id.resolve_chain_id."""

import pytest

from aitbc.exceptions import ConfigurationError
from aitbc.utils.chain_id import ChainIdNotConfigured, resolve_chain_id


class TestResolveChainId:
    def test_explicit_argument_wins(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "env-chain")
        assert resolve_chain_id("explicit-chain") == "explicit-chain"

    def test_explicit_argument_without_env(self, monkeypatch):
        monkeypatch.delenv("CHAIN_ID", raising=False)
        assert resolve_chain_id("explicit-chain") == "explicit-chain"

    def test_env_used_when_no_argument(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "env-chain")
        assert resolve_chain_id() == "env-chain"
        assert resolve_chain_id(None) == "env-chain"

    def test_env_whitespace_stripped(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "  env-chain  ")
        assert resolve_chain_id() == "env-chain"

    def test_empty_argument_falls_through_to_env(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "env-chain")
        assert resolve_chain_id("") == "env-chain"
        assert resolve_chain_id("   ") == "env-chain"

    def test_unset_raises(self, monkeypatch):
        monkeypatch.delenv("CHAIN_ID", raising=False)
        with pytest.raises(ChainIdNotConfigured, match="CHAIN_ID"):
            resolve_chain_id()

    def test_empty_env_raises(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "")
        with pytest.raises(ChainIdNotConfigured, match="CHAIN_ID"):
            resolve_chain_id()

    def test_whitespace_env_raises(self, monkeypatch):
        monkeypatch.setenv("CHAIN_ID", "   ")
        with pytest.raises(ChainIdNotConfigured, match="CHAIN_ID"):
            resolve_chain_id()

    def test_error_names_the_env_var(self, monkeypatch):
        monkeypatch.delenv("CHAIN_ID", raising=False)
        with pytest.raises(ChainIdNotConfigured) as excinfo:
            resolve_chain_id()
        assert "CHAIN_ID" in str(excinfo.value)

    def test_error_is_configuration_error(self, monkeypatch):
        monkeypatch.delenv("CHAIN_ID", raising=False)
        with pytest.raises(ConfigurationError):
            resolve_chain_id()
