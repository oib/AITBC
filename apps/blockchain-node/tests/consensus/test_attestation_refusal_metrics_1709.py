"""#1709: every attestation refusal is counted; responses carry request_age_ms.

A past-skewed validator used to drop peer attest requests with only a
journal line — a silent quorum dropout invisible to metrics and peers.
Pins: ``attestation_refused_total`` plus per-reason counters on ALL
refusal exits of ``_handle_request`` (freshness, resign-after-expiry,
non-validator proposer, bad proposer signature, unsigned request when
required), and ``request_age_ms`` on published attestation responses.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry

T0 = 1_800_000_000.0


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


class TestRefusalMetrics:
    @pytest.mark.asyncio
    async def test_freshness_refusal_counts_total_and_reason(self, monkeypatch):
        """The #1709 case: a peer header 35s in OUR future is refused —
        now visible as attestation_refused_future_header_total AND the
        aggregate attestation_refused_total."""
        svc, broker, clock, proposer = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now + 35))
        assert not broker.published
        assert _counter("attestation_refused_future_header_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_stale_header_counts_total_and_reason(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now - 61))
        assert _counter("attestation_refused_stale_header_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_resign_after_expiry_counts_total_and_reason(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now))
        clock.advance(61)
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock.now - 61))
        # second request is stale AND would be resign — freshness fires first;
        # use a fresh timestamp for the same hash to hit resign path instead
        metrics_registry.reset()
        clock2 = _Clock(T0)
        svc2, broker2, clock2, proposer2 = _service(monkeypatch, clock2)
        await svc2._handle_request(_request(100, "0xaaaa", proposer2, clock2.now))
        clock2.advance(61)
        await svc2._handle_request(_request(100, "0xaaaa", proposer2, clock2.now))
        assert _counter("attestation_refused_resign_after_expiry_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_non_validator_proposer_is_counted(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        stranger = "0x" + "33" * 20
        await svc._handle_request(_request(100, "0xaaaa", stranger, clock.now))
        assert not broker.published
        assert _counter("attestation_refused_non_validator_proposer_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_bad_proposer_signature_is_counted(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        req["proposer_signature"] = "0x" + "00" * 65
        await svc._handle_request(req)
        assert not broker.published
        assert _counter("attestation_refused_bad_proposer_signature_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_unsigned_request_refused_when_required_is_counted(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_require_signed_attest_request", True)
        svc, broker, clock, proposer = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now))
        assert not broker.published
        assert _counter("attestation_refused_unsigned_attest_request_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_round_auth_mismatch_is_counted(self, monkeypatch):
        """Round-authentication refusal (declared != independently derived
        round) is a policy refusal — it must be counted like the rest."""
        monkeypatch.setattr(settings, "attestation_round_lock_enabled", True)
        svc, broker, clock, proposer = _service(monkeypatch)
        svc._derive_request_round = lambda header: 0  # type: ignore[method-assign]
        req = _request(100, "0xaaaa", proposer, clock.now)
        req["header"]["round"] = 5  # declared 5, derived 0 -> mismatch
        await svc._handle_request(req)
        assert not broker.published
        assert _counter("attestation_refused_round_auth_mismatch_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_tip_authorization_refusal_is_counted(self, monkeypatch):
        """Round auth passes but _tip_authorizes refuses (no local head in
        the test env) — the tip reason must surface as a bounded counter."""
        monkeypatch.setattr(settings, "attestation_round_lock_enabled", True)
        svc, broker, clock, proposer = _service(monkeypatch)
        svc._derive_request_round = lambda header: 0  # type: ignore[method-assign]
        req = _request(100, "0xaaaa", proposer, clock.now)
        req["header"]["round"] = 0  # matches derived -> reaches tip check
        await svc._handle_request(req)
        assert not broker.published
        assert _counter("attestation_refused_tip_no_local_head_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_attestation_lock_rival_is_counted(self, monkeypatch):
        """A rival hash at a locked height is refused by the attestation
        lock — the silent-dropout class #1709 targets."""
        svc, broker, clock, proposer = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now))
        assert broker.published
        metrics_registry.reset()
        await svc._handle_request(_request(100, "0xbbbb", proposer, clock.now))
        assert _counter("attestation_refused_attestation_lock_rival_total") == 1.0
        assert _counter("attestation_refused_total") == 1.0

    @pytest.mark.asyncio
    async def test_unsigned_request_allowed_when_not_required_is_not_a_refusal(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        await svc._handle_request(_request(100, "0xaaaa", proposer, clock.now))
        assert broker.published
        assert _counter("attestation_refused_total") == 0.0


class TestResponseMetadata:
    @pytest.mark.asyncio
    async def test_response_carries_request_age_ms(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        req["timestamp"] = clock.now - 1.5  # 1500ms old at the fake clock
        await svc._handle_request(req)
        responses = [m for m in broker.published if m.get("signature")]
        assert responses, "expected at least one attestation response"
        assert responses[0]["request_age_ms"] == 1500

    @pytest.mark.asyncio
    async def test_response_omits_request_age_ms_without_timestamp(self, monkeypatch):
        svc, broker, clock, proposer = _service(monkeypatch)
        req = _request(100, "0xaaaa", proposer, clock.now)
        del req["timestamp"]
        await svc._handle_request(req)
        responses = [m for m in broker.published if m.get("signature")]
        assert responses
        assert "request_age_ms" not in responses[0]
