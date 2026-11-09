"""#1301 L2: proposer-signed abandon releases the voters' journal entry.

Flag off is inert; a valid abandon from the voted hash's proposer releases
exactly that entry; forged / wrong-proposer / wrong-hash / wrong-chain /
decided-height statements release nothing.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import abandon, vote_fetch, vote_journal
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.vote_journal import KIND_ATTEST, get_vote_journal, reset_vote_journals
from aitbc_chain.metrics import metrics_registry

CHAIN = "test-chain"
H = 100
HASH = "0x" + "aa" * 32
OTHER = "0x" + "bb" * 32


def _addr(key: str) -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(key[2:])).public_key.to_checksum_address()


OUR_KEY, PROP_KEY, EVIL_KEY = "0x" + "11" * 32, "0x" + "22" * 32, "0x" + "33" * 32
OUR, PROP, EVIL = _addr(OUR_KEY), _addr(PROP_KEY), _addr(EVIL_KEY)


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    vote_fetch.reset_throttle()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", True)
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": OUR}, {"address": PROP}]))
    yield
    reset_vote_journals()
    metrics_registry.reset()


def _svc() -> RemoteAttestationService:
    return RemoteAttestationService(CHAIN, {OUR: OUR_KEY})


def _vote(proposer: str = PROP, block_hash: str = HASH, height: int = H) -> None:
    get_vote_journal(CHAIN).record(height, OUR, block_hash, KIND_ATTEST, None, proposer)


def _live(block_hash: str = HASH, height: int = H) -> bool:
    return any(v.block_hash == block_hash for v in get_vote_journal(CHAIN).votes_at(height, OUR))


def _stmt(key: str = PROP_KEY, proposer: str = PROP, block_hash: str = HASH, height: int = H, chain: str = CHAIN) -> dict:
    return abandon.build_abandon(chain, height, block_hash, None, proposer, key)


def test_valid_abandon_releases_exactly_the_voted_hash():
    _vote()
    _vote(block_hash=OTHER, height=H + 1)
    assert _svc().handle_abandon(_stmt()) == 1
    assert not _live()
    assert _live(OTHER, H + 1)
    assert _counter("vote_journal_abandon_released_total") == 1


def test_flag_off_is_inert(monkeypatch):
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", False)
    assert abandon.abandon_enabled() is False
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_enabled", False)
    assert abandon.abandon_enabled() is False


def test_forged_signature_is_rejected():
    _vote()
    stmt = _stmt(key=EVIL_KEY)  # signed by someone else but claims PROP
    assert _svc().handle_abandon(stmt) == 0
    assert _live()
    assert _counter("vote_journal_abandon_rejected_total") == 1


def test_non_proposer_cannot_abandon_anothers_hash():
    _vote(proposer=PROP)
    # EVIL signs a valid statement under its own address for the same hash.
    assert _svc().handle_abandon(_stmt(key=EVIL_KEY, proposer=EVIL)) == 0
    assert _live()


def test_wrong_hash_and_wrong_chain_release_nothing():
    _vote()
    assert _svc().handle_abandon(_stmt(block_hash=OTHER)) == 0
    assert _svc().handle_abandon(_stmt(chain="other-chain")) == 0
    assert _live()


def test_tampered_fields_invalidate_signature():
    _vote()
    stmt = _stmt()
    stmt["hash"] = OTHER
    assert _svc().handle_abandon(stmt) == 0
    assert _live()


def test_decided_height_is_left_to_pruning():
    _vote()
    svc = _svc()
    svc._tip_height_hint = H
    assert svc.handle_abandon(_stmt()) == 0
    assert _live()


@pytest.mark.parametrize("junk", [None, "x", {}, {"kind": "abandon"}, {"kind": "abandon", "chain_id": CHAIN}])
def test_malformed_payloads_are_rejected(junk):
    _vote()
    assert _svc().handle_abandon(junk) == 0
    assert _live()


@pytest.mark.asyncio
async def test_proposer_publishes_abandon_on_quorum_miss(monkeypatch):
    from aitbc_chain.consensus import poa as poa_module

    published: list[tuple[str, dict]] = []

    class _Broker:
        async def publish(self, topic, msg):
            published.append((topic, msg))

    monkeypatch.setattr(poa_module, "gossip_broker", _Broker())
    prop = SimpleNamespace(
        _config=SimpleNamespace(chain_id=CHAIN),
        _validator_keys={PROP: PROP_KEY},
        _logger=SimpleNamespace(warning=lambda *a, **k: None),
    )
    block = SimpleNamespace(proposer=PROP, height=H)
    await PoAProposer._publish_abandon(prop, block, HASH)
    assert len(published) == 1
    topic, msg = published[0]
    assert topic == abandon.abandon_topic(CHAIN)
    assert abandon.verify_abandon(CHAIN, msg) is not None
    assert _counter("vote_journal_abandon_published_total") == 1


@pytest.mark.asyncio
async def test_no_publish_when_flag_off(monkeypatch):
    from aitbc_chain.consensus import poa as poa_module

    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", False)
    broker = SimpleNamespace(publish=AsyncMock())
    monkeypatch.setattr(poa_module, "gossip_broker", broker)
    prop = SimpleNamespace(_config=SimpleNamespace(chain_id=CHAIN), _validator_keys={PROP: PROP_KEY}, _logger=None)
    await PoAProposer._publish_abandon(prop, SimpleNamespace(proposer=PROP, height=H), HASH)
    broker.publish.assert_not_awaited()


def test_own_proposal_entry_is_not_released_self_lock():
    from aitbc_chain.consensus.vote_journal import KIND_PROPOSE

    get_vote_journal(CHAIN).record(H, OUR, HASH, KIND_PROPOSE, None, OUR)
    assert _svc().handle_abandon(_stmt(key=OUR_KEY, proposer=OUR)) == 0
    assert _live()
