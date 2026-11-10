"""Batch v3 item 24: #1301 abandon x vote-journal valve x round-lock release (cc9bb2299).

Pins that releasing locks on an abandon statement cannot deadlock or wedge,
and how it composes with the liveness valve:

* ``VoteJournal.release_abandoned`` holds the journal lock and calls
  ``retract`` which takes it again -- the lock must stay re-entrant (a plain
  ``Lock`` would hang the abandon listener forever);
* concurrent record / release / conflict queries from several threads finish;
* a failing round-lock persist during an abandon never raises or blocks and
  still releases the in-memory locks (stale file is the conservative side);
* abandon is idempotent and composes with an already-open valve;
* after an abandon the rival is admitted by the journal gate WITHOUT waiting
  for the valve; without it (valve closed) the rival is refused.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import abandon, vote_fetch, vote_journal
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.vote_journal import KIND_ATTEST, get_vote_journal, reset_vote_journals
from aitbc_chain.metrics import metrics_registry

CHAIN = "test-chain"
H = 100
HASH = "0x" + "aa" * 32
RIVAL = "0x" + "bb" * 32
JOIN = 10.0


def _addr(key: str) -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(key[2:])).public_key.to_checksum_address()


OUR_KEY, PROP_KEY = "0x" + "11" * 32, "0x" + "22" * 32
OUR, PROP = _addr(OUR_KEY), _addr(PROP_KEY)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    vote_fetch.reset_throttle()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_abandon_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_unlock_seconds", 300.0)
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": OUR}, {"address": PROP}]))

    async def _no_peer(chain_id, height, hashes):
        return None

    monkeypatch.setattr(ra_module, "locate_voted_block", _no_peer)
    yield
    reset_vote_journals()
    metrics_registry.reset()


def _svc() -> RemoteAttestationService:
    return RemoteAttestationService(CHAIN, {OUR: OUR_KEY})


def _stmt(block_hash: str = HASH, height: int = H) -> dict:
    return abandon.build_abandon(CHAIN, height, block_hash, None, PROP, PROP_KEY)


def _run_with_timeout(fn, *args) -> object:
    box: dict[str, object] = {}

    def target() -> None:
        try:
            box["result"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(JOIN)
    assert not t.is_alive(), f"{getattr(fn, '__name__', fn)} did not finish within {JOIN}s (deadlock)"
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box.get("result")


def _vote(block_hash: str = HASH, recorded_ago: float = 0.0) -> None:
    get_vote_journal(CHAIN).record(H, OUR, block_hash, KIND_ATTEST, None, PROP)
    if recorded_ago:
        j = get_vote_journal(CHAIN)
        for rec in j._votes[H][_canon(OUR)]:
            if rec.block_hash == block_hash:
                object.__setattr__(rec, "ts", time.time() - recorded_ago)


def _canon(a: str) -> str:
    from aitbc.crypto.signature_recovery import canonical_address

    return canonical_address(a)


def test_release_abandoned_does_not_deadlock_on_nested_journal_lock():
    _vote()
    journal = get_vote_journal(CHAIN)
    assert _run_with_timeout(journal.release_abandoned, H, OUR, HASH, PROP) is True


def test_handle_abandon_completes_and_releases_everything():
    svc = _svc()
    _vote()
    svc._record_attestation_lock(H, HASH, PROP)
    svc._record_round_lock(H, 1, HASH, PROP)
    assert _run_with_timeout(svc.handle_abandon, _stmt()) == 3  # journal vote + legacy lock + round lock


def test_concurrent_record_release_and_query_finish():
    svc = _svc()
    journal = get_vote_journal(CHAIN)
    errors: list[BaseException] = []

    def hammer(i: int) -> None:
        try:
            for n in range(40):
                h = H + (n % 5)
                block_hash = "0x" + f"{(i * 100 + n):064x}"
                journal.record(h, OUR, block_hash, KIND_ATTEST, None, PROP)
                journal.conflicting(h, OUR, "0x" + "ff" * 32)
                journal.release_abandoned(h, OUR, block_hash, PROP)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(i,), daemon=True) for i in range(4)]
    for t in threads:
        t.start()
    deadline = time.time() + JOIN * 3
    for t in threads:
        t.join(max(0.1, deadline - time.time()))
    assert not any(t.is_alive() for t in threads), "journal threads wedged (deadlock)"
    assert not errors, errors
    del svc


def test_round_lock_persist_failure_never_raises_and_still_releases(monkeypatch):
    svc = _svc()
    svc._record_round_lock(H, 1, HASH, PROP)

    def boom() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(svc, "_persist_round_locks", boom)
    assert _run_with_timeout(svc.handle_abandon, _stmt()) == 1
    assert not svc._round_locks  # released in memory; the stale file is the conservative side


def test_abandon_is_idempotent():
    svc = _svc()
    _vote()
    svc._record_attestation_lock(H, HASH, PROP)
    assert svc.handle_abandon(_stmt()) == 2
    assert svc.handle_abandon(_stmt()) == 0
    assert svc.handle_abandon(_stmt()) == 0


def test_abandon_after_valve_already_opened_is_clean():
    """Valve aged past its window (vote still on file) then abandon: releases it, no error."""
    svc = _svc()
    _vote(recorded_ago=10_000.0)
    assert get_vote_journal(CHAIN).conflicting(H, OUR, RIVAL)  # still a conflict until released
    assert _run_with_timeout(svc.handle_abandon, _stmt()) == 1
    assert get_vote_journal(CHAIN).conflicting(H, OUR, RIVAL) == []


@pytest.mark.asyncio
async def test_rival_refused_while_valve_closed_then_admitted_right_after_abandon():
    svc = _svc()
    _vote()  # fresh vote: valve (300 s) is closed
    refused = await svc._journal_refuses(H, RIVAL, OUR, PROP, None)
    assert refused is True
    assert svc.handle_abandon(_stmt()) == 1
    admitted = await svc._journal_refuses(H, RIVAL, OUR, PROP, None)
    assert admitted is False  # abandon, not the 300 s valve, unlocked the rival


@pytest.mark.asyncio
async def test_abandon_for_a_different_hash_leaves_the_rival_refused():
    svc = _svc()
    _vote()
    assert svc.handle_abandon(_stmt(block_hash=RIVAL)) == 0
    assert await svc._journal_refuses(H, RIVAL, OUR, PROP, None) is True
