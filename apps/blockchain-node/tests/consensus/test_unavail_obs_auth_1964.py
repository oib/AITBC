"""#1964 — GossipObservationIndex pre-arming hardening.

F1: the ``attest_response`` feed trusted a string ``validator`` claim. It now
feeds the index only when the signature verifies, for that validator, against
the attestation payload of the verified request the index holds — so forged
responses can neither inflate ``mesh_visible`` nor create entries.
F2: ``.clear()`` eviction wiped all quiet-window evidence at 512 keys. It now
evicts stale-then-lowest-height entries and refuses newcomers rather than
dropping in-window evidence.
F3: heights far from the local tip are not recorded.
All of it sits behind ``unavail.justification_enabled()`` (dormant).
"""

from __future__ import annotations

import json

import pytest
from aitbc.crypto.signature_recovery import canonical_address
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus import unavail, vote_journal
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.consensus.remote_attestation_crypto import _attestation_message, _sign_attestation
from aitbc_chain.consensus.unavail import GossipObservationIndex
from aitbc_chain.consensus.vote_journal import reset_vote_journals
from aitbc_chain.metrics import metrics_registry

from . import test_round_lock as rl

_round_lock_on = rl._round_lock_on  # reuse the round-lock fixture (autouse)
CHAIN = "test-chain"
A = "0xaaaa"
OUR, OUR_KEY, PROP, PROP_KEY = rl._keys()
EVIL_KEY = "0x" + "33" * 32
OTHER = "0x" + "44" * 20


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    metrics_registry.reset()
    reset_vote_journals()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    monkeypatch.setattr(settings, "vote_journal_justification_enabled", True)
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": OUR}, {"address": PROP}]))
    yield
    reset_vote_journals()
    metrics_registry.reset()


def _svc() -> RemoteAttestationService:
    return RemoteAttestationService(CHAIN, {OUR: OUR_KEY})


def _msg(height: int = 100, block_hash: str = A, round_: int | None = 0) -> dict:
    return _attestation_message(rl._header(height, block_hash, PROP, round_ or 0)["header"], CHAIN, round_)


def _response(msg: dict, key: str, validator: str, **extra) -> dict:
    resp = {
        "chain_id": CHAIN,
        "height": msg["height"],
        "hash": msg["hash"],
        "validator": validator,
        "signature": _sign_attestation(msg, key, msg["height"]),
    }
    if "round" in msg:
        resp["round"] = msg["round"]
    resp.update(extra)
    return resp


def _index_with_request(msg: dict) -> GossipObservationIndex:
    idx = GossipObservationIndex()
    idx.note_request(msg["height"], msg["hash"], PROP, att_message=msg)
    return idx


class TestResponseAuthentication:
    def test_honest_response_authenticates(self):
        msg = _msg()
        idx = _index_with_request(msg)
        assert _svc()._index_response_authentic(idx, _response(msg, OUR_KEY, OUR), 100, A, OUR) is True
        assert _counter("unavail_obs_response_unverified_total") == 0

    def test_forged_validator_claim_is_rejected(self):
        """Signed by an attacker key, claimed to come from a real validator."""
        msg = _msg()
        idx = _index_with_request(msg)
        forged = _response(msg, EVIL_KEY, OUR)
        assert _svc()._index_response_authentic(idx, forged, 100, A, OUR) is False
        assert _counter("unavail_obs_response_unverified_total") == 1

    def test_response_for_a_key_with_no_verified_request_is_dropped(self):
        msg = _msg()
        idx = GossipObservationIndex()  # the request was never seen / never verified
        assert _svc()._index_response_authentic(idx, _response(msg, OUR_KEY, OUR), 100, A, OUR) is False
        assert idx._entries == {}  # and a response can never create an entry

    @pytest.mark.parametrize("sig", [None, "", 123])
    def test_missing_or_malformed_signature_is_rejected(self, sig):
        msg = _msg()
        idx = _index_with_request(msg)
        resp = _response(msg, OUR_KEY, OUR)
        resp["signature"] = sig
        assert _svc()._index_response_authentic(idx, resp, 100, A, OUR) is False

    def test_round_contradicting_the_request_is_rejected(self):
        msg = _msg(round_=0)
        idx = _index_with_request(msg)
        resp = _response(msg, OUR_KEY, OUR, round=3)
        assert _svc()._index_response_authentic(idx, resp, 100, A, OUR) is False

    def test_signature_over_a_different_hash_is_rejected(self):
        msg = _msg()
        other = _msg(block_hash="0xbbbb")
        idx = _index_with_request(msg)
        replay = _response(other, OUR_KEY, OUR)
        replay["hash"] = A  # claim it is for the indexed hash
        assert _svc()._index_response_authentic(idx, replay, 100, A, OUR) is False

    @pytest.mark.asyncio
    async def test_listener_stores_the_verified_request_payload(self, monkeypatch, tmp_path):
        """End to end: the real request handler records the signed payload, and
        the response it published authenticates against it."""
        await unavail.reset_observation_indices()
        svc, broker = rl._service(monkeypatch, OUR, OUR_KEY, PROP, tmp_path)
        await svc._handle_request(rl._header(100, A, PROP, 0))
        assert len(broker.published) == 1
        published = broker.published[0][1]
        idx = await unavail.get_observation_index(CHAIN)
        assert idx.attestation_message(100, A) == _msg()
        assert svc._index_response_authentic(idx, published, 100, A, published["validator"]) is True
        await unavail.reset_observation_indices()


class TestEviction:
    @staticmethod
    def _idx(max_entries: int = 4) -> GossipObservationIndex:
        idx = GossipObservationIndex()
        idx._max_entries = max_entries
        return idx

    def test_lowest_height_entry_goes_not_everything(self):
        idx = self._idx()
        for h in range(100, 104):
            idx.note_request(h, f"0x{h}", PROP)
        idx.note_request(104, "0x104", PROP)
        assert sorted(k[0] for k in idx._entries) == [101, 102, 103, 104]  # was: all wiped

    def test_in_window_evidence_survives_a_flood(self):
        """The hash we voted has a fresh foreign attestation; 600 junk keys at
        the same height must not make the height look quiet again."""
        idx = GossipObservationIndex()
        idx.note_request(100, A, PROP)
        idx.note_response(100, A, OTHER)
        before = idx.clean_verdict(100, A, window=60.0)
        assert before["quiet"] is False
        for i in range(600):
            idx.note_request(100, f"0xjunk{i}", PROP)
        assert len(idx._entries) <= idx._max_entries
        assert idx.clean_verdict(100, A, window=60.0)["quiet"] is False
        assert _counter("unavail_obs_entry_refused_total") > 0

    def test_stale_entry_is_evicted_first(self, monkeypatch):
        idx = self._idx()
        clock = [1000.0]
        monkeypatch.setattr(GossipObservationIndex, "_mono", staticmethod(lambda: clock[0]))
        idx.note_request(105, "0xold", PROP)  # HIGH height but will be stale
        clock[0] += unavail.evidence_seconds() + 1
        for h in (100, 101, 102):
            idx.note_request(h, f"0x{h}", PROP)
        idx.note_request(103, "0x103", PROP)
        keys = {k[1] for k in idx._entries}
        assert "0xold" not in keys
        assert {"0x100", "0x101", "0x102", "0x103"} <= keys

    def test_newcomer_not_above_any_entry_is_refused(self):
        idx = self._idx()
        for h in range(101, 105):
            idx.note_request(h, f"0x{h}", PROP)
        idx.note_request(100, "0xlow", PROP)
        assert (100, "0xlow") not in idx._entries
        assert len(idx._entries) == 4
        assert _counter("unavail_obs_entry_refused_total") == 1


class TestHeightBound:
    def test_bounds_around_the_tip(self):
        assert unavail.obs_height_plausible(100, 100)
        assert unavail.obs_height_plausible(100 + unavail.OBS_HEIGHT_AHEAD, 100)
        assert not unavail.obs_height_plausible(100 + unavail.OBS_HEIGHT_AHEAD + 1, 100)
        assert unavail.obs_height_plausible(100 - unavail.OBS_HEIGHT_BEHIND, 100)
        assert not unavail.obs_height_plausible(100 - unavail.OBS_HEIGHT_BEHIND - 1, 100)
        assert unavail.obs_height_plausible(10**9, None)  # unknown tip: unchanged behaviour

    def test_implausible_heights_are_not_recorded(self):
        idx = GossipObservationIndex()
        idx.note_request(10**9, "0xfar", PROP, tip_hint=100)
        idx.note_response(10**9, "0xfar", OTHER, tip_hint=100)
        assert idx._entries == {}
        assert idx._actors == {}
        assert _counter("unavail_obs_height_rejected_total") == 2
        idx.note_request(101, "0xnear", PROP, tip_hint=100)
        assert (101, "0xnear") in idx._entries

    def test_legacy_call_shape_is_unchanged(self):
        idx = GossipObservationIndex()
        idx.note_request(100, A, PROP)
        idx.note_response(100, A, OTHER)
        assert idx.attestation_message(100, A) is None
        assert idx.quiet_verdict(100, A)["attestations_seen"] == 1
        assert canonical_address(OTHER) in idx._entries[(100, A)]["attestations"]


class _Sub:
    """Async-iterable stand-in for a TopicSubscription."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item

    def close(self):
        pass


class TestFeedWiring:
    @pytest.mark.asyncio
    async def test_feed_records_only_authenticated_responses(self, monkeypatch):
        """Runs the real ``_listen_responses_for_index`` loop: a forged
        response is not recorded, the honest one is."""
        await unavail.reset_observation_indices()
        msg = _msg()
        idx = await unavail.get_observation_index(CHAIN)
        idx.note_request(100, A, PROP, att_message=msg)
        forged = _response(msg, EVIL_KEY, PROP)  # claims to be the proposer-side validator
        honest = _response(msg, OUR_KEY, OUR)

        async def _subscribe(topic, max_queue_size=0):
            return _Sub([forged, honest])

        monkeypatch.setattr(ra_module, "gossip_broker", type("B", (), {"subscribe": staticmethod(_subscribe)})())
        svc = RemoteAttestationService(CHAIN, {})  # no own keys: nothing is ignored
        await svc._listen_responses_for_index()
        attesters = idx._entries[(100, A)]["attestations"]
        assert set(attesters) == {canonical_address(OUR)}  # the forged claim never landed
        assert _counter("unavail_obs_response_unverified_total") == 1
        await unavail.reset_observation_indices()
