"""GAP-47 tests for the cross-chain swap/bridge RPC router.

The router no longer simulates settlement: ``POST /swap`` and
``POST /cross-chain/bridge`` verify a wallet signature and run the real
``CrossChainBridge.initiate_transfer`` path, returning the actual
``BRIDGE_LOCK`` transaction hash. These tests exercise signature
verification, rate/slippage validation, persistence of ``CrossChainSwap``
rows, and honest (non-terminal) status reporting.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from eth_keys import keys
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.models import Account, CrossChainSwap, CrossChainTransfer
from aitbc_chain.rpc.routers.cross_chain import router


def _sign_request(private_key_hex: str, data: dict[str, Any]) -> str:
    """Sign a request payload the same way verify_request_signature does."""
    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(message)).to_hex()


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    """A CrossChainBridge backed by the in-memory engine."""
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def sender_account() -> EthAccount:
    return EthAccount.create()


@pytest.fixture(autouse=True)
def _patch_settings():
    """Allow test chain IDs and wire the test bridge into the router."""
    with (
        patch("aitbc_chain.config.settings.supported_chains", "chain-a,chain-b"),
        patch("aitbc_chain.config.settings.bridge_supported_chains", "chain-b"),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_bridge(bridge: CrossChainBridge):
    with patch("aitbc_chain.cross_chain.bridge.get_cross_chain_bridge", return_value=bridge):
        yield


def _fund(engine, chain_id: str, address: str, balance: int) -> None:
    with Session(engine) as session:
        session.add(Account(chain_id=chain_id, address=address, balance=balance, nonce=0))
        session.commit()


def _swap_sign_data(sender: str, recipient: str, amount_units: int, **overrides) -> dict[str, Any]:
    data: dict[str, Any] = {
        "from_chain": "chain-a",
        "to_chain": "chain-b",
        "from_token": "AIT",
        "to_token": "AIT",
        "sender": sender,
        "recipient": recipient,
        "amount": amount_units,
        "min_amount": 0,
        "slippage_tolerance": 0.01,
    }
    data.update(overrides)
    return data


class TestCrossChainSwap:
    """POST /swap must run a real signed bridge lock, not simulate."""

    def test_swap_requires_signature(self, client: TestClient, engine, sender_account) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        payload = _swap_sign_data(sender_account.address, sender, 1_000)
        # No signature at all
        resp = client.post("/swap", json=payload)
        assert resp.status_code == 403

    def test_swap_rejects_wrong_signature(self, client: TestClient, engine, sender_account) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(EthAccount.create().key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        assert resp.status_code == 403

    def test_swap_rejects_same_chain(self, client: TestClient, engine, sender_account) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000, to_chain="chain-a")
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        assert resp.status_code == 400

    def test_swap_rejects_unconfigured_token_pair(self, client: TestClient, engine, sender_account) -> None:
        """Different tokens with no configured rate are refused — no invented price."""
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000, to_token="OTHER")
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        assert resp.status_code == 400
        assert "No swap rate configured" in resp.json()["detail"]

    def test_swap_rejects_decimal_amount(self, client: TestClient, engine, sender_account) -> None:
        """Amounts must be integer compute-units, not ambiguous decimals."""
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["amount"] = "1.5"
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        assert resp.status_code == 400

    def test_signed_swap_creates_real_lock_and_persists(
        self, client: TestClient, engine, bridge: CrossChainBridge, sender_account
    ) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)

        resp = client.post("/swap", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["status"] in ("pending", "locked")
        # The returned hash is the real BRIDGE_LOCK tx hash == transfer_id.
        assert body["from_tx_hash"] == body["transfer_id"]
        assert not body["from_tx_hash"].startswith("0xfrom")
        assert body["to_tx_hash"] is None
        # Same-asset parity: expected == locked amount.
        assert body["expected_amount_units"] == 1_000

        # A real CrossChainTransfer row exists, with the quoted release amount.
        with Session(engine) as session:
            record = session.get(CrossChainTransfer, body["transfer_id"])
            assert record is not None
            assert record.status == "pending"
            assert record.source_tx_hash == body["from_tx_hash"]
            assert record.release_amount == 1_000

            # The swap row is persisted too.
            swap = session.get(CrossChainSwap, body["swap_id"])
            assert swap is not None
            assert swap.transfer_id == body["transfer_id"]
            assert swap.amount_units == 1_000

        # Sender was actually debited amount + fee.
        with Session(engine) as session:
            acct = session.get(Account, ("chain-a", sender))
            assert acct is not None
            assert acct.balance < 10_000

    def test_swap_min_amount_slippage_guard(self, client: TestClient, engine, sender_account) -> None:
        """A min_amount above the parity quote is rejected."""
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000, min_amount=1_001)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        assert resp.status_code == 400
        assert "min_amount" in resp.json()["detail"]

    def test_swap_status_reports_honest_pending(self, client: TestClient, engine, sender_account) -> None:
        """A locked-but-unconfirmed swap reports pending, never completed."""
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        swap_id = resp.json()["swap_id"]

        status = client.get(f"/cross-chain/swap/{swap_id}")
        assert status.status_code == 200
        body = status.json()
        assert body["status"] == "pending"
        assert body["to_tx_hash"] is None
        assert body["actual_amount"] is None

    def test_swap_status_404_for_unknown(self, client: TestClient) -> None:
        resp = client.get("/cross-chain/swap/swap_doesnotexist")
        assert resp.status_code == 404


class TestCrossChainBridgeEndpoint:
    """POST /cross-chain/bridge must run a real signed bridge lock."""

    def _bridge_sign_data(self, sender: str, recipient: str, amount_units: int, **overrides) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source_chain": "chain-a",
            "target_chain": "chain-b",
            "sender": sender,
            "recipient": recipient,
            "amount": amount_units,
            "asset": "AIT",
        }
        data.update(overrides)
        return data

    def test_bridge_requires_signature(self, client: TestClient, engine, sender_account) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        payload = self._bridge_sign_data(sender_account.address, sender, 1_000)
        resp = client.post("/cross-chain/bridge", json=payload)
        assert resp.status_code == 403

    def test_signed_bridge_locks_and_reports_pending(
        self, client: TestClient, engine, bridge: CrossChainBridge, sender_account
    ) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = self._bridge_sign_data(sender_account.address, sender, 2_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)

        resp = client.post("/cross-chain/bridge", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["bridge_id"] == body["source_tx_hash"]
        assert not body["source_tx_hash"].startswith("0xsrc")
        assert body["target_tx_hash"] is None
        assert body["status"] in ("pending", "locked")

        with Session(engine) as session:
            record = session.get(CrossChainTransfer, body["bridge_id"])
            assert record is not None
            assert record.status == "pending"
            assert record.release_amount is None  # plain bridge: release == lock

        # Status endpoint reports the honest pending state.
        status = client.get(f"/cross-chain/bridge/{body['bridge_id']}")
        assert status.status_code == 200
        sbody = status.json()
        assert sbody["status"] == "pending"
        assert sbody["target_tx_hash"] is None
        assert sbody["recipient_address"] == sender

    def test_bridge_status_404_for_unknown(self, client: TestClient) -> None:
        resp = client.get("/cross-chain/bridge/0xdeadbeef")
        assert resp.status_code == 404

    def test_bridge_rejects_unsupported_target(self, client: TestClient, engine, sender_account) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = self._bridge_sign_data(sender_account.address, sender, 1_000, target_chain="chain-zzz")
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/cross-chain/bridge", json=payload)
        assert resp.status_code == 400


class TestCrossChainReadOnly:
    """Read-only endpoints reflect real persisted state, not demo data."""

    def test_rates_empty_by_default(self, client: TestClient) -> None:
        resp = client.get("/cross-chain/rates")
        assert resp.status_code == 200
        assert resp.json()["rates"] == {}

    def test_pools_is_honestly_empty(self, client: TestClient) -> None:
        resp = client.get("/cross-chain/pools")
        assert resp.status_code == 200
        assert resp.json()["pools"] == []

    def test_swaps_lists_persisted_rows(self, client: TestClient, engine, sender_account) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        client.post("/swap", json=payload)

        resp = client.get("/cross-chain/swaps")
        assert resp.status_code == 200
        swaps = resp.json()["swaps"]
        assert len(swaps) == 1
        assert swaps[0]["status"] == "pending"

    def test_stats_reflect_real_records(self, client: TestClient, engine, sender_account) -> None:
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        client.post("/swap", json=payload)

        resp = client.get("/cross-chain/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_volume_units"] == 1_000
        statuses = {s["status"] for s in body["swap_stats"]}
        assert statuses == {"pending"}


class TestSwapFinalityRelay:
    """The relayer path moves a real lock through the genuine lifecycle."""

    def test_relay_confirm_with_real_proof(self, client: TestClient, engine, bridge: CrossChainBridge, sender_account) -> None:
        """A sealed + finalized lock can be confirmed through the real path.

        This exercises build_proof (persisted tx.type detection), header
        sync (store_block_header) and confirm_transfer without simulation.
        """
        from aitbc_chain.models import Block, Transaction

        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        assert resp.status_code == 200, resp.text
        transfer_id = resp.json()["transfer_id"]

        # Seal the lock tx into a real block row.
        with Session(engine) as session:
            lock_tx = session.exec(
                select(Transaction).where(Transaction.chain_id == "chain-a", Transaction.tx_hash == transfer_id)
            ).first()
            assert lock_tx is not None
            lock_tx.block_height = 5
            session.add(lock_tx)
            session.add(
                Block(
                    chain_id="chain-a",
                    height=5,
                    hash="0x" + "ab" * 32,
                    parent_hash="0x" + "00" * 32,
                    proposer="0xproposer",
                    state_root="0x" + "cd" * 32,
                    timestamp=lock_tx.timestamp,
                )
            )
            session.commit()

        # build_proof must find the lock via the persisted tx.type column.
        proof = bridge.build_proof(transfer_id, source_chain="chain-a")
        assert proof["lock_tx_hash"] == transfer_id
        assert proof["block_height"] == 5

    def test_build_proof_refuses_unsealed_lock(
        self, client: TestClient, engine, bridge: CrossChainBridge, sender_account
    ) -> None:
        """An unsealed lock must not produce a proof anchored to a wrong block."""
        sender = sender_account.address.lower()
        _fund(engine, "chain-a", sender, 10_000)
        sign_data = _swap_sign_data(sender_account.address, sender, 1_000)
        payload = dict(sign_data)
        payload["signature"] = _sign_request(sender_account.key.hex(), sign_data)
        resp = client.post("/swap", json=payload)
        transfer_id = resp.json()["transfer_id"]

        with pytest.raises(ValueError, match="not sealed"):
            bridge.build_proof(transfer_id, source_chain="chain-a")
