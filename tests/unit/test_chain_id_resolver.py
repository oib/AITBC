"""Tests for aitbc.utils.chain_id resolution (RESET-CHAINID-SWEEP-1 #347).

Shared precedence: explicit arg > AITBC_CHAIN_ID > CHAIN_ID, then either the
caller-supplied ``default`` (``default_chain_id()`` lands on ``"bc-2"``) or a
strict ``ChainIdNotConfigured``. Empty strings count as unset at every level.
"""

from __future__ import annotations

import pytest

from aitbc.utils.chain_id import (
    DEFAULT_CHAIN_ID,
    ChainIdNotConfigured,
    default_chain_id,
    resolve_chain_id,
)


@pytest.fixture(autouse=True)
def _clear_chain_env(monkeypatch):
    monkeypatch.delenv("AITBC_CHAIN_ID", raising=False)
    monkeypatch.delenv("CHAIN_ID", raising=False)


def test_explicit_arg_wins_over_env(monkeypatch):
    monkeypatch.setenv("AITBC_CHAIN_ID", "env-aitbc")
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    assert resolve_chain_id("explicit") == "explicit"
    assert resolve_chain_id("explicit", default=DEFAULT_CHAIN_ID) == "explicit"


def test_aitbc_chain_id_wins_over_chain_id(monkeypatch):
    monkeypatch.setenv("AITBC_CHAIN_ID", "env-aitbc")
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    assert resolve_chain_id() == "env-aitbc"
    assert resolve_chain_id(None) == "env-aitbc"
    assert resolve_chain_id("") == "env-aitbc"
    assert default_chain_id() == "env-aitbc"


def test_chain_id_env_used_when_aitbc_unset(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    assert resolve_chain_id() == "env-chain"
    assert default_chain_id() == "env-chain"


def test_strict_raises_without_default():
    with pytest.raises(ChainIdNotConfigured):
        resolve_chain_id()


def test_default_param_returns_default():
    assert resolve_chain_id(default="x-1") == "x-1"
    assert resolve_chain_id("", default="x-1") == "x-1"


def test_default_chain_id_is_bc2():
    assert DEFAULT_CHAIN_ID == "bc-2"
    assert default_chain_id() == "bc-2"


def test_dataclass_defaults_resolve(monkeypatch):
    """SDK dataclass fields resolve through the same precedence — an env-set
    run stamps the env id, a bare run stamps bc-2; never ait-hub."""
    from aitbc.governance.types import ExecuteData

    assert ExecuteData(proposal_id="p", executor="e").chain_id == "bc-2"
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    assert ExecuteData(proposal_id="p", executor="e").chain_id == "env-chain"
