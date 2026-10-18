"""CALLERS-NEWFORM-1: the bodies migrated callers emit pass both replay flags.

Drives the real routes through ``TestClient`` with both
``*_REQUIRE_REPLAY_GUARD`` flags on — the fleet posture — using the exact body
key sets the updated callers send:

- CLI ``bridge lock`` and MCP ``bridge_lock``: canonical keys + ``issued_at`` /
  ``nonce``.
- MCP ``create_cross_chain_swap``: ``user_address`` (sender alias), no
  ``recipient`` (defaults to sender) — plus ``signature`` / replay fields.
- MCP ``create_cross_chain_bridge``: ``sender`` + ``recipient_address`` +
  ``token`` (recipient/asset aliases) — plus ``signature`` / replay fields.

New-form bodies are accepted; the same bodies without the two fields are the
old form and answer 400. Throwaway keys only.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc.routers.bridge import router as bridge_router
from aitbc_chain.rpc.routers.cross_chain import router as cross_chain_router


def _sign(private_key_hex: str, data: dict[str, Any]) -> str:
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(message)).to_hex()


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    try:
        yield engine
    finally:
        chain_metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(bridge_router)
    app.include_router(cross_chain_router)
    return TestClient(app)


@pytest.fixture
def sender_account() -> EthAccount:
    return EthAccount.create()


@pytest.fixture(autouse=True)
def _patch_settings():
    from unittest.mock import patch

    with (
        patch("aitbc_chain.config.settings.supported_chains", "chain-a,chain-b"),
        patch("aitbc_chain.config.settings.bridge_supported_chains", "chain-b"),
        patch("aitbc_chain.config.settings.block_scoped_preregistered_transactions", False),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_bridge_and_nonce(bridge: CrossChainBridge, tmp_path, monkeypatch):
    monkeypatch.setattr("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", lambda: bridge)
    monkeypatch.setattr("aitbc_chain.rpc.utils._nonce_db_path", lambda: tmp_path / "nonces.db")
    monkeypatch.setattr("aitbc_chain.config.settings.bridge_lock_require_replay_guard", True)
    monkeypatch.setattr("aitbc_chain.config.settings.cross_chain_require_replay_guard", True)


def _fund(engine, chain_id: str, address: str, balance: int) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _cli_lock_body(sender: EthAccount, *, guarded: bool) -> dict[str, Any]:
    """Body emitted by ``aitbc bridge lock --signature --issued-at --nonce``."""
    sign_data: dict[str, Any] = {
        "source_chain": "chain-a",
        "target_chain": "chain-b",
        "sender": sender.address,
        "recipient": "0x" + "cc" * 20,
        "amount": 3_600_000,
        "asset": "native",
    }
    if guarded:
        sign_data["issued_at"] = int(time.time())
        sign_data["nonce"] = "cli-nonce-1"
    body = dict(sign_data)
    body["signature"] = _sign(sender.key.hex(), sign_data)
    return body


def _mcp_swap_body(sender: EthAccount, *, guarded: bool) -> dict[str, Any]:
    """Body emitted by MCP ``create_cross_chain_swap`` (sender via ``user_address``)."""
    sign_data: dict[str, Any] = {
        "from_chain": "chain-a",
        "to_chain": "chain-b",
        "from_token": "AIT",
        "to_token": "AIT",
        "sender": sender.address,
        "recipient": sender.address,  # route defaults recipient to sender
        "amount": 1_000,
        "min_amount": 0,
        "slippage_tolerance": 0.01,
    }
    if guarded:
        sign_data["issued_at"] = int(time.time())
        sign_data["nonce"] = "mcp-swap-1"
    body = {
        "from_chain": sign_data["from_chain"],
        "to_chain": sign_data["to_chain"],
        "from_token": sign_data["from_token"],
        "to_token": sign_data["to_token"],
        "amount": sign_data["amount"],
        "slippage_tolerance": sign_data["slippage_tolerance"],
        "user_address": sender.address,
        "signature": _sign(sender.key.hex(), sign_data),
    }
    if guarded:
        body["issued_at"] = sign_data["issued_at"]
        body["nonce"] = sign_data["nonce"]
    return body


def _mcp_cc_bridge_body(sender: EthAccount, *, guarded: bool) -> dict[str, Any]:
    """Body emitted by MCP ``create_cross_chain_bridge`` (recipient/token aliases)."""
    sign_data: dict[str, Any] = {
        "source_chain": "chain-a",
        "target_chain": "chain-b",
        "sender": sender.address,
        "recipient": "0x" + "bb" * 20,
        "amount": 1_000,
        "asset": "AIT",
    }
    if guarded:
        sign_data["issued_at"] = int(time.time())
        sign_data["nonce"] = "mcp-bridge-1"
    body = {
        "source_chain": sign_data["source_chain"],
        "target_chain": sign_data["target_chain"],
        "token": "AIT",
        "amount": sign_data["amount"],
        "sender": sign_data["sender"],
        "recipient_address": sign_data["recipient"],
        "signature": _sign(sender.key.hex(), sign_data),
    }
    if guarded:
        body["issued_at"] = sign_data["issued_at"]
        body["nonce"] = sign_data["nonce"]
    return body


class TestCallerShapedBodiesFlagsOn:
    def test_cli_lock_new_form_accepted(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        resp = client.post("/bridge/lock", json=_cli_lock_body(sender_account, guarded=True))
        assert resp.status_code == 200, resp.text

    def test_cli_lock_old_form_refused(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        resp = client.post("/bridge/lock", json=_cli_lock_body(sender_account, guarded=False))
        assert resp.status_code == 400, resp.text

    def test_mcp_swap_alias_shape_accepted(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        resp = client.post("/swap", json=_mcp_swap_body(sender_account, guarded=True))
        assert resp.status_code == 200, resp.text

    def test_mcp_swap_alias_shape_old_form_refused(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        resp = client.post("/swap", json=_mcp_swap_body(sender_account, guarded=False))
        assert resp.status_code == 400, resp.text

    def test_mcp_cc_bridge_alias_shape_accepted(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        resp = client.post("/cross-chain/bridge", json=_mcp_cc_bridge_body(sender_account, guarded=True))
        assert resp.status_code == 200, resp.text

    def test_mcp_cc_bridge_alias_shape_old_form_refused(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        resp = client.post("/cross-chain/bridge", json=_mcp_cc_bridge_body(sender_account, guarded=False))
        assert resp.status_code == 400, resp.text
