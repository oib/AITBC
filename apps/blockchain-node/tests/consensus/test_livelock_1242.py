"""#1242 livelock regression pin: single-validator loss + round-robin churn.

The R13-01 drill (#1242 issue body) showed the height-keyed attestation lock
livelocking block production: with one validator down, the two survivors
alternate proposer rounds at the same height; every round derives a fresh
timestamp → fresh block hash → the peer's live height-only lock refuses the
new hash → the round fails → the NEXT round locks another fresh hash →
repeat. Sandbox recovery needed a service restart (in-memory ``_attested``
cleared); self-recovery was unproven.

The #1242 fix keys the lock to ``(height, round)`` and unlocks a later round
via U1 (strictly later round) + U2 (the locked round's failure is evidenced:
a subsequent-round request seen AND the locked round's full gates window
elapsed — or the monotonic window fallback). This pin exercises exactly the
drill choreography against the flag-on path: successive rounds at one height,
each a different hash, each first refused while the previous round's failure
is unproven, then signed once the gates window is simulated as elapsed —
recovery WITHOUT restart, bounded per round, while same-round fork rivals
stay refused.

Scope note: this pins the attester-side mechanism that starved quorum. The
proposer-side mirror (``_honor_attestation_lock``) is covered by
``TestProposerMirror`` in ``test_round_lock.py``; full multi-validator quorum
assembly is out of scope for a unit pin. ``ATTESTATION_ROUND_LOCK_ENABLED``
stays OFF in prod pending the soak clock — this pins the engineered fix, not
the currently-deployed legacy path (whose worst case is precisely the
livelock this file reproduces the absence of).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry

PARENT_TS = datetime(2026, 1, 1, tzinfo=UTC)
ROUND_SECONDS = 60
UNLOCK_WINDOW = 16.0
HEIGHT = 100
CHURN_ROUNDS = 4


@pytest.fixture(autouse=True)
def _round_lock_on(monkeypatch):
    """Same flag set as test_round_lock.py — the #1242 fix path under test."""
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", True)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", ROUND_SECONDS)
    monkeypatch.setattr(settings, "attestation_round_unlock_window_seconds", UNLOCK_WINDOW)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 3600.0)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_enforce_proposer_schedule", False)
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _addr(seed: str) -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(seed * 32)).public_key.to_checksum_address()


def _keys() -> tuple[str, str, str, str]:
    """(our_addr, our_key, prop_a_addr, prop_b_addr).

    Three configured validators model the drill's 3-validator set with one
    lost: our attester plus two peers that alternate proposer rounds. The
    requests are unsigned (fixture pins pre-arming behaviour), so only
    addresses are needed for the proposers.
    """
    return _addr("11"), "0x" + "11" * 32, _addr("22"), _addr("33")


def _block_ts(round_: int) -> datetime:
    return PARENT_TS + timedelta(seconds=round_ * ROUND_SECONDS + 1)


def _header(height: int, block_hash: str, proposer: str, round_: int) -> dict:
    return {
        "header": {
            "chain_id": "test-chain",
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "timestamp": _block_ts(round_).isoformat(),
            "round": round_,
        },
        "timestamp": time.time(),
    }


class _StubBroker:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict):
        self.published.append((topic, message))


def _service(
    monkeypatch,
    our_addr: str,
    our_key: str,
    validator_addrs: list[str],
    tmp_path,
) -> tuple[RemoteAttestationService, _StubBroker]:
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": a} for a in validator_addrs]))
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService("test-chain", {our_addr: our_key})
    svc._round_locks_path = tmp_path / "locks.json"
    svc._local_head = lambda: (HEIGHT - 1, "0xparent")  # type: ignore[method-assign]
    svc._canonical_hash_at = lambda h: {HEIGHT - 1: "0xparent", HEIGHT: "0xchurn00"}.get(h)  # type: ignore[method-assign]
    svc._parent_timestamp = lambda p: PARENT_TS if p == "0xparent" else None  # type: ignore[method-assign]
    return svc, broker


def _attestation_responses(broker: _StubBroker) -> list[dict]:
    return [msg for topic, msg in broker.published if "attest" in topic]


class TestSingleValidatorLossChurn:
    """The #1242 livelock choreography, replayed at attester level."""

    @pytest.mark.asyncio
    async def test_round_robin_hash_churn_recovers_without_restart(self, monkeypatch, tmp_path):
        our_addr, our_key, prop_a_addr, prop_b_addr = _keys()
        # 3-validator set; the third slot models the lost validator — it is
        # configured but never sends a request, signature, or lock.
        svc, broker = _service(monkeypatch, our_addr, our_key, [our_addr, prop_a_addr, prop_b_addr], tmp_path)
        proposers = [prop_a_addr, prop_b_addr]

        for r in range(CHURN_ROUNDS):
            block_hash = f"0xchurn{r:02d}"
            proposer = proposers[r % 2]
            request = _header(HEIGHT, block_hash, proposer, r)
            before = len(broker.published)

            # Round 0 has no prior lock — it signs on first contact.
            await svc._handle_request(request)
            if r == 0:
                assert len(broker.published) == before + 1
                continue

            # 1) The fresh later-round request arrives while the previous
            #    round's lock is still inside its gates window → refused.
            #    This is the livelock pressure: every round's new hash
            #    arrives before the prior round's failure is provable.
            assert len(broker.published) == before, f"round {r} signed before the prior round's failure was provable"

            # 2) The round fails — simulate the gates window elapsing by
            #    ageing every locked entry's request_seen_at past
            #    attestation_round_unlock_window_seconds (the protocol U2
            #    route; the monotonic fallback is covered separately in
            #    test_round_lock.py).
            aged = time.monotonic() - (UNLOCK_WINDOW + 4.0)
            for entry in svc._round_locks.values():
                entry.request_seen_at = aged

            # 3) The SAME request now satisfies U1+U2 → signs. No restart,
            #    no new lock semantics — bounded recovery per round.
            await svc._handle_request(request)
            assert len(broker.published) == before + 1, f"round {r} did not recover after gates window"
            signed = _attestation_responses(broker)
            assert signed, "no attestation response published"
            assert signed[-1].get("round") == r

        # Every churn round is durably locked — the anti-equivocation record
        # accumulated one entry per (height, round), none overwritten.
        assert set(svc._round_locks) == {(HEIGHT, r) for r in range(CHURN_ROUNDS)}

        # Fork protection intact: a same-round RIVAL at the last round is
        # still refused (U1 fails — never sign backwards or sideways).
        before = len(broker.published)
        await svc._handle_request(_header(HEIGHT, "0xrival99", proposers[-1], CHURN_ROUNDS - 1))
        assert len(broker.published) == before

    @pytest.mark.asyncio
    async def test_churn_locks_do_not_block_a_still_later_round(self, monkeypatch, tmp_path):
        """After churn recovery, an even-later round unlocks the same way —
        the lock set grows but never wedges the height (no livelock)."""
        our_addr, our_key, prop_a_addr, prop_b_addr = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, [our_addr, prop_a_addr, prop_b_addr], tmp_path)
        proposers = [prop_a_addr, prop_b_addr]

        for r in range(CHURN_ROUNDS):
            request = _header(HEIGHT, f"0xchurn{r:02d}", proposers[r % 2], r)
            before = len(broker.published)
            await svc._handle_request(request)
            if r == 0:
                assert len(broker.published) == before + 1
                continue
            # Same refuse-then-recover discipline as the churn test: the
            # fresh request is refused while the prior lock is inside its
            # gates window, then signs once the window is simulated elapsed.
            assert len(broker.published) == before
            aged = time.monotonic() - (UNLOCK_WINDOW + 4.0)
            for entry in svc._round_locks.values():
                entry.request_seen_at = aged
            await svc._handle_request(request)
            assert len(broker.published) == before + 1

        # Round CHURN_ROUNDS (one past the churn) — every prior entry must
        # satisfy U2; they do, so the height keeps advancing.
        before = len(broker.published)
        request = _header(HEIGHT, "0xchurnnext", proposers[0], CHURN_ROUNDS)
        await svc._handle_request(request)
        assert len(broker.published) == before  # fresh prior lock → refused first
        aged = time.monotonic() - (UNLOCK_WINDOW + 4.0)
        for entry in svc._round_locks.values():
            entry.request_seen_at = aged
        await svc._handle_request(request)
        assert len(broker.published) == before + 1
        signed = _attestation_responses(broker)
        assert signed[-1].get("round") == CHURN_ROUNDS
