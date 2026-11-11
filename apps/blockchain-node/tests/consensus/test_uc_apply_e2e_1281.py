"""#1281 end-to-end apply: a real VALIDATOR_DEACTIVATE through StateTransition.apply_transaction.

In-process stand-in for the mesh replay drill: seeds chain parameters in force at
the block height, builds a signed cross-round attestation pair plus a real
unavailability certificate, and checks excuse vs control through the full apply path.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from aitbc_chain.base_models import ChainParameter
from aitbc_chain.consensus import unavail
from aitbc_chain.consensus.equivocation_policy import JUSTIFICATION_FIELD
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.consensus.unavail import UnavailabilityCertificate
from aitbc_chain.state.state_transition import StateTransition
from sqlmodel import Session

from aitbc.crypto.signature_recovery import canonical_address

from ..test_apply_parity import CHAIN, PROVIDER, PROVIDER_KEY, _seed_bond
from .test_deactivation_evidence_1263 import HA, HB, V2, TestApplyGate, _attestation_record, _v2_payload
from .test_unavail_cert_fuzz_1281 import ADDR1, ADDR2, ADDR3, KEY1, KEY2
from .test_validator_deactivation_1198 import BLOCK_TIME, _deactivation_tx, _engine, _seed_authority

HEIGHT = 11
VSET = {canonical_address(a) for a in (ADDR1, ADDR2, ADDR3)}
DIGEST = hashlib.sha256("\n".join(sorted(VSET)).encode()).hexdigest()
EPOCH = int(BLOCK_TIME.timestamp())


def _cert(block_hash: str, epoch: int = EPOCH) -> dict:
    return UnavailabilityCertificate(
        chain_id=CHAIN,
        height=HEIGHT,
        hash=block_hash,
        epoch=epoch,
        responses=tuple(
            {
                "validator": a,
                "signature": unavail.build_unavail_response(CHAIN, HEIGHT, block_hash, epoch, a, k)["signature"],
            }
            for a, k in ((ADDR1, KEY1), (ADDR2, KEY2))
        ),
    ).to_dict()


def _payload(cert: dict | None) -> dict:
    """Signed cross-round pair (HA at round 0, HB at round 5) with an optional UC justification."""
    atts = [
        _attestation_record(PROVIDER_KEY, HA, height=HEIGHT, round_in_payload=True, request_round=0, chain_id=CHAIN),
        _attestation_record(PROVIDER_KEY, HB, height=HEIGHT, round_in_payload=True, request_round=5, chain_id=CHAIN),
    ]
    mgr = SlashingManager()
    mgr.record_attestation_equivocation(
        validator_address=PROVIDER,
        height=HEIGHT,
        round_number=5,
        block_hash_a=HA,
        block_hash_b=HB,
        proposer=V2,
        attestations=atts,
    )
    if cert is not None:
        ev = json.loads(mgr.slashing_events[0].evidence)
        ev[JUSTIFICATION_FIELD] = {"kind": "uc", "cert": cert}
        mgr.slashing_events[0] = replace(mgr.slashing_events[0], evidence=json.dumps(ev, sort_keys=True))
    payload = _v2_payload(mgr, PROVIDER)
    payload["bond_id"] = "bond-par-1"
    return payload


def _seed_params(session: Session, **over) -> None:
    params = {
        "validator_deactivation_evidence_required": "true",
        "unlock_proof_uc_enabled": "true",
        "unlock_proof_uc_min_responses": "2",
        "unlock_proof_uc_max_age_seconds": "120",
        "unlock_proof_uc_validator_set_digest": DIGEST,
    }
    params.update(over)
    for name, value in params.items():
        if value is not None:
            session.add(ChainParameter(chain_id=CHAIN, parameter=name, value=value, applied_height=0))


def _apply(tmp_path, payload: dict, *, block_time: datetime = BLOCK_TIME, db: str = "vd.db", **param_over) -> int:
    """Apply the deactivation; return how many markers landed."""
    st = StateTransition()
    with Session(_engine(tmp_path, db)) as session:
        _seed_bond(session)
        _seed_authority(session)
        _seed_params(session, **param_over)
        session.commit()
        ok, msg = st.apply_transaction(
            session,
            CHAIN,
            _deactivation_tx(payload),
            tx_hash="vd-uc",
            block_version=22,
            block_height=20,
            block_time=block_time,
        )
        assert ok, msg
        return len(TestApplyGate._markers(session))


@pytest.fixture(autouse=True)
def _vset(monkeypatch):
    monkeypatch.setattr(unavail, "validator_addresses", lambda: set(VSET))


def test_control_no_uc_params_pair_stands_even_with_a_cert(tmp_path):
    """Parent-build behaviour: uc params absent => the cert is ignored, the marker lands."""
    assert _apply(tmp_path, _payload(_cert(HA)), unlock_proof_uc_enabled=None) == 1


def test_control_no_justification_pair_stands(tmp_path):
    assert _apply(tmp_path, _payload(None)) == 1


def test_valid_uc_excuses_the_pair_no_marker(tmp_path):
    assert _apply(tmp_path, _payload(_cert(HA))) == 0


def test_cert_for_later_vote_does_not_excuse(tmp_path):
    assert _apply(tmp_path, _payload(_cert(HB))) == 1


def test_stale_cert_against_block_time_does_not_excuse(tmp_path):
    assert _apply(tmp_path, _payload(_cert(HA)), block_time=BLOCK_TIME + timedelta(seconds=600)) == 1


def test_digest_mismatch_fails_closed(tmp_path):
    assert _apply(tmp_path, _payload(_cert(HA)), unlock_proof_uc_validator_set_digest="00" * 32) == 1


def test_threshold_above_signers_does_not_excuse(tmp_path):
    assert _apply(tmp_path, _payload(_cert(HA)), unlock_proof_uc_min_responses="3") == 1


def test_verdict_is_wall_clock_independent(tmp_path, monkeypatch):
    """Replay a year later (wall clock far ahead): same excuse, because freshness uses block time."""
    first = _apply(tmp_path, _payload(_cert(HA)))
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 365 * 86400)
    assert _apply(tmp_path, _payload(_cert(HA)), db="replay.db") == first == 0


def test_tampered_cert_does_not_excuse(tmp_path):
    cert = _cert(HA)
    cert["responses"][0]["signature"] = cert["responses"][1]["signature"]
    assert _apply(tmp_path, _payload(cert)) == 1


def test_unrelated_zero_height_never_excuses_without_block_time(tmp_path):
    """No sealed block_time (mempool-style call) => context None => pair stands."""
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed_bond(session)
        _seed_authority(session)
        _seed_params(session)
        session.commit()
        ok, _ = st.apply_transaction(
            session,
            CHAIN,
            _deactivation_tx(_payload(_cert(HA))),
            tx_hash="vd-nt",
            block_version=22,
            block_height=20,
            block_time=None,
        )
        assert ok
        assert len(TestApplyGate._markers(session)) == 1
