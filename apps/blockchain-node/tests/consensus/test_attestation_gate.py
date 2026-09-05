"""The attestation gate in poa.py: what satisfies it, and who answers it.

Two defects are pinned here, both of which stalled a four-validator fleet even
though PBFT reached quorum on every round:

1. The remote attestation listener was started *after* the
   ``enable_block_production`` early return, so validators that do not produce
   blocks never answered attestation requests. On a fleet where two of four
   validators produce blocks, a proposer could collect exactly one attestation
   against ``MULTI_VALIDATOR_MIN_ATTESTATIONS=2``.
2. The gate rejected the proposer's own block for missing attestations even
   when it held a PBFT commit certificate -- which is precisely what
   ``sync_validator._validate_attestations`` checks *instead of* the
   attestations list. The proposer was stricter than every verifier.
"""

from typing import Any

import pytest

from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus.poa import PoAProposer


def _proposer() -> PoAProposer:
    config = ProposerConfig(
        chain_id="test-attestation-chain",
        proposer_id="0x" + "a" * 40,
        interval_seconds=5,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )
    return PoAProposer(config=config, session_factory=lambda: None)  # type: ignore[arg-type,return-value]


def _commit(sender: str, block_hash: str) -> dict[str, Any]:
    return {
        "message_type": "commit",
        "sender": sender,
        "view_number": 0,
        "sequence_number": 1,
        "digest": "deadbeef",
        "signature": "0x00",
        "block_hash": block_hash,
    }


class _FakeAttestationService:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


# --- certificate counting -------------------------------------------------


def test_certificate_commit_count_counts_distinct_senders() -> None:
    certificate = [_commit(f"0x{i:040x}", "0xblock") for i in range(3)]
    assert PoAProposer._certificate_commit_count(certificate, "0xblock") == 3


def test_certificate_commit_count_is_case_insensitive_on_sender() -> None:
    """Two spellings of one validator are one commit, not two."""
    addr = "0x" + "AB" * 20
    certificate = [_commit(addr, "0xblock"), _commit(addr.lower(), "0xblock")]
    assert PoAProposer._certificate_commit_count(certificate, "0xblock") == 1


def test_certificate_commit_count_ignores_other_blocks() -> None:
    certificate = [
        _commit("0x" + "1" * 40, "0xblock"),
        _commit("0x" + "2" * 40, "0xotherblock"),
    ]
    assert PoAProposer._certificate_commit_count(certificate, "0xblock") == 1


def test_certificate_commit_count_ignores_non_commit_messages() -> None:
    prepare = _commit("0x" + "1" * 40, "0xblock")
    prepare["message_type"] = "prepare"
    certificate = [prepare, _commit("0x" + "2" * 40, "0xblock")]
    assert PoAProposer._certificate_commit_count(certificate, "0xblock") == 1


def test_certificate_commit_count_ignores_malformed_entries() -> None:
    no_sender = _commit("", "0xblock")
    certificate: list[Any] = ["not-a-dict", no_sender, _commit("0x" + "3" * 40, "0xblock")]
    assert PoAProposer._certificate_commit_count(certificate, "0xblock") == 1


def test_certificate_commit_count_empty_certificate() -> None:
    assert PoAProposer._certificate_commit_count([], "0xblock") == 0


def test_certificate_commit_count_matches_sync_validator_counting() -> None:
    """A commit with no block_hash field is bound to the block being validated.

    ``sync_validator._validate_pbft_certificate`` treats a missing
    ``block_hash`` as "this block" rather than skipping the commit; the proposer
    must count it the same way or it will reject blocks followers accept.
    """
    commit = _commit("0x" + "4" * 40, "0xblock")
    del commit["block_hash"]
    assert PoAProposer._certificate_commit_count([commit], "0xblock") == 1


# --- listener lifecycle ---------------------------------------------------


@pytest.mark.asyncio
async def test_attestation_listener_starts_without_block_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """A validator that produces no blocks still has to sign other proposers' headers."""
    from aitbc_chain.consensus import poa as poa_module

    monkeypatch.setattr(poa_module.settings, "enable_block_production", False, raising=False)
    monkeypatch.setattr(poa_module.settings, "multi_validator_consensus_enabled", True, raising=False)

    proposer = _proposer()
    fake = _FakeAttestationService()
    proposer._remote_attestation = fake  # type: ignore[assignment]

    await proposer.start()

    assert fake.started, "attestation listener must start even with block production disabled"
    assert proposer._task is None, "the proposer loop itself must stay off"


@pytest.mark.asyncio
async def test_attestation_listener_stops_without_proposer_task() -> None:
    """stop() used to return early when no loop was running, leaking the subscription."""
    proposer = _proposer()
    fake = _FakeAttestationService()
    proposer._remote_attestation = fake  # type: ignore[assignment]

    assert proposer._task is None
    await proposer.stop()

    assert fake.stopped, "attestation listener must be stopped even when no proposer loop ran"


@pytest.mark.asyncio
async def test_stop_is_safe_without_attestation_service() -> None:
    proposer = _proposer()
    assert proposer._remote_attestation is None
    await proposer.stop()
