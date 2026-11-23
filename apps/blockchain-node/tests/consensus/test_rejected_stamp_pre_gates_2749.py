"""#2749 — proposer stamps must reach the PBFT pre-prepare body.

Under the armed view-change protocol every validator re-seals the committed
block onto ``blocks.<chain>`` with ``block_metadata`` rebuilt from the
persisted pre-prepare body plus the commit certificate. Stamps the proposer
used to add only *after* the gates (``rejected_txs``,
``state_transition_version``) never entered that body, so re-seal payloads
stripped them: followers stored certificate-only metadata, wrote no
``rejected`` rows, and kept apply-rejected txs in their mempools until TTL
(live: ``0xaee9134d…`` zombie on node0/hub1, fleet split-brain tx status).

The deterministic stamps are now seeded into ``metadata_dict`` and
``block.block_metadata`` *before* ``_run_gates_released`` — the gates add
their own keys (certificate, attestations, unlock justification) and the
post-gates dump still lands on the committed block.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus.poa import PoAProposer

CHAIN = "rejected-stamp-fixture"
TX_HASH = "0x" + "a1" * 32


@contextmanager
def _null_session():
    yield None


def _stale_tx() -> SimpleNamespace:
    return SimpleNamespace(
        tx_hash=TX_HASH,
        content={"from": "0x" + "aa" * 20, "to": "0x" + "bb" * 20, "type": "LIQUIDITY_WITHDRAW", "nonce": 189},
        received_at=0.0,
        fee=1,
        size_bytes=1,
    )


@pytest.mark.asyncio
async def test_rejected_and_version_stamps_present_before_gates(monkeypatch):
    config = ProposerConfig(
        chain_id=CHAIN,
        proposer_id="test-node",
        interval_seconds=1,
        max_block_size_bytes=1000,
        max_txs_per_block=100,
    )
    proposer = PoAProposer(config=config, session_factory=_null_session)
    proposer._logger = MagicMock()

    block = SimpleNamespace()
    block.block_metadata = ""

    head = SimpleNamespace()
    head.timestamp = datetime.now(UTC)

    captured: dict = {}

    async def _gates_released(_session, _block, _hash, _proposer, _round, _height, metadata_dict, **_kwargs):
        # The pre-prepare body is built from ``block.block_metadata`` inside
        # the gates — capture exactly what a validator re-seal would inherit.
        captured["block_metadata"] = _block.block_metadata
        captured["metadata_dict"] = dict(metadata_dict)
        # Simulate the gate-time keys the real path adds.
        metadata_dict["pbft_certificate"] = [{"message_type": "commit"}]
        return "ok"

    async def _passes_early_gates(*_args, **_kwargs):
        return SimpleNamespace()

    async def _broadcast(*_args, **_kwargs):
        return True

    monkeypatch.setattr(proposer, "_passes_early_gates", _passes_early_gates)
    monkeypatch.setattr(proposer, "_resolve_proposal_head", lambda *_: (head, 1, b"parent", 1))
    monkeypatch.setattr(proposer, "_select_round_proposer", lambda *_: ("0x" + "0" * 40, 0))
    # 5th element is stale_nonce_txs — seeds rejected_txs before apply.
    monkeypatch.setattr(
        proposer,
        "_collect_proposal_txs",
        lambda *_, **__: ([], {}, {}, set(), [_stale_tx()]),
    )
    monkeypatch.setattr(proposer, "_process_proposal_txs", lambda *_a, **_k: ([], set(), True))
    monkeypatch.setattr(proposer, "_reject_if_all_invalid", lambda *_: False)
    monkeypatch.setattr(proposer, "_assemble_proposal_block", lambda *_: (block, b"fake-block-hash"))
    monkeypatch.setattr(proposer, "_run_gates_released", _gates_released)
    monkeypatch.setattr(proposer, "_sign_block_hash_for", lambda *_: "sig")
    monkeypatch.setattr(proposer, "_commit_and_record_block", lambda *_: None)
    monkeypatch.setattr(proposer, "_broadcast_block", _broadcast)

    result = await proposer._propose_block()

    assert result is True
    assert captured["block_metadata"], "block.block_metadata was empty when the gates ran"
    pre_gate_meta = json.loads(captured["block_metadata"])
    assert "state_transition_version" in pre_gate_meta
    assert pre_gate_meta["rejected_txs"] == [
        {
            "tx_hash": TX_HASH,
            "sender": "0x" + "aa" * 20,
            "nonce": 189,
            "type": "LIQUIDITY_WITHDRAW",
            "reason": "nonce_below_confirmed",
        }
    ]
    # The committed block still carries the gate-time keys on top.
    final_meta = json.loads(block.block_metadata)
    assert final_meta["rejected_txs"] == pre_gate_meta["rejected_txs"]
    assert final_meta["state_transition_version"] == pre_gate_meta["state_transition_version"]
    assert final_meta["pbft_certificate"] == [{"message_type": "commit"}]
