"""#1245: attestation replay cannot renew the attester lock.

Pins the AD ruling (comment 18687): each (height, block_hash) is signed once
per node and a duplicate never renews the lock (c2), and a request whose SIGNED
HEADER timestamp is older than ``attestation_header_max_age_seconds`` -- or
further in the future than the skew allowance -- is refused, so retransmitting
a captured request, or replaying it after a restart, re-arms nothing.

Time is a fake clock injected into the service: header timestamps are naive UTC
ISO strings exactly as ``collect_attestations`` emits them.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry

T0 = 1_800_000_000.0  # arbitrary fixed "now"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    metrics_registry.reset()
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 60.0)
    monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 10.0)
    yield
    metrics_registry.reset()


class _Clock:
    """Stands in for the `time` module inside remote_attestation."""

    def __init__(self, now: float = T0) -> None:
        self.now = now

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Broker:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: str, message: dict) -> None:
        self.published.append(message)


def _keys() -> tuple[str, str, str]:
    from eth_keys import keys

    our_key = "0x" + "11" * 32
    proposer_key = "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).replace(tzinfo=None).isoformat()


def _request(height: int, block_hash: str, proposer: str, header_epoch: float | None) -> dict:
    header = {
        "chain_id": "test-chain",
        "height": height,
        "hash": block_hash,
        "parent_hash": "0xparent",
        "proposer": proposer,
        "state_root": "0xroot",
        "bridge_state_root": "",
    }
    if header_epoch is not None:
        header["timestamp"] = _ts(header_epoch)
    return {"header": header, "timestamp": T0}


def _service(monkeypatch, clock: _Clock | None = None):
    our_addr, our_key, proposer = _keys()
    monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": our_addr}, {"address": proposer}]))
    broker = _Broker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    clock = clock or _Clock()
    monkeypatch.setattr(ra_module, "time", clock)
    return RemoteAttestationService("test-chain", {our_addr: our_key}), broker, clock, proposer


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


class TestReplayIdempotence:
    @pytest.mark.asyncio
    async def test_replay_inside_window_is_one_signing_one_lock(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)

        await svc._handle_request(req)
        first_lock = svc._attested[100]
        for _ in range(5):
            clock.advance(2)
            await svc._handle_request(req)

        # Idempotent re-publish is allowed, but it is the same signing.
        assert svc._signed_once == {100: {None: {"0xaaaa"}}}
        assert svc._attested[100] == first_lock
        assert {m["signature"] for m in broker.published} == {broker.published[0]["signature"]}

    @pytest.mark.asyncio
    async def test_re_sign_does_not_renew_the_lock(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        await svc._handle_request(req)  # signs at t0, lock until t0+60

        clock.advance(40)
        await svc._handle_request(req)  # duplicate at t0+40
        assert len(broker.published) == 2
        assert svc._attested[100][None][2] == T0  # signed_at is still the first signing

        # t0+65: had the duplicate renewed the lock it would live until t0+100.
        clock.advance(25)
        assert svc.attestation_lock(100, 60.0) is None
        # A rival (fresh header) is signable again -- the lock lapsed on schedule.
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock.now))
        assert svc.attestation_lock(100, 60.0)[0] == "0xbbbb"

    @pytest.mark.asyncio
    async def test_re_sign_after_expiry_is_refused_without_the_freshness_bound(self, monkeypatch):
        """Freshness off: the once-per-(height,hash) memory alone closes the replay."""
        monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        await svc._handle_request(req)
        assert len(broker.published) == 1

        clock.advance(61)
        await svc._handle_request(req)

        assert len(broker.published) == 1
        assert svc.attestation_lock(100, 60.0) is None  # not re-armed
        assert _counter("attestation_refused_resign_after_expiry_total") == 1.0


class TestHeaderFreshness:
    @pytest.mark.asyncio
    async def test_expired_header_is_refused_and_takes_no_lock(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)

        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now - 61))

        assert not broker.published
        assert svc._attested == {} and svc._signed_once == {}
        assert _counter("attestation_refused_stale_header_total") == 1.0

    @pytest.mark.asyncio
    async def test_edge_header_age_at_the_bound(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)

        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now - 59.9))
        await svc._handle_request(_request(101, "0xbbbb", proposer, clock.now - 60.0))  # == bound: still fresh
        await svc._handle_request(_request(102, "0xcccc", proposer, clock.now - 60.1))

        assert [m["height"] for m in broker.published] == [100, 101]
        assert _counter("attestation_refused_stale_header_total") == 1.0

    @pytest.mark.asyncio
    async def test_future_header_beyond_the_skew_allowance_is_refused(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)

        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now + 9.9))  # inside allowance
        await svc._handle_request(_request(101, "0xbbbb", proposer, clock.now + 10.1))  # beyond it

        assert [m["height"] for m in broker.published] == [100]
        assert svc.attestation_lock(101, 60.0) is None
        assert _counter("attestation_refused_future_header_total") == 1.0

    @pytest.mark.asyncio
    async def test_freshness_is_read_from_the_header_not_from_arrival(self, monkeypatch):
        """Retransmission does not refresh: the same request is fresh at t0, stale at t0+61,
        however many times it is re-sent and whatever its envelope timestamp says."""
        svc, broker, clock, proposer = _service(monkeypatch)
        header_epoch = clock.now
        await svc._handle_request(_request(100, "0xaaaa", proposer, header_epoch))
        clock.advance(61)
        replay = _request(101, "0xbbbb", proposer, header_epoch)
        replay["timestamp"] = clock.now  # attacker refreshes the unsigned envelope timestamp
        await svc._handle_request(replay)

        assert [m["height"] for m in broker.published] == [100]

    @pytest.mark.asyncio
    async def test_header_without_timestamp_skips_the_bound_and_is_counted(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)

        await svc._handle_request(_request(100, "0xaaaa", proposer, None))

        assert len(broker.published) == 1  # pre-v9 shadow mode still attests
        assert _counter("attestation_header_timestamp_missing_total") == 1.0

    @pytest.mark.asyncio
    async def test_unparsable_header_timestamp_skips_the_bound(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        req["header"]["timestamp"] = "not-a-time"

        await svc._handle_request(req)

        assert len(broker.published) == 1
        assert _counter("attestation_header_timestamp_missing_total") == 1.0

    @pytest.mark.asyncio
    async def test_aware_timestamp_is_normalised_to_utc(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, None)
        req["header"]["timestamp"] = datetime.fromtimestamp(clock.now - 30, UTC).isoformat()  # +00:00

        await svc._handle_request(req)
        assert len(broker.published) == 1


class TestRestartAndRivals:
    @pytest.mark.asyncio
    async def test_restart_then_replay_of_an_old_request_is_refused(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        await svc._handle_request(req)
        assert len(broker.published) == 1

        clock.advance(61)
        restarted = RemoteAttestationService("test-chain", dict(svc._validator_keys))  # memory is gone
        assert restarted._signed_once == {} and restarted._attested == {}
        await restarted._handle_request(req)

        assert len(broker.published) == 1  # nothing new signed
        assert restarted._attested == {}  # and no lock armed

    @pytest.mark.asyncio
    async def test_restart_replay_inside_the_bound_extends_the_lock_at_most_once(self, monkeypatch):
        """Residual of option c2, documented: restart wipes the memory, so a replay while the
        header is still fresh re-signs once. It cannot repeat -- the second replay is a
        duplicate -- and the header goes stale 60 s after it was built regardless."""
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        await svc._handle_request(req)

        clock.advance(59)
        restarted = RemoteAttestationService("test-chain", dict(svc._validator_keys))
        await restarted._handle_request(req)  # fresh by 1 s: re-signs, new lock
        armed = restarted._attested[100]
        clock.advance(30)
        await restarted._handle_request(req)  # duplicate: no renewal
        assert restarted._attested[100] == armed

        clock.advance(31)  # header is now 120 s old
        await restarted._handle_request(req)
        assert restarted.attestation_lock(100, 60.0) is None

    @pytest.mark.asyncio
    async def test_conflicting_hash_at_the_same_height_is_refused_then_allowed_after_expiry(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now))

        clock.advance(10)
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock.now))  # rival, fresh header
        assert len(broker.published) == 1
        assert svc.attestation_lock(100, 60.0)[0] == "0xaaaa"

        clock.advance(51)  # t0+61: the first lock has lapsed
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock.now))
        assert len(broker.published) == 2
        assert svc._signed_once == {100: {None: {"0xaaaa", "0xbbbb"}}}

        # The old block's request, replayed: stale AND already signed.
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now - 61))
        assert len(broker.published) == 2


class TestLegitimatePropagation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("age", [0.05, 1.0, 15.0, 16.5, 30.0, 45.0, 59.0])
    async def test_delayed_legitimate_request_signs_normally(self, monkeypatch, age):
        """The proposer collects for at most 15 s + 0.5 s per missing attestation (16 s), so
        no request that can still count is older than that; the bound leaves 3.75x headroom."""
        svc, broker, clock, proposer = _service(monkeypatch)

        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now - age))

        assert len(broker.published) == 1
        assert svc.attestation_lock(100, 60.0)[0] == "0xaaaa"

    @pytest.mark.asyncio
    async def test_a_peer_that_was_behind_signs_normally_the_first_time(self, monkeypatch):
        """A lagging attester refuses (nothing recorded) and signs on the first request it can
        take -- refusals must not consume the once-per-(height,hash) allowance."""
        svc, broker, clock, proposer = _service(monkeypatch)
        monkeypatch.setattr(settings, "state_transition_v9_height", 1)  # refusals are enforced, not shadow
        monkeypatch.setattr(svc, "_v9_check_transactions", lambda *a, **k: "not_at_parent")
        req = _request(100, "0xaaaa", proposer, clock.now)
        req["transactions"] = []
        await svc._handle_request(req)
        assert not broker.published and svc._signed_once == {}

        monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
        monkeypatch.setattr(svc, "_v9_check_transactions", lambda *a, **k: None)
        clock.advance(8)
        await svc._handle_request(req)
        assert len(broker.published) == 1
        assert svc._signed_once == {100: {None: {"0xaaaa"}}}


class TestMemoryBounds:
    def test_signed_once_is_pruned_below_the_tip(self, monkeypatch):
        svc, _, _, _ = _service(monkeypatch)
        svc._tip_height_hint = 102  # what the v9 check last read from the local chain
        svc._signed_once = {99: {None: {"0x1"}}, 101: {None: {"0x2"}}, 102: {None: {"0x3"}}}

        assert svc._record_attestation_lock(103, "0x4", "p") is True

        assert sorted(svc._signed_once) == [102, 103]

    def test_signed_once_is_capped_when_no_tip_has_been_read(self, monkeypatch):
        svc, _, _, _ = _service(monkeypatch)
        monkeypatch.setattr(ra_module, "SIGNED_ONCE_MAX_HEIGHTS", 4)
        for height in range(10):
            svc._record_attestation_lock(height, f"0x{height}", "p")
        assert sorted(svc._signed_once) == [6, 7, 8, 9]

    def test_record_returns_false_for_a_duplicate(self, monkeypatch):
        svc, _, clock, _ = _service(monkeypatch)
        assert svc._record_attestation_lock(5, "0xa", "p") is True
        before = svc._attested[5]
        clock.advance(30)
        assert svc._record_attestation_lock(5, "0xa", "p") is False
        assert svc._attested[5] == before
