"""#2373: market signing must prefer the serving RPC's chain over stale
island credentials.

A node that ran ``aitbc node island join`` keeps
``/var/lib/aitbc/island_credentials.json`` forever; when it still serves
the hub chain (bc-2), signing market requests with the island id gets
every party-gated route refused. The RPC probe advertises the chain the
node actually serves — it must outrank the join-time cache. Credentials
remain the last resort when no RPC answers, and every disagreement warns.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import click

import aitbc_cli.commands.market as market_pkg


def _creds(chain_id: str) -> dict:
    return {"island_chain_id": chain_id, "island_id": "isl-1", "island_name": "test-island"}


def _invoke_chain_id(monkeypatch, *, creds=None, probe="bc-2", probe_exc=None, env=None):
    """Drive market get_chain_id() with each source stubbed."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)

    def _load():
        if creds is None:
            raise FileNotFoundError("no island credentials")
        return creds

    config = SimpleNamespace(blockchain_rpc_url="http://127.0.0.1:8202")
    with (
        patch.object(market_pkg, "load_island_credentials", side_effect=_load),
        patch.object(market_pkg, "get_config", return_value=config),
        patch("aitbc_cli.utils.chain_id.get_chain_id", side_effect=probe_exc, return_value=probe),
    ):
        return market_pkg.get_chain_id()


@pytest.mark.unit
def test_rpc_probe_outranks_stale_island_credentials(monkeypatch):
    """The #2373 regression: island creds say ait-8ae57c67, node serves bc-2."""
    result = _invoke_chain_id(monkeypatch, creds=_creds("ait-8ae57c67"), probe="bc-2")
    assert result == "bc-2"


@pytest.mark.unit
def test_probe_result_returned_when_no_credentials(monkeypatch):
    assert _invoke_chain_id(monkeypatch, creds=None, probe="bc-2") == "bc-2"


@pytest.mark.unit
def test_credentials_fallback_when_probe_fails(monkeypatch):
    result = _invoke_chain_id(
        monkeypatch,
        creds=_creds("ait-island-1"),
        probe_exc=RuntimeError("no rpc"),
    )
    assert result == "ait-island-1"


@pytest.mark.unit
def test_chain_id_env_still_wins(monkeypatch):
    result = _invoke_chain_id(
        monkeypatch,
        creds=_creds("ait-8ae57c67"),
        probe="bc-2",
        env={"CHAIN_ID": "bc-2"},
    )
    assert result == "bc-2"


@pytest.mark.unit
def test_probe_failure_without_credentials_aborts(monkeypatch):
    with pytest.raises(click.Abort):
        _invoke_chain_id(monkeypatch, creds=None, probe_exc=RuntimeError("no rpc"))
