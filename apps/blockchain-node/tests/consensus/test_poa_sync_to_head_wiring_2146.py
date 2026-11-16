"""#2146 — pin the poa.py ``sync_to_head`` wiring (construction, start, slot wait).

#2145 added ``PBFTConsensus.sync_to_head`` and three call sites in
``PoAProposer`` — after PBFT init in ``__init__``, in ``start()``, and in
``_wait_until_next_slot``. The helper itself is pinned by
``test_pbft_state_head_init_2145.py`` but nothing exercised the wiring: a
mutant deleting any call site survived the whole suite. This file injects
a fake ``PBFTConsensus`` at the ``poa`` module seam and asserts the sealed
head height reaches ``sync_to_head`` once per site, in order.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import aitbc_chain.consensus.poa as poa
from aitbc_chain.config import settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA
from aitbc_chain.consensus.poa import PoAProposer, ProposerConfig

CHAIN = "chain-2146"


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    return keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address(), priv


ADDR, KEY = _key("41")


class _FakePBFT:
    """Stands in for ``PBFTConsensus`` — records every ``sync_to_head`` head."""

    instances: list[_FakePBFT] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.heads: list[int] = []
        _FakePBFT.instances.append(self)

    def set_gossip_backend(self, backend: object) -> None:
        pass

    def sync_to_head(self, head_height: int) -> bool:
        self.heads.append(head_height)
        return True


def _config() -> ProposerConfig:
    return ProposerConfig(
        chain_id=CHAIN,
        proposer_id=ADDR,
        interval_seconds=5,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )


@pytest.fixture
def _pbft_wiring(monkeypatch):
    """Arm PBFT + validator keys, fake the consensus class and the head read."""
    _FakePBFT.instances = []
    monkeypatch.setattr(settings, "pbft_consensus_enabled", True)
    monkeypatch.setattr(settings, "validator_keys", json.dumps({ADDR: KEY}))
    monkeypatch.setattr(settings, "validator_set", "")
    monkeypatch.setattr(poa, "PBFTConsensus", _FakePBFT)
    head = {"height": 0}

    def _head(self: PoAProposer):
        return SimpleNamespace(height=head["height"], timestamp=datetime.now(UTC))

    monkeypatch.setattr(PoAProposer, "_fetch_chain_head", _head)
    return head


@pytest.mark.asyncio
async def test_sync_to_head_wired_at_all_three_call_sites(_pbft_wiring):
    head = _pbft_wiring
    head["height"] = 100
    proposer = PoAProposer(
        config=_config(),
        session_factory=lambda: None,  # type: ignore[arg-type,return-value]
        consensus=MultiValidatorPoA(CHAIN),
    )
    pbft = _FakePBFT.instances[-1]
    assert pbft.heads == [100], "construction must sync PBFT to the sealed head"

    # start(): second site — re-reads the head and syncs again.
    head["height"] = 200
    proposer._remote_attestation = None  # listener is out of scope for this pin
    proposer._ensure_genesis_block = lambda: _noop()  # type: ignore[method-assign]
    proposer._run_loop = lambda: proposer._stop_event.wait()  # type: ignore[method-assign]
    await proposer.start()
    try:
        assert pbft.heads == [100, 200], "start() must sync PBFT to the sealed head"

        # _wait_until_next_slot(): third site — syncs the head every slot wait.
        head["height"] = 300
        proposer._stop_event.set()
        await proposer._wait_until_next_slot()
        assert pbft.heads == [100, 200, 300], "slot wait must sync PBFT to the sealed head"
    finally:
        await proposer.stop()


async def _noop() -> None:
    return None
