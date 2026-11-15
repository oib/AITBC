"""#1940 ruling A — UC cert freshness is the evidence block's time, per event.

``unlock_proof_uc_evidence_time_enabled`` (on-chain boolean, resolved at the
apply height) switches the ``uc`` unlock proof's freshness clock from the
apply block's time to each DOUBLE_SIGN attestation event's own evidence
block time — the canonical ``Block.timestamp`` at ``(chain_id,
event.block_height)``. These tests pin the full apply path: real signed
attestation pairs and real unavailability certificates through
``StateTransition.apply_transaction`` on scratch databases.

Pinned semantics:

- flag armed + canonical evidence block present → the cert is judged
  against the evidence block's timestamp, so a cert fresh there excuses
  even when it is stale at apply time;
- flag unset or false → the pre-#1940 apply-time context exactly;
- a cert fresh only against the apply time stays slashable;
- each event resolves its own height's time — two events at different
  heights cannot share one clock;
- ``|epoch - evidence_time| == max_age`` excuses, ``max_age + 1`` does not;
- the canonical lookup constrains ``chain_id`` AND ``height`` — another
  chain's block at the same height supplies nothing;
- negative, future (> apply height) or missing evidence blocks never excuse;
- ``evidence_height == apply_height`` uses the caller-sealed ``block_time``
  (the block being applied may not be inserted yet);
- both signed records must carry the event's height as a strict ``int`` on
  the context's chain — a relabeled or non-integer height never excuses;
- naive and aware UTC timestamps agree, and the wall clock never enters.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from aitbc_chain.base_models import Block, ChainParameter, ChainParameterHistory
from aitbc_chain.consensus import unavail
from aitbc_chain.consensus.equivocation_policy import JUSTIFICATION_FIELD
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.consensus.unavail import UnavailabilityCertificate
from aitbc_chain.state import deactivation_evidence as de
from aitbc_chain.state.state_transition import StateTransition

from aitbc.crypto.signature_recovery import canonical_address

from ..test_apply_parity import CHAIN, PROVIDER, PROVIDER_KEY, _seed_bond
from .test_deactivation_evidence_1263 import HA, HB, V2, _attestation_record, _v2_payload
from .test_unavail_cert_fuzz_1281 import ADDR1, ADDR2, ADDR3, KEY1, KEY2
from .test_validator_deactivation_1198 import _deactivation_tx, _engine, _markers, _seed_authority

EVIDENCE_H = 11
APPLY_H = 20
HC = "0x" + "cc" * 32
HD = "0x" + "dd" * 32
FLAG = "unlock_proof_uc_evidence_time_enabled"

# Evidence block 11 sealed at E0; the apply block lands 20h later. A cert
# epoched at E0 is fresh against the evidence block and stale against apply.
E0 = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)
EPOCH = int(E0.timestamp())
APPLY_TIME = E0 + timedelta(hours=20)
APPLY_EPOCH = int(APPLY_TIME.timestamp())

VSET = {canonical_address(a) for a in (ADDR1, ADDR2, ADDR3)}
DIGEST = hashlib.sha256("\n".join(sorted(VSET)).encode()).hexdigest()


def _cert(block_hash: str, *, height: int = EVIDENCE_H, epoch: int = EPOCH) -> dict:
    return UnavailabilityCertificate(
        chain_id=CHAIN,
        height=height,
        hash=block_hash,
        epoch=epoch,
        responses=tuple(
            {
                "validator": a,
                "signature": unavail.build_unavail_response(CHAIN, height, block_hash, epoch, a, k)["signature"],
            }
            for a, k in ((ADDR1, KEY1), (ADDR2, KEY2))
        ),
    ).to_dict()


def _inject_uc(mgr: SlashingManager, index: int, cert: dict) -> None:
    event = mgr.slashing_events[index]
    evidence = json.loads(event.evidence)
    evidence[JUSTIFICATION_FIELD] = {"kind": "uc", "cert": cert}
    mgr.slashing_events[index] = replace(event, evidence=json.dumps(evidence, sort_keys=True))


def _payload_one(
    *,
    height: int = EVIDENCE_H,
    hash_a: str = HA,
    hash_b: str = HB,
    rounds: tuple[int, int] = (0, 5),
    cert: dict | None = None,
    att_height: int | str | float | bool | None = None,
) -> dict:
    """One signed cross-round attestation pair at ``height`` with an optional UC cert."""
    signed_height = height if att_height is None else att_height
    attestations = [
        _attestation_record(
            PROVIDER_KEY, hash_a, height=signed_height, round_in_payload=True, request_round=rounds[0], chain_id=CHAIN
        ),
        _attestation_record(
            PROVIDER_KEY, hash_b, height=signed_height, round_in_payload=True, request_round=rounds[1], chain_id=CHAIN
        ),
    ]
    mgr = SlashingManager()
    mgr.record_attestation_equivocation(
        validator_address=PROVIDER,
        height=height,
        round_number=rounds[1],
        block_hash_a=hash_a,
        block_hash_b=hash_b,
        proposer=V2,
        attestations=attestations,
    )
    if cert is not None:
        _inject_uc(mgr, 0, cert)
    payload = _v2_payload(mgr, PROVIDER)
    payload["bond_id"] = "bond-par-1"
    return payload


def _payload_two_heights() -> dict:
    """Two equivocation events at heights 11 and 12, each with its own signed pair and cert."""
    mgr = SlashingManager()
    for height, hash_a, hash_b, _epoch in (
        (EVIDENCE_H, HA, HB, EPOCH),
        (EVIDENCE_H + 1, HC, HD, EPOCH + 1000),
    ):
        attestations = [
            _attestation_record(PROVIDER_KEY, hash_a, height=height, round_in_payload=True, request_round=0, chain_id=CHAIN),
            _attestation_record(PROVIDER_KEY, hash_b, height=height, round_in_payload=True, request_round=5, chain_id=CHAIN),
        ]
        mgr.record_attestation_equivocation(
            validator_address=PROVIDER,
            height=height,
            round_number=5,
            block_hash_a=hash_a,
            block_hash_b=hash_b,
            proposer=V2,
            attestations=attestations,
        )
    _inject_uc(mgr, 0, _cert(HA))
    _inject_uc(mgr, 1, _cert(HC, height=EVIDENCE_H + 1, epoch=EPOCH + 1000))
    payload = _v2_payload(mgr, PROVIDER)
    payload["bond_id"] = "bond-par-1"
    return payload


def _block(height: int, when: datetime, *, chain_id: str = CHAIN) -> Block:
    return Block(
        chain_id=chain_id,
        height=height,
        hash="0x" + f"{height + 0x1000:064x}",
        parent_hash="0x" + "00" * 32,
        proposer=PROVIDER,
        timestamp=when,
    )


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


def _apply(
    tmp_path,
    payload: dict,
    *,
    block_height: int = APPLY_H,
    block_time: datetime = APPLY_TIME,
    db: str = "ucet.db",
    param_over: dict | None = None,
    rows=(),
) -> int:
    """Apply the deactivation; return how many markers landed."""
    st = StateTransition()
    with Session(_engine(tmp_path, db)) as session:
        _seed_bond(session)
        _seed_authority(session)
        _seed_params(session, **(param_over or {}))
        for row in rows:
            session.add(row)
        session.commit()
        ok, msg = st.apply_transaction(
            session,
            CHAIN,
            _deactivation_tx(payload),
            tx_hash="vd-uet",
            block_version=22,
            block_height=block_height,
            block_time=block_time,
        )
        assert ok, msg
        return len(_markers(session))


@pytest.fixture(autouse=True)
def _vset(monkeypatch):
    monkeypatch.setattr(unavail, "validator_addresses", lambda: set(VSET))


class TestEvidenceTimeFlag:
    """Flag armed: freshness is the evidence block's canonical time, per event."""

    def test_armed_excuses_cert_fresh_at_evidence_time(self, tmp_path):
        payload = _payload_one(cert=_cert(HA))
        assert _apply(tmp_path, payload, rows=[_block(EVIDENCE_H, E0)], param_over={FLAG: "true"}, db="armed.db") == 0

    @pytest.mark.parametrize("flag", ["false", None])
    def test_unset_or_false_keeps_apply_time_freshness(self, tmp_path, flag):
        """Legacy path: a cert epoched at evidence time is 20h stale at apply → slashable."""
        payload = _payload_one(cert=_cert(HA))
        assert _apply(tmp_path, payload, rows=[_block(EVIDENCE_H, E0)], param_over={FLAG: flag}, db=f"legacy-{flag}.db") == 1

    def test_cert_fresh_only_against_apply_time_stays_slashable(self, tmp_path):
        """Armed: ``now`` is evidence time — a cert epoched at apply time is stale there."""
        payload = _payload_one(cert=_cert(HA, epoch=APPLY_EPOCH))
        assert _apply(tmp_path, payload, rows=[_block(EVIDENCE_H, E0)], param_over={FLAG: "true"}, db="applyfresh.db") == 1

    def test_each_event_resolves_its_own_evidence_time(self, tmp_path):
        payload = _payload_two_heights()
        assert (
            _apply(
                tmp_path,
                payload,
                rows=[_block(EVIDENCE_H, E0), _block(EVIDENCE_H + 1, E0 + timedelta(seconds=1000))],
                param_over={FLAG: "true"},
                db="two-on.db",
            )
            == 0
        )
        assert (
            _apply(
                tmp_path,
                payload,
                rows=[_block(EVIDENCE_H, E0), _block(EVIDENCE_H + 1, E0 + timedelta(seconds=1000))],
                param_over={FLAG: "false"},
                db="two-off.db",
            )
            == 1
        )

    @pytest.mark.parametrize("delta,markers", [(120, 0), (-120, 0), (121, 1), (-121, 1)])
    def test_cert_epoch_boundary_against_max_age(self, tmp_path, delta, markers):
        payload = _payload_one(cert=_cert(HA, epoch=EPOCH + delta))
        assert (
            _apply(tmp_path, payload, rows=[_block(EVIDENCE_H, E0)], param_over={FLAG: "true"}, db=f"edge-{delta}.db")
            == markers
        )

    def test_block_on_another_chain_cannot_supply_time(self, tmp_path):
        payload = _payload_one(cert=_cert(HA))
        assert (
            _apply(
                tmp_path,
                payload,
                rows=[_block(EVIDENCE_H, E0, chain_id="other-chain")],
                param_over={FLAG: "true"},
                db="xchain.db",
            )
            == 1
        )

    def test_missing_evidence_block_never_excuses(self, tmp_path):
        payload = _payload_one(cert=_cert(HA))
        assert _apply(tmp_path, payload, rows=[], param_over={FLAG: "true"}, db="noblock.db") == 1

    def test_negative_evidence_height_never_excuses(self, tmp_path):
        payload = _payload_one(height=-5, att_height=-5, cert=_cert(HA, height=-5))
        assert _apply(tmp_path, payload, rows=[], param_over={FLAG: "true"}, db="neg.db") == 1

    def test_future_evidence_height_never_excuses(self, tmp_path):
        payload = _payload_one(height=25, att_height=25, cert=_cert(HA, height=25))
        assert _apply(tmp_path, payload, rows=[], param_over={FLAG: "true"}, db="future.db") == 1

    def test_apply_height_event_uses_sealed_block_time(self, tmp_path):
        """``evidence_height == apply_height`` → caller ``block_time``, not a DB row."""
        payload = _payload_one(height=APPLY_H, att_height=APPLY_H, cert=_cert(HA, height=APPLY_H, epoch=APPLY_EPOCH))
        # The canonical row disagrees (E0, stale vs the cert) — the sealed caller time must win.
        assert (
            _apply(
                tmp_path,
                payload,
                block_height=APPLY_H,
                block_time=APPLY_TIME,
                rows=[_block(APPLY_H, E0)],
                param_over={FLAG: "true"},
                db="sealed.db",
            )
            == 0
        )
        # A naive caller block_time resolves identically (naive reads as UTC).
        assert (
            _apply(
                tmp_path,
                payload,
                block_height=APPLY_H,
                block_time=APPLY_TIME.replace(tzinfo=None),
                rows=[_block(APPLY_H, E0)],
                param_over={FLAG: "true"},
                db="sealed-naive.db",
            )
            == 0
        )

    @pytest.mark.parametrize(
        "signed_height,cert_height",
        [(12, 12), ("11", 11), (True, 1), (11.0, 11)],
    )
    def test_signed_height_not_matching_event_height_never_excuses(self, tmp_path, signed_height, cert_height):
        """Both signed records must carry the event height as a strict int on ``ctx.chain_id``."""
        payload = _payload_one(height=EVIDENCE_H, att_height=signed_height, cert=_cert(HA, height=cert_height))
        assert (
            _apply(
                tmp_path,
                payload,
                rows=[_block(EVIDENCE_H, E0)],
                param_over={FLAG: "true"},
                db=f"signed-{signed_height}.db",
            )
            == 1
        )

    def test_naive_and_aware_block_times_agree(self):
        naive = E0.replace(tzinfo=None)
        assert de._epoch_seconds(naive) == de._epoch_seconds(E0) == float(EPOCH)
        assert de._epoch_seconds(None) is None

    def test_verdict_is_wall_clock_independent(self, tmp_path, monkeypatch):
        payload = _payload_one(cert=_cert(HA))
        over = {FLAG: "true"}
        first = _apply(tmp_path, payload, rows=[_block(EVIDENCE_H, E0)], param_over=over, db="clock-a.db")
        real = time.time
        monkeypatch.setattr(time, "time", lambda: real() + 365 * 86400)
        second = _apply(tmp_path, payload, rows=[_block(EVIDENCE_H, E0)], param_over=over, db="clock-b.db")
        assert first == second == 0

    def test_parameter_history_scopes_activation_by_apply_height(self, tmp_path):
        """Flag armed only from height 25: an apply at 20 keeps legacy semantics."""
        payload = _payload_one(cert=_cert(HA))

        def rows():
            return [
                _block(EVIDENCE_H, E0),
                ChainParameterHistory(chain_id=CHAIN, parameter=FLAG, value="true", applied_height=25),
                ChainParameter(chain_id=CHAIN, parameter=FLAG, value="true", applied_height=25),
            ]

        assert (
            _apply(tmp_path, payload, block_height=20, block_time=APPLY_TIME, rows=rows(), param_over={}, db="hist-20.db") == 1
        )
        assert (
            _apply(tmp_path, payload, block_height=30, block_time=APPLY_TIME, rows=rows(), param_over={}, db="hist-30.db") == 0
        )

    @pytest.mark.parametrize("flag", ["false", None])
    def test_flag_off_never_queries_canonical_blocks(self, tmp_path, monkeypatch, flag):
        """Flag unset/false: zero canonical block lookups — the legacy apply-time path exactly."""

        def _boom(*_args, **_kwargs):
            raise AssertionError("_canonical_block_time ran with the flag off")

        monkeypatch.setattr(de, "_canonical_block_time", _boom)
        payload = _payload_one(cert=_cert(HA))
        # Cert epoched at evidence time is 20h stale at apply → legacy slashable verdict.
        assert _apply(tmp_path, payload, rows=[_block(EVIDENCE_H, E0)], param_over={FLAG: flag}, db=f"nolookup-{flag}.db") == 1

    def test_expired_event_skips_lookup_live_event_still_excused(self, tmp_path, monkeypatch):
        """TTL-expired heights do no canonical lookup; live heights still resolve their own time."""
        payload = _payload_two_heights()
        real_lookup = de._canonical_block_time
        looked_up: list[int] = []

        def _selective(session, chain_id, height):
            looked_up.append(height)
            if height == EVIDENCE_H:
                raise AssertionError("canonical lookup ran for a TTL-expired height")
            return real_lookup(session, chain_id, height)

        monkeypatch.setattr(de, "_canonical_block_time", _selective)
        # apply 20 - h11 = 9 > ttl 8 → expired; apply 20 - h12 = 8 → still live.
        assert (
            _apply(
                tmp_path,
                payload,
                rows=[_block(EVIDENCE_H, E0), _block(EVIDENCE_H + 1, E0 + timedelta(seconds=1000))],
                param_over={FLAG: "true", "validator_deactivation_evidence_ttl_blocks": "8"},
                db="ttl-skip.db",
            )
            == 0
        )
        assert looked_up == [EVIDENCE_H + 1]

    def test_apply_height_event_without_block_row_uses_sealed_time(self, tmp_path, monkeypatch):
        """``evidence_height == apply_height`` needs no stored row — and does no lookup."""

        def _boom(*_args, **_kwargs):
            raise AssertionError("canonical lookup ran for the apply height itself")

        monkeypatch.setattr(de, "_canonical_block_time", _boom)
        payload = _payload_one(height=APPLY_H, att_height=APPLY_H, cert=_cert(HA, height=APPLY_H, epoch=APPLY_EPOCH))
        assert (
            _apply(
                tmp_path,
                payload,
                block_height=APPLY_H,
                block_time=APPLY_TIME,
                rows=[],
                param_over={FLAG: "true"},
                db="sealed-norow.db",
            )
            == 0
        )
