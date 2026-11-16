"""#2145 — PBFT state must start at the sealed chain head, not at 0.

``current_sequence`` is the base of the intake window (``+ pbft_max_sequence_ahead``)
and only ``execute_phase`` raised it. Armed on a chain that already had blocks, every
real-height vote sat past the window and was silently dropped, so PBFT could never
commit the first block that would have moved the window.
"""

from __future__ import annotations

import asyncio
import hashlib

from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import PBFTConsensus
from aitbc_chain.consensus.pbft_vote_signature import pbft_vote_preimage

CHAIN = "chain-2145"
BH = "0x" + "ab" * 32
HEAD = 5000


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    return keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address(), priv


ADDR, KEY = _key("31")
ADDR2, KEY2 = _key("32")
ADDR3, KEY3 = _key("33")
MEMBERS = [ADDR, ADDR2, ADDR3]


def _pbft() -> PBFTConsensus:
    consensus = MultiValidatorPoA(CHAIN)
    for addr in MEMBERS:
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return PBFTConsensus(consensus, chain_id=CHAIN, local_validator="")


def _prepare(seq: int, view: int = 0) -> dict:
    rec = {
        "message_type": "prepare",
        "sender": ADDR2,
        "view_number": view,
        "sequence_number": seq,
        "digest": hashlib.sha256(f"{BH}:{seq}:{view}".encode()).hexdigest(),
        "block_hash": BH,
    }
    return {**rec, "signature": sign_consensus_message(pbft_vote_preimage(rec, CHAIN), KEY2), "timestamp": 0.0}


def _counted(pbft: PBFTConsensus, seq: int, view: int = 0) -> bool:
    return bool(pbft.state.prepared_messages.get(f"{seq}:{view}"))


def test_fresh_engine_on_existing_chain_drops_real_height_votes():
    """The stall itself: the window is [0, 512], so a head+1 vote never lands."""
    pbft = _pbft()
    asyncio.run(pbft.handle_incoming_message(_prepare(HEAD + 1)))
    assert not _counted(pbft, HEAD + 1)


def test_sync_to_head_makes_real_height_votes_count():
    pbft = _pbft()
    assert pbft.sync_to_head(HEAD) is True
    assert pbft.state.current_sequence == HEAD
    asyncio.run(pbft.handle_incoming_message(_prepare(HEAD + 1)))
    assert _counted(pbft, HEAD + 1)


def test_sync_to_head_is_monotonic():
    pbft = _pbft()
    pbft.sync_to_head(HEAD)
    assert pbft.sync_to_head(HEAD - 100) is False  # reorg-low / stale head
    assert pbft.sync_to_head(HEAD) is False
    assert pbft.state.current_sequence == HEAD


def test_first_block_after_genesis_is_a_noop():
    pbft = _pbft()
    assert pbft.sync_to_head(0) is False
    assert pbft.state.current_sequence == 0
    asyncio.run(pbft.handle_incoming_message(_prepare(1)))
    assert _counted(pbft, 1)


def test_sync_prunes_only_below_the_new_base_and_keeps_view():
    pbft = _pbft()
    asyncio.run(pbft.handle_incoming_message(_prepare(3)))
    asyncio.run(pbft.handle_incoming_message(_prepare(40)))
    pbft.state.current_view = 4
    pbft.sync_to_head(10)
    assert not _counted(pbft, 3, 0)
    assert _counted(pbft, 40, 0)
    assert pbft.state.current_view == 4  # the proposer round is not a height


def test_garbage_head_never_raises():
    pbft = _pbft()
    assert pbft.sync_to_head("nope") is False  # type: ignore[arg-type]
    assert pbft.sync_to_head(None) is False  # type: ignore[arg-type]
    assert pbft.state.current_sequence == 0


def test_proposer_helper_syncs_engine_from_the_head_and_swallows_read_errors():
    from types import SimpleNamespace

    from aitbc_chain.consensus.poa import PoAProposer

    pbft = _pbft()

    def _boom():
        raise RuntimeError("db down")

    owner = SimpleNamespace(
        _pbft_consensus=pbft,
        _fetch_chain_head=lambda: SimpleNamespace(height=HEAD),
        _logger=SimpleNamespace(warning=lambda *a, **k: None),
    )
    PoAProposer._sync_pbft_to_head(owner)  # type: ignore[arg-type]
    assert pbft.state.current_sequence == HEAD

    owner._fetch_chain_head = _boom
    PoAProposer._sync_pbft_to_head(owner)  # type: ignore[arg-type]
    assert pbft.state.current_sequence == HEAD

    owner._pbft_consensus = None  # PBFT off: nothing to do
    PoAProposer._sync_pbft_to_head(owner)  # type: ignore[arg-type]


# --- #2157: the same silent window, on the view axis ------------------------


def test_restarted_engine_drops_votes_from_a_round_past_the_view_window():
    """The second stall layer: views climb with the clock while the window restarts at 0."""
    pbft = _pbft()
    pbft.sync_to_head(HEAD)
    asyncio.run(pbft.handle_incoming_message(_prepare(HEAD + 1, view=95)))
    assert not _counted(pbft, HEAD + 1, 95)


def test_sync_view_reopens_the_window_for_the_networks_round():
    pbft = _pbft()
    pbft.sync_to_head(HEAD)
    assert pbft.sync_view(95) is True
    assert pbft.state.current_view == 95
    asyncio.run(pbft.handle_incoming_message(_prepare(HEAD + 1, view=95)))
    assert _counted(pbft, HEAD + 1, 95)


def test_sync_view_is_monotonic_and_rejects_garbage():
    pbft = _pbft()
    assert pbft.sync_view(10) is True
    assert pbft.sync_view(10) is False
    assert pbft.sync_view(3) is False
    assert pbft.sync_view("9") is False  # type: ignore[arg-type]
    assert pbft.sync_view(True) is False  # type: ignore[arg-type]
    assert pbft.state.current_view == 10


def test_proposer_helper_seeds_the_view_from_the_head_timestamp():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from aitbc_chain.consensus.poa import PoAProposer

    pbft = _pbft()
    head_ts = datetime.now(UTC) - timedelta(seconds=600)
    owner = SimpleNamespace(
        _pbft_consensus=pbft,
        _fetch_chain_head=lambda: SimpleNamespace(height=HEAD, timestamp=head_ts),
        _proposer_round=lambda parent, now: int((now - parent).total_seconds() // 60),
        _logger=SimpleNamespace(warning=lambda *a, **k: None),
    )
    PoAProposer._sync_pbft_to_head(owner)  # type: ignore[arg-type]
    assert pbft.state.current_view == 10
