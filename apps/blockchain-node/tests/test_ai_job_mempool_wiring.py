"""AI job submission must reach the mempool (issue #162).

Before this, ``/rpc/ai/submit`` wrote a ``Transaction`` row directly with
``status="queued"`` and never enqueued anything, so a submitted job could never
be included in a block: the public chain minted 103k empty blocks while one job
sat queued for five weeks.

These tests pin the two properties that were missing:

* a valid job is handed to ``mempool.add`` in the shape the PoA proposer reads
  (``from``/``to``/``amount``/``fee``), so it can actually be mined;
* the job debits the sender, so an unsigned or wrongly-signed request is
  rejected and never reaches the mempool.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.utils import DEFAULT_TX_FEE_UNITS, ait_to_units
from aitbc_chain.rpc.ai_services import AI_JOB_TX_TYPE, AI_SERVICE_RECIPIENT
from aitbc_chain.rpc.router import router
from aitbc_chain.rpc.utils import get_chain_id

# Deterministic secp256k1 test key and its derived address (same key style as
# test_signing_round_trip.py).
PK_HEX = "4c0883a69102937d6231471b5dbb6204fe512961708279e1c1d4f0e0a1d9d2e3"
ADDR = keys.PrivateKey(bytes.fromhex(PK_HEX)).public_key.to_checksum_address()

PAYMENT_AIT = 2.0


def _sign(tx_data: dict[str, Any]) -> str:
    """Sign the canonical JSON of a tx (minus signature), as the verifier expects."""
    unsigned = {k: v for k, v in tx_data.items() if k != "signature"}
    message = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(PK_HEX))
    return pk.sign_msg_hash(keccak(message)).to_bytes().hex()


def _job_request(signature: str | None = None, nonce: int = 0, fee: int = DEFAULT_TX_FEE_UNITS) -> dict[str, Any]:
    """Build an /ai/submit body, signing the exact tx the endpoint will rebuild."""
    body = {
        "wallet_address": ADDR,
        "job_type": "inference",
        "prompt": "hello world",
        "payment": PAYMENT_AIT,
        "parameters": {},
        "nonce": nonce,
        "fee": fee,
    }
    tx_data = {
        "from": ADDR,
        "to": AI_SERVICE_RECIPIENT,
        "amount": ait_to_units(PAYMENT_AIT),
        "fee": fee,
        "nonce": nonce,
        "type": AI_JOB_TX_TYPE,
        "payload": {
            "job_type": body["job_type"],
            "prompt": body["prompt"],
            "payment": PAYMENT_AIT,
            "parameters": {},
        },
        "chain_id": get_chain_id(),
    }
    body["signature"] = signature if signature is not None else _sign(tx_data)
    return body


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def mempool() -> MagicMock:
    mock = MagicMock()
    mock.add.return_value = "0xdeadbeef"
    return mock


class TestAIJobReachesMempool:
    def test_valid_job_is_added_to_mempool(self, client: TestClient, mempool: MagicMock) -> None:
        """The regression: a submitted job must be enqueued, not written to a dead row."""
        with (
            patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
            patch("aitbc_chain.rpc.transactions._validate_transaction_admission"),
        ):
            response = client.post("/ai/submit", json=_job_request())

        assert response.status_code == 200, response.text
        mempool.add.assert_called_once()

    def test_enqueued_tx_has_the_shape_the_proposer_reads(self, client: TestClient, mempool: MagicMock) -> None:
        """consensus/poa.py skips any tx without from/to and a payable amount."""
        with (
            patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
            patch("aitbc_chain.rpc.transactions._validate_transaction_admission"),
        ):
            client.post("/ai/submit", json=_job_request())

        tx = mempool.add.call_args.args[0]
        assert tx["from"] == ADDR
        assert tx["to"] == AI_SERVICE_RECIPIENT
        # Payment is quoted in AIT but the chain settles in compute-units.
        assert tx["amount"] == ait_to_units(PAYMENT_AIT)
        assert tx["fee"] == DEFAULT_TX_FEE_UNITS
        # The proposer upper-cases type when persisting; it must already match
        # what the job queries look for.
        assert tx["type"] == AI_JOB_TX_TYPE
        assert tx["payload"]["job_type"] == "inference"

    def test_job_is_enqueued_on_the_resolved_chain(self, client: TestClient, mempool: MagicMock) -> None:
        """The old code hardcoded chain_id="" so rows never matched the running chain."""
        with (
            patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
            patch("aitbc_chain.rpc.transactions._validate_transaction_admission"),
        ):
            client.post("/ai/submit", json=_job_request())

        assert mempool.add.call_args.kwargs["chain_id"] == get_chain_id()
        assert mempool.add.call_args.args[0]["chain_id"] == get_chain_id()

    def test_job_id_is_the_mempool_tx_hash(self, client: TestClient, mempool: MagicMock) -> None:
        """job_id must be the real tx hash, not a uuid unrelated to any chain state."""
        with (
            patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
            patch("aitbc_chain.rpc.transactions._validate_transaction_admission"),
        ):
            response = client.post("/ai/submit", json=_job_request())

        body = response.json()
        assert body["tx_hash"] == "0xdeadbeef"
        assert body["job_id"] == body["tx_hash"]
        assert body["status"] == "pending"


class TestAIJobRequiresSignature:
    def test_wrong_signature_is_rejected_and_not_enqueued(self, client: TestClient, mempool: MagicMock) -> None:
        """A job moves the sender's balance, so an unauthenticated one must not be admitted."""
        someone_else = keys.PrivateKey(bytes.fromhex("11" * 32))
        forged = someone_else.sign_msg_hash(keccak(b"anything")).to_bytes().hex()

        with (
            patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
            patch("aitbc_chain.rpc.transactions._validate_transaction_admission"),
        ):
            response = client.post("/ai/submit", json=_job_request(signature=forged))

        assert response.status_code == 403
        mempool.add.assert_not_called()

    def test_signature_is_required(self, client: TestClient) -> None:
        body = _job_request()
        del body["signature"]
        assert client.post("/ai/submit", json=body).status_code == 422

    def test_rejected_job_returns_400_not_silent_success(self, client: TestClient, mempool: MagicMock) -> None:
        """Admission failures (unknown sender, low balance, bad nonce) must surface."""
        with (
            patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
            patch(
                "aitbc_chain.rpc.transactions._validate_transaction_admission",
                side_effect=ValueError("sender account not found on chain 'ait-mainnet'"),
            ),
        ):
            response = client.post("/ai/submit", json=_job_request())

        assert response.status_code == 400
        assert "sender account not found" in response.json()["detail"]
        mempool.add.assert_not_called()
