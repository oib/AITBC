"""CLI-CHAINID-PRECEDENCE-1 (#377): env CHAIN_ID wins on signing paths and any
credentials-vs-env disagreement warns naming both values plus the file path —
never silently. Island-scoped accessors stay creds-pure but warn too. Nothing
here signs or sends; every source is mocked.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import click
import pytest

import aitbc_cli.commands.market as market
import aitbc_cli.utils.island_credentials as ic

OLD = "ait-hub.aitbc.bubuit.net"
NEW = "bc-2"
OLD_ISLAND = "ait-hub.aitbc.bubuit.net-island"
NEW_ISLAND = "bc-2-island"


def _creds(chain_id: str | None = None, island_id: str | None = None) -> dict:
    return {
        "island_id": island_id or NEW_ISLAND,
        "island_name": "test",
        "island_chain_id": chain_id or NEW,
        "credentials": {},
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    monkeypatch.delenv("ISLAND_ID", raising=False)


def test_env_and_creds_agree_no_warning(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", NEW)
    with patch.object(market, "load_island_credentials", return_value=_creds(NEW)), patch.object(market, "warning") as warn:
        assert market.get_chain_id() == NEW
        warn.assert_not_called()


def test_env_wins_on_mismatch_and_warns_both_values_and_path(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", NEW)
    with patch.object(market, "load_island_credentials", return_value=_creds(OLD)), patch.object(market, "warning") as warn:
        assert market.get_chain_id() == NEW
        warn.assert_called_once()
        msg = warn.call_args[0][0]
        assert OLD in msg and NEW in msg and ic.CREDENTIALS_PATH in msg


def test_env_wins_when_creds_absent(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", NEW)
    with (
        patch.object(market, "load_island_credentials", side_effect=FileNotFoundError),
        patch.object(market, "warning") as warn,
    ):
        assert market.get_chain_id() == NEW
        warn.assert_not_called()


def test_creds_win_when_env_unset():
    with patch.object(market, "load_island_credentials", return_value=_creds(OLD)):
        assert market.get_chain_id() == OLD


def test_neither_probe_then_abort(monkeypatch):
    cfg = MagicMock()
    cfg.blockchain_rpc_url = "http://localhost:8202"
    with (
        patch.object(market, "load_island_credentials", side_effect=FileNotFoundError),
        patch.object(market, "get_config", return_value=cfg),
        patch("aitbc_cli.utils.chain_id.get_chain_id", return_value="probed-chain") as probe,
    ):
        assert market.get_chain_id() == "probed-chain"
        probe.assert_called_once()
    with (
        patch.object(market, "load_island_credentials", side_effect=FileNotFoundError),
        patch.object(market, "get_config", return_value=cfg),
        patch("aitbc_cli.utils.chain_id.get_chain_id", side_effect=RuntimeError("dead")),
    ):
        with pytest.raises(click.Abort):
            market.get_chain_id()


def test_unreadable_creds_env_wins_and_warns(monkeypatch, caplog):
    monkeypatch.setenv("CHAIN_ID", NEW)
    with patch.object(market, "load_island_credentials", side_effect=PermissionError("0600 guard")):
        with caplog.at_level(logging.WARNING):
            assert market.get_chain_id() == NEW
        assert any(ic.CREDENTIALS_PATH in r.getMessage() for r in caplog.records)


def test_pure_accessor_contract_unchanged(monkeypatch):
    with patch.object(ic, "load_island_credentials", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError):
            ic.get_chain_id()
    with patch.object(ic, "load_island_credentials", return_value={"island_id": "x"}):
        with pytest.raises(ValueError):
            ic.get_chain_id()


def test_get_island_id_env_first_warns_on_mismatch(monkeypatch):
    monkeypatch.setenv("ISLAND_ID", NEW_ISLAND)
    with (
        patch.object(market, "load_island_credentials", return_value=_creds(island_id=OLD_ISLAND)),
        patch.object(market, "warning") as warn,
    ):
        assert market.get_island_id() == NEW_ISLAND
        warn.assert_called_once()
        msg = warn.call_args[0][0]
        assert OLD_ISLAND in msg and NEW_ISLAND in msg and ic.CREDENTIALS_PATH in msg


def test_island_scoped_accessor_warns_but_creds_win(monkeypatch, caplog):
    monkeypatch.setenv("CHAIN_ID", NEW)
    with patch.object(ic, "load_island_credentials", return_value=_creds(OLD)):
        with caplog.at_level(logging.WARNING):
            assert ic.get_chain_id() == OLD
        assert any(OLD in r.getMessage() and NEW in r.getMessage() for r in caplog.records)
