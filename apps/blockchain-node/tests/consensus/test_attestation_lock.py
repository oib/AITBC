"""Attester lock (v0.25.x).

A validator that signs (attests) a peer's block X at height h must not
propose — or re-attest — a different block at h for one proposer round.
While the lock is live the proposer path tries to fetch X from a mesh peer
and pull it; if no peer serves it the proposal is suppressed until the lock
expires, which bounds the liveness hit. This closes the equivocation that
turned the 2026-09-27 asymmetric partitions into same-height forks: hub1
attested node2's block, never received it, then proposed a rival.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _keys() -> tuple[str, str, str, str]:
    """(our_addr, our_key, proposer_addr, proposer_key) — distinct test keys."""
    from eth_keys import keys

    our_key = "0x" + "11" * 32
    proposer_key = "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr, proposer_key


def _header(height: int, block_hash: str, proposer: str, chain_id: str = "test-chain") -> dict:
    return {
        "header": {
            "chain_id": chain_id,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
        },
        "timestamp": time.time(),
    }


class _StubBroker:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict):
        self.published.append((topic, message))


def _service(monkeypatch, our_addr: str, our_key: str, proposer_addr: str) -> tuple[RemoteAttestationService, _StubBroker]:
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
    )
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService("test-chain", {our_addr: our_key})
    return svc, broker


class TestAttesterLockRecord:
    async def test_signing_a_peer_header_records_the_lock(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))

        assert broker.published, "attestation response should have been published"
        lock = svc.attestation_lock(100, 60.0)
        assert lock is not None
        assert lock[0] == "0xaaaa"
        assert lock[1] == proposer_addr

    async def test_own_proposal_does_not_lock(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        # Proposer field equals our own key — we never attest our own block.
        await svc._handle_request(_header(100, "0xaaaa", our_addr))

        assert not broker.published
        assert svc.attestation_lock(100, 60.0) is None

    async def test_rival_header_at_locked_height_is_refused(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert len(broker.published) == 1

        # A rival block at the same height must not collect our signature.
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr))
        assert len(broker.published) == 1
        assert svc.attestation_lock(100, 60.0)[0] == "0xaaaa"

    async def test_same_height_same_hash_re_signs(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert len(broker.published) == 2  # idempotent re-sign is allowed

    async def test_rival_signs_after_lock_expiry(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        # Backdate the lock past the window.
        svc._attested[100] = ("0xaaaa", proposer_addr, time.monotonic() - 3600)

        await svc._handle_request(_header(100, "0xbbbb", proposer_addr))
        assert len(broker.published) == 2
        assert svc.attestation_lock(100, 60.0)[0] == "0xbbbb"

    def test_lock_accessor_expires_entries(self):
        svc = RemoteAttestationService("test-chain", {})
        svc._attested[5] = ("0xaaaa", "0xPROP", time.monotonic() - 3600)
        assert svc.attestation_lock(5, 60.0) is None
        assert 5 not in svc._attested

    async def test_lock_disabled_flag_restores_double_sign(self, monkeypatch):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr)
        monkeypatch.setattr(settings, "attestation_lock_enabled", False)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr))
        assert len(broker.published) == 2  # legacy behaviour: signed both


class TestProposalSuppression:
    def _proposer(self, locked: tuple[str, str] | None) -> tuple[PoAProposer, Mock]:
        sm = Mock()
        sm.pull_from_peer.return_value = True
        sm.pull_in_flight.return_value = False
        config = ProposerConfig(
            chain_id="test-chain",
            proposer_id="test-proposer",
            interval_seconds=1.0,
            max_txs_per_block=10,
            max_block_size_bytes=1_000_000,
        )
        proposer = PoAProposer(config=config, session_factory=lambda: Mock(), sync_manager=sm)
        attestation = SimpleNamespace(attestation_lock=lambda h, w: locked if h == 100 else None)
        proposer._remote_attestation = attestation  # type: ignore[attr-defined]
        return proposer, sm

    async def test_locked_height_fetches_block_and_pulls(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)

        get = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"height": 100, "hash": "0xaaaa"}))
        monkeypatch.setattr(poa_module.SharedHttpClient, "get", get)

        assert await proposer._honor_attestation_lock(100) is True
        sm.pull_from_peer.assert_called_once_with("test-chain", "https://peer1.example")
        assert get.await_count == 1

    async def test_locked_height_without_serving_peer_still_suppresses(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)

        get = AsyncMock(return_value=SimpleNamespace(status_code=404, json=lambda: {}))
        monkeypatch.setattr(poa_module.SharedHttpClient, "get", get)

        assert await proposer._honor_attestation_lock(100) is True
        sm.pull_from_peer.assert_not_called()

    async def test_peer_serving_different_hash_does_not_pull(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "wss://peer1.example/rpc/gossip/ws")
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)

        get = AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: {"height": 100, "hash": "0xbbbb"}))
        monkeypatch.setattr(poa_module.SharedHttpClient, "get", get)

        assert await proposer._honor_attestation_lock(100) is True
        sm.pull_from_peer.assert_not_called()

    async def test_no_lock_proceeds(self, monkeypatch):
        proposer, sm = self._proposer(None)
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)
        assert await proposer._honor_attestation_lock(100) is False
        sm.pull_from_peer.assert_not_called()

    async def test_disabled_flag_proceeds(self, monkeypatch):
        proposer, sm = self._proposer(("0xaaaa", "0xPROP"))
        monkeypatch.setattr(settings, "attestation_lock_enabled", False)
        assert await proposer._honor_attestation_lock(100) is False
        sm.pull_from_peer.assert_not_called()

    async def test_no_attestation_service_proceeds(self, monkeypatch):
        proposer, sm = self._proposer(None)
        proposer._remote_attestation = None
        monkeypatch.setattr(settings, "attestation_lock_enabled", True)
        assert await proposer._honor_attestation_lock(100) is False
