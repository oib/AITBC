"""Batch v3 item 17: attestation-lock property test.

Random (height, hash, clock-advance) request sequences are replayed through
``RemoteAttestationService._handle_request`` against an independent oracle of
the lock rules, with a controllable monotonic clock. Properties:

* the service publishes exactly when the oracle says it may (lock live and
  rival -> refused; lapsed and already signed -> refused; else signed);
* NO DUAL SIGN WITHOUT EVIDENCE: whenever a signature for hash B is published
  at a height where a different hash A was already signed, (a) the earlier
  lock had lapsed (never inside the window) and (b) an equivocation evidence
  record pairing A with B was handed to the recorder;
* a replayed (height, hash) never extends or re-arms a live lock.
"""

from __future__ import annotations

import json
import random
import time

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry


def _keys() -> tuple[str, str, str, str]:
    from eth_keys import keys

    our_key, proposer_key = "0x" + "11" * 32, "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr, proposer_key


def _header(height: int, block_hash: str, proposer: str) -> dict:
    return {
        "header": {
            "chain_id": "test-chain",
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
        },
        "timestamp": time.time(),
    }


WINDOW = 60.0
HEIGHTS = (100, 101, 102)
HASHES = ("0xa1", "0xb2", "0xc3", "0xd4")
STEPS = (0.0, 0.0, 1.0, 30.0, 59.0, 61.0, 3600.0)


class _Clock:
    def __init__(self) -> None:
        self.now = 10_000.0

    def __call__(self) -> float:
        return self.now


class _Broker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict) -> None:
        self.published.append((topic, message))


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, str]] = []

    def record_attestation_equivocation(self, **kw) -> None:
        self.calls.append((kw["height"], kw["block_hash_a"], kw["block_hash_b"]))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    monkeypatch.setattr(settings, "chain_id", "test-chain")
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", int(WINDOW))
    monkeypatch.setattr(settings, "consensus_domain_separation_height", None, raising=False)
    metrics_registry.reset()
    yield
    metrics_registry.reset()


class _Oracle:
    """Independent model of the lock rules (domain-less, pre-activation window)."""

    def __init__(self) -> None:
        self.lock: dict[int, tuple[str, float]] = {}
        self.signed_once: dict[int, set[str]] = {}

    def decide(self, height: int, h: str, now: float) -> bool:
        lock = self.lock.get(height)
        live = lock is not None and now - lock[1] < WINDOW
        if live and lock[0] != h:
            return False
        if not live and h in self.signed_once.get(height, set()):
            return False
        if h not in self.signed_once.get(height, set()):
            self.lock[height] = (h, now)
            self.signed_once.setdefault(height, set()).add(h)
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(40))
async def test_lock_sequences_match_oracle_and_leave_evidence(monkeypatch, seed):
    our_addr, our_key, proposer_addr, _ = _keys()
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": our_addr}, {"address": proposer_addr}]))
    broker = _Broker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    clock = _Clock()
    monkeypatch.setattr(ra_module.time, "monotonic", clock)
    svc = RemoteAttestationService("test-chain", {our_addr: our_key})
    rec = _Recorder()
    monkeypatch.setattr(svc, "_equivocation_recorder", lambda: rec)

    rng = random.Random(seed)
    oracle = _Oracle()
    signed_at: dict[int, list[tuple[str, float]]] = {}
    for _ in range(30):
        clock.now += rng.choice(STEPS)
        height, h = rng.choice(HEIGHTS), rng.choice(HASHES)
        before = len(broker.published)
        calls_before = len(rec.calls)
        lock_before = oracle.lock.get(height)
        expected = oracle.decide(height, h, clock.now)
        await svc._handle_request(_header(height, h, proposer_addr))
        published = len(broker.published) > before
        assert published == expected, (seed, height, h, clock.now)
        if not published:
            assert len(rec.calls) == calls_before  # refusal records nothing
            continue
        prior = signed_at.setdefault(height, [])
        rivals = {p for p, _t in prior if p != h}
        if rivals and h not in {p for p, _t in prior}:  # a first signing of h next to an earlier rival
            # dual sign: only legal after the lock lapsed, and only with evidence
            assert lock_before is None or clock.now - lock_before[1] >= WINDOW, ("dual sign inside live lock", seed, height, h)
            recorded = {(a, b) for (ht, a, b) in rec.calls[calls_before:] if ht == height}
            for r in rivals:
                assert (r, h) in recorded or (h, r) in recorded, ("dual sign without evidence", seed, height, r, h)
        prior.append((h, clock.now))


@pytest.mark.asyncio
async def test_replay_never_extends_live_lock(monkeypatch):
    our_addr, our_key, proposer_addr, _ = _keys()
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": our_addr}, {"address": proposer_addr}]))
    monkeypatch.setattr(ra_module, "gossip_broker", _Broker())
    clock = _Clock()
    monkeypatch.setattr(ra_module.time, "monotonic", clock)
    svc = RemoteAttestationService("test-chain", {our_addr: our_key})
    await svc._handle_request(_header(100, "0xa1", proposer_addr))
    t0 = clock.now
    for _ in range(10):
        clock.now += 5.0
        await svc._handle_request(_header(100, "0xa1", proposer_addr))
    assert svc.attestation_lock(100, WINDOW) is not None
    clock.now = t0 + WINDOW + 1
    assert svc.attestation_lock(100, WINDOW) is None  # replays did not re-arm it
