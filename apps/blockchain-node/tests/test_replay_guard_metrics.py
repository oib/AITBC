"""OLDFORM-COUNTER-1: ``blockchain_replay_guard_requests_total{endpoint, form}``.

The counter decides, from observed traffic, when ``BRIDGE_LOCK_REQUIRE_REPLAY_GUARD``
can flip: ``legacy_accepted`` counts signed old-form bodies (signature verified
first, so unauthenticated traffic cannot inflate it), ``legacy_refused`` counts
old-form bodies the flag turned away, and ``new_form`` counts guarded bodies.
Tests drive the real JSON path through ``TestClient`` on both routers.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account
from aitbc_chain.rpc.routers.bridge import router as bridge_router
from aitbc_chain.rpc.routers.cross_chain import router as cross_chain_router

METRIC = "blockchain_replay_guard_requests_total"


def _counter(endpoint: str, form: str) -> float:
    value = REGISTRY.get_sample_value(METRIC, {"endpoint": endpoint, "form": form})
    return value if value is not None else 0.0


def _sign(private_key_hex: str, data: dict[str, Any]) -> str:
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(message)).to_hex()


@pytest.fixture(name="engine")
def engine_fixture():
    """Shared in-memory engine — TestClient handlers run on a portal thread."""
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


def _fund(engine, chain_id: str, address: str, balance: int) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _bridge_lock_body(sender: EthAccount, *, new_form: bool, nonce: str = "n-1") -> dict[str, Any]:
    sign_data: dict[str, Any] = {
        "source_chain": "chain-a",
        "target_chain": "chain-b",
        "sender": sender.address,
        "recipient": "0x" + "cc" * 20,
        "amount": 3_600_000,
        "asset": "native",
    }
    if new_form:
        sign_data["issued_at"] = time.time()
        sign_data["nonce"] = nonce
    body = dict(sign_data)
    body["signature"] = _sign(sender.key.hex(), sign_data)
    return body


def _cc_bridge_body(sender: EthAccount, *, new_form: bool, nonce: str = "n-1", amount: int = 1_000) -> dict[str, Any]:
    sign_data: dict[str, Any] = {
        "source_chain": "chain-a",
        "target_chain": "chain-b",
        "sender": sender.address,
        "recipient": "0x" + "bb" * 20,
        "amount": amount,
        "asset": "AIT",
    }
    if new_form:
        sign_data["issued_at"] = time.time()
        sign_data["nonce"] = nonce
    body = dict(sign_data)
    body["signature"] = _sign(sender.key.hex(), sign_data)
    return body


class TestBridgeLockCounter:
    def test_new_form_counted(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        before = _counter("bridge_lock", "new_form")
        resp = client.post("/bridge/lock", json=_bridge_lock_body(sender_account, new_form=True))
        assert resp.status_code == 200, resp.text
        assert _counter("bridge_lock", "new_form") == before + 1

    def test_legacy_accepted_counted_flag_off(self, client: TestClient, engine, sender_account, monkeypatch) -> None:
        monkeypatch.setattr("aitbc_chain.config.settings.bridge_lock_require_replay_guard", False)
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        before = _counter("bridge_lock", "legacy_accepted")
        resp = client.post("/bridge/lock", json=_bridge_lock_body(sender_account, new_form=False))
        assert resp.status_code == 200, resp.text
        assert _counter("bridge_lock", "legacy_accepted") == before + 1

    def test_legacy_refused_counted_flag_on(self, client: TestClient, engine, sender_account, monkeypatch) -> None:
        monkeypatch.setattr("aitbc_chain.config.settings.bridge_lock_require_replay_guard", True)
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000_000)
        before = _counter("bridge_lock", "legacy_refused")
        resp = client.post("/bridge/lock", json=_bridge_lock_body(sender_account, new_form=False))
        assert resp.status_code == 400, resp.text
        assert _counter("bridge_lock", "legacy_refused") == before + 1

    def test_bad_signature_counts_nothing(self, client: TestClient, engine, sender_account, monkeypatch) -> None:
        monkeypatch.setattr("aitbc_chain.config.settings.bridge_lock_require_replay_guard", False)
        snapshot = {f: _counter("bridge_lock", f) for f in ("new_form", "legacy_accepted", "legacy_refused")}
        body = _bridge_lock_body(sender_account, new_form=False)
        body["signature"] = _sign(EthAccount.create().key.hex(), {k: v for k, v in body.items() if k != "signature"})
        resp = client.post("/bridge/lock", json=body)
        assert resp.status_code == 403
        assert {f: _counter("bridge_lock", f) for f in snapshot} == snapshot

    def test_unsigned_counts_nothing(self, client: TestClient) -> None:
        snapshot = {f: _counter("bridge_lock", f) for f in ("new_form", "legacy_accepted", "legacy_refused")}
        body = _bridge_lock_body(EthAccount.create(), new_form=False)
        body.pop("signature")
        resp = client.post("/bridge/lock", json=body)
        assert resp.status_code == 403
        assert {f: _counter("bridge_lock", f) for f in snapshot} == snapshot


class TestCrossChainLockCounter:
    def test_new_form_counted_bridge(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000)
        before = _counter("cross_chain_lock", "new_form")
        resp = client.post("/cross-chain/bridge", json=_cc_bridge_body(sender_account, new_form=True))
        assert resp.status_code == 200, resp.text
        assert _counter("cross_chain_lock", "new_form") == before + 1

    def test_new_form_counted_swap(self, client: TestClient, engine, sender_account) -> None:
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000)
        sign_data: dict[str, Any] = {
            "from_chain": "chain-a",
            "to_chain": "chain-b",
            "from_token": "AIT",
            "to_token": "AIT",
            "sender": sender_account.address,
            "recipient": sender_account.address.lower(),
            "amount": 1_000,
            "min_amount": 0,
            "slippage_tolerance": 0.01,
            "issued_at": time.time(),
            "nonce": "swap-n-1",
        }
        body = dict(sign_data)
        body["signature"] = _sign(sender_account.key.hex(), sign_data)
        before = _counter("cross_chain_lock", "new_form")
        resp = client.post("/swap", json=body)
        assert resp.status_code == 200, resp.text
        assert _counter("cross_chain_lock", "new_form") == before + 1

    def test_legacy_accepted_counted_flag_off(self, client: TestClient, engine, sender_account, monkeypatch) -> None:
        monkeypatch.setattr("aitbc_chain.config.settings.cross_chain_require_replay_guard", False)
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000)
        before = _counter("cross_chain_lock", "legacy_accepted")
        resp = client.post("/cross-chain/bridge", json=_cc_bridge_body(sender_account, new_form=False))
        assert resp.status_code == 200, resp.text
        assert _counter("cross_chain_lock", "legacy_accepted") == before + 1

    def test_legacy_refused_counted_flag_on(self, client: TestClient, engine, sender_account, monkeypatch) -> None:
        monkeypatch.setattr("aitbc_chain.config.settings.cross_chain_require_replay_guard", True)
        _fund(engine, "chain-a", sender_account.address.lower(), 10_000)
        before = _counter("cross_chain_lock", "legacy_refused")
        resp = client.post("/cross-chain/bridge", json=_cc_bridge_body(sender_account, new_form=False))
        assert resp.status_code == 400, resp.text
        assert _counter("cross_chain_lock", "legacy_refused") == before + 1

    def test_bad_signature_counts_nothing(self, client: TestClient, engine, sender_account, monkeypatch) -> None:
        monkeypatch.setattr("aitbc_chain.config.settings.cross_chain_require_replay_guard", False)
        snapshot = {f: _counter("cross_chain_lock", f) for f in ("new_form", "legacy_accepted", "legacy_refused")}
        body = _cc_bridge_body(sender_account, new_form=False)
        body["signature"] = _sign(EthAccount.create().key.hex(), {k: v for k, v in body.items() if k != "signature"})
        resp = client.post("/cross-chain/bridge", json=body)
        assert resp.status_code == 403
        assert {f: _counter("cross_chain_lock", f) for f in snapshot} == snapshot

    def test_unsigned_counts_nothing(self, client: TestClient) -> None:
        snapshot = {f: _counter("cross_chain_lock", f) for f in ("new_form", "legacy_accepted", "legacy_refused")}
        body = _cc_bridge_body(EthAccount.create(), new_form=False)
        body.pop("signature")
        resp = client.post("/cross-chain/bridge", json=body)
        assert resp.status_code == 403
        assert {f: _counter("cross_chain_lock", f) for f in snapshot} == snapshot
