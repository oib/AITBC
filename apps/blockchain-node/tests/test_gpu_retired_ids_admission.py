"""GPU_RETIRED_IDS: admission refuses GPU_REGISTER / GPU_ALLOCATE naming a retired gpu_id.

On 2 Oct 2026 ten test and canary registrations were removed from the fleet's registries by SQL. Nothing stopped
anyone from registering one of those ids again (the eight sealed ones also left no registrant on record to guard
them), so the node can now refuse them at the door. The setting is admission only: consensus does not apply it, and
with it unset (the default) nothing is refused.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.base_models import Account
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.database import chain_metadata
from aitbc_chain.rpc import transactions as tx_mod
from aitbc_chain.rpc.transactions import _validate_transaction_admission
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.gpu_resources import retired_gpu_error

CHAIN = "ait-test"
KEY = "0x" + "33" * 32
SENDER = derive_ethereum_address(KEY)
RETIRED = "canary9-gpu-001"
FRESH = "gpu-fresh-1"


def _gpu_payload(gpu_id: str) -> dict[str, Any]:
    return {"gpu_id": gpu_id, "miner_id": "miner-1", "model": "RTX 4090", "memory_gb": 24, "price_per_hour": "0.1"}


def _tx(tx_type: str, gpu_id: str, nonce: int = 0, **overrides: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": SENDER,
        "to": SENDER,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": nonce,
        "type": tx_type,
        "chain_id": CHAIN,
        "payload": _gpu_payload(gpu_id) if tx_type == "GPU_REGISTER" else {"gpu_id": gpu_id, "client_id": "c-1"},
    }
    tx.update(overrides)
    return tx


@pytest.fixture
def retired(monkeypatch):
    monkeypatch.setattr(settings, "gpu_retired_ids", f"{RETIRED}, gpu-live-05")


# --------------------------------------------------------------------------------------------------------------------
# the rule and the setting
# --------------------------------------------------------------------------------------------------------------------


class TestRule:
    IDS = frozenset({RETIRED, "gpu-live-05"})

    @pytest.mark.parametrize("tx_type", ["GPU_REGISTER", "GPU_ALLOCATE"])
    def test_refuses_a_retired_id(self, tx_type):
        error = retired_gpu_error(tx_type, {"gpu_id": RETIRED}, self.IDS)
        assert error and RETIRED in error and tx_type in error

    @pytest.mark.parametrize("tx_type", ["GPU_REGISTER", "GPU_ALLOCATE"])
    def test_admits_another_id(self, tx_type):
        assert retired_gpu_error(tx_type, {"gpu_id": FRESH}, self.IDS) is None

    def test_nothing_is_refused_when_the_set_is_empty(self):
        assert retired_gpu_error("GPU_REGISTER", {"gpu_id": RETIRED}, frozenset()) is None

    @pytest.mark.parametrize("tx_type", ["GPU_DEREGISTER", "GPU_MARKET", "TRANSFER", "STAKE"])
    def test_other_types_are_not_touched(self, tx_type):
        assert retired_gpu_error(tx_type, {"gpu_id": RETIRED}, self.IDS) is None

    @pytest.mark.parametrize("payload", [None, [], "gpu", 7, {}, {"gpu_id": None}, {"gpu_id": 5}, {"gpu_id": ""}])
    def test_malformed_payloads_are_left_to_the_existing_validation(self, payload):
        assert retired_gpu_error("GPU_REGISTER", payload, self.IDS) is None

    def test_ids_compare_exactly(self):
        assert retired_gpu_error("GPU_REGISTER", {"gpu_id": RETIRED.upper()}, self.IDS) is None
        assert retired_gpu_error("GPU_REGISTER", {"gpu_id": RETIRED + " "}, self.IDS) is None


class TestSetting:
    def test_default_is_empty(self):
        assert ChainSettings().gpu_retired_id_set() == frozenset()

    def test_parses_a_comma_list(self):
        cfg = ChainSettings(gpu_retired_ids=" a ,b,, c ,")
        assert cfg.gpu_retired_id_set() == frozenset({"a", "b", "c"})

    def test_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("GPU_RETIRED_IDS", "canary-gpu-001,gpu-live-06")
        assert ChainSettings().gpu_retired_id_set() == frozenset({"canary-gpu-001", "gpu-live-06"})


# --------------------------------------------------------------------------------------------------------------------
# the shared admission door (REST, gossip ingest, p2p transport and the AI-job path all call it)
# --------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def door(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Account(chain_id=CHAIN, address=SENDER, balance=10_000_000, nonce=0))
        session.commit()

        @contextmanager
        def _scope(*_a, **_kw):
            yield session

        monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
        monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])
        yield lambda tx: _validate_transaction_admission(tx, None)


class TestAdmissionDoor:
    @pytest.mark.parametrize("tx_type", ["GPU_REGISTER", "GPU_ALLOCATE"])
    def test_refuses_a_retired_id(self, door, retired, tx_type):
        with pytest.raises(ValueError, match="retired"):
            door(_tx(tx_type, RETIRED))

    @pytest.mark.parametrize("tx_type", ["GPU_REGISTER", "GPU_ALLOCATE"])
    def test_admits_another_id(self, door, retired, tx_type):
        door(_tx(tx_type, FRESH))

    @pytest.mark.parametrize("tx_type", ["GPU_REGISTER", "GPU_ALLOCATE"])
    def test_admits_a_retired_id_when_the_setting_is_unset(self, door, tx_type):
        assert settings.gpu_retired_ids == ""
        door(_tx(tx_type, RETIRED))

    def test_a_transfer_envelope_carrying_the_type_in_its_payload_is_refused_too(self, door, retired):
        """Consensus resolves a TRANSFER whose payload names a type under that type; the door must as well."""
        tx = _tx("TRANSFER", RETIRED, payload={**_gpu_payload(RETIRED), "type": "GPU_REGISTER"})
        with pytest.raises(ValueError, match="retired"):
            door(tx)

    def test_every_earlier_rejection_keeps_its_message(self, door, retired):
        with pytest.raises(ValueError, match="stale nonce|insufficient balance|sender account not found"):
            door(_tx("GPU_REGISTER", RETIRED, **{"from": "0x" + "9" * 40}))


# --------------------------------------------------------------------------------------------------------------------
# the GPU_REGISTER branch of /rpc/transactions/market, which does not call the door
# --------------------------------------------------------------------------------------------------------------------


def _signed_market_register(gpu_id: str) -> dict[str, Any]:
    tx = _tx("GPU_REGISTER", gpu_id)
    tx["signature"] = sign_transaction_data(tx, KEY)
    return tx


@pytest.mark.asyncio
class TestMarketRoute:
    async def _submit(self, tx: dict[str, Any]) -> tuple[Any, MagicMock]:
        mempool = MagicMock()
        mempool.add = MagicMock(return_value="0xtxhash")
        with patch("aitbc_chain.mempool.get_mempool", return_value=mempool), patch.object(tx_mod, "_queue_peer_fanout"):
            try:
                return await tx_mod.submit_market_transaction(MagicMock(), tx), mempool
            except HTTPException as exc:
                return exc, mempool

    async def test_refuses_a_retired_id_and_queues_nothing(self, retired):
        result, mempool = await self._submit(_signed_market_register(RETIRED))
        assert isinstance(result, HTTPException) and result.status_code == 400
        assert "retired" in result.detail
        mempool.add.assert_not_called()

    async def test_admits_another_id(self, retired):
        result, mempool = await self._submit(_signed_market_register(FRESH))
        assert isinstance(result, dict) and result["success"] is True
        mempool.add.assert_called_once()

    async def test_admits_a_retired_id_when_the_setting_is_unset(self):
        result, mempool = await self._submit(_signed_market_register(RETIRED))
        assert isinstance(result, dict) and result["success"] is True
        mempool.add.assert_called_once()
