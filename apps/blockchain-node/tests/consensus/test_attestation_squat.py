"""R12-A2-1 (#1240): a forged gossip attest_request must not squat the lock.

The sequence seen on the at1 sandbox mesh: any validator-authenticated WS
client publishes an *unsigned* attest_request that names the scheduled
proposer and carries a self-consistent hash for a block that is never
produced. Every honest attester used to sign it and record an attestation
lock on the fake hash, then refuse the real proposer's request inside the
lock window ("Attestation lock: refusing to sign rival"), stretching the
round from ~61 s to ~80 s. Repeated every round it approaches a stall.

``consensus_require_signed_attest_request`` closes it: authorship is proved
by the scheduled proposer's block signature, which the attacker cannot make.
These pins hold the *default* configuration, so a fresh deployment (the
sandbox mesh carried no override) is protected without an env edit.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from aitbc_chain.config import ChainSettings, settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry

from tests.consensus.test_attestation_lock import (
    _keys,
    _schedule,
    _signed_request,
    _StubBroker,
    _timed_header,
)

FORGED = "0x" + "f0" * 32
REAL = "0x" + "a1" * 32
HEIGHT = 100


@pytest.fixture(autouse=True)
def _shipped_defaults(monkeypatch):
    """Run under the shipped default, not whatever the test env exports."""
    metrics_registry.reset()
    default = ChainSettings.model_fields["consensus_require_signed_attest_request"].default
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", default)
    yield
    metrics_registry.reset()


def _attester(monkeypatch):
    our_addr, our_key, proposer_addr, proposer_key = _keys()
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
    )
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService("test-chain", {our_addr: our_key})
    parent_ts = _schedule(monkeypatch, proposer_addr)
    return svc, broker, proposer_addr, proposer_key, parent_ts + timedelta(seconds=10)


def test_shipped_default_requires_signed_requests():
    """Mutation pin: flipping the default back to False reopens the squat on
    every deployment that carries no explicit override."""
    assert ChainSettings.model_fields["consensus_require_signed_attest_request"].default is True


@pytest.mark.asyncio
async def test_forged_request_does_not_squat_the_real_proposers_request(monkeypatch):
    svc, broker, proposer, proposer_key, ts = _attester(monkeypatch)

    # 1. Forgery: valid-looking, names the scheduled proposer, no signature.
    await svc._handle_request(_timed_header(HEIGHT, FORGED, proposer, ts))
    assert not broker.published, "an unsigned request must not collect an attestation"
    assert svc.attestation_lock(HEIGHT, 60.0) is None, "…and must not leave a lock behind"

    # 2. The real proposer's signed request for the same height is attested
    #    straight away — no "refusing to sign rival", no retry-after-expiry.
    await svc._handle_request(_signed_request(HEIGHT, REAL, proposer_key, proposer, ts))
    assert len(broker.published) == 1
    assert broker.published[0][1]["hash"] == REAL
    assert svc.attestation_lock(HEIGHT, 60.0)[0] == REAL


@pytest.mark.asyncio
async def test_forgery_signed_by_a_third_key_does_not_squat_either(monkeypatch):
    svc, broker, proposer, proposer_key, ts = _attester(monkeypatch)

    await svc._handle_request(_signed_request(HEIGHT, FORGED, "0x" + "77" * 32, proposer, ts))
    assert not broker.published
    assert svc.attestation_lock(HEIGHT, 60.0) is None

    await svc._handle_request(_signed_request(HEIGHT, REAL, proposer_key, proposer, ts))
    assert svc.attestation_lock(HEIGHT, 60.0)[0] == REAL


@pytest.mark.asyncio
async def test_unarmed_escape_hatch_reproduces_the_squat(monkeypatch):
    """The documented rolling-upgrade override (=false) is exactly the
    vulnerable configuration: this is the repro sequence, kept so the pin
    above is known to bite."""
    svc, broker, proposer, proposer_key, ts = _attester(monkeypatch)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)

    await svc._handle_request(_timed_header(HEIGHT, FORGED, proposer, ts))
    assert svc.attestation_lock(HEIGHT, 60.0)[0] == FORGED  # squatted

    await svc._handle_request(_signed_request(HEIGHT, REAL, proposer_key, proposer, ts))
    assert len(broker.published) == 1  # real request refused: only the forged one was signed
    assert svc.attestation_lock(HEIGHT, 60.0)[0] == FORGED


@pytest.mark.asyncio
async def test_honest_replay_stays_idempotent_when_armed(monkeypatch):
    """Dedup of an identical signed request is unchanged by arming."""
    svc, broker, proposer, proposer_key, ts = _attester(monkeypatch)
    req = _signed_request(HEIGHT, REAL, proposer_key, proposer, ts)

    await svc._handle_request(req)
    await svc._handle_request(req)
    assert len(broker.published) == 2
    assert svc.attestation_lock(HEIGHT, 60.0)[0] == REAL
