"""#1298 T1–T22 domain-separation test matrix (design v2.5/v2.6).

One pin per matrix row from the #1298 implementation plan (c23018 T1–T20,
c23383 +T21/T22). Rows that depend on not-yet-landed slices are
``pytest.mark.skip`` with the dependency named — they must NOT fake-pass:

- T7a  unconditional round authentication post-H (round inside the signed
       payload with ``attestation_round_lock_enabled`` OFF)
- T11  proposer emission gate (proposal-signature journal refusing a second
       different-hash proposal at sign time)
- T12  pin-expiry / abandon-height behaviour (AD ruling + emission gate)
- T13  bounded dual-accept window ``[H, S)`` via
       ``consensus_legacy_attestation_until_height``
- T14  declared-round mismatch refused post-H with round_lock OFF
- T15  effective attestation-lock lapse window 130 s shared constant
       (attester + proposer coupling, incl. future-skewed header case)
- T18w legacy attestation counting inside the dual-accept window (T18's
       reject legs ARE implemented below)
- T19  same-key rotation return at r+4 — pending AD disposition (v2.2 O5)
- T20  L4 mixed-version mesh leg (CARD6, sandbox-only, needs impl SHA)

Landed slices covered here: S0 domain helpers, S1 sign/verify gating,
S2 evidence ``signature_domain`` labels + attestation-lock journal.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from aitbc.crypto.consensus_signing import (
    DOMAIN_BLOCK_ATTESTATION,
    DOMAIN_BLOCK_PROPOSAL,
    block_header_message,
    sign_block_hash,
    sign_consensus_message,
    sign_consensus_message_domain,
    verify_consensus_message,
    verify_consensus_message_domain,
)
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.multi_validator_poa import _verify_block_signature_gated
from aitbc_chain.consensus.remote_attestation import (
    RemoteAttestationService,
    _attestation_message,
    _verify_attestation,
)
from aitbc_chain.consensus.slashing import event_signature_evidence
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence

from .test_deactivation_evidence_1263 import ADDR, ADDR_KEY, HA, HB, V2, _v2_payload
from .test_proposer_equivocation_1278 import _header as _header_1278
from .test_proposer_equivocation_1278 import _setup as _setup_1278

ACTIVATION = 50
H = 100  # >= ACTIVATION — domain-separated territory
LOW = ACTIVATION - 1  # < ACTIVATION — legacy territory
CHAIN = "test-chain"
ROUND_SECONDS = 60
PARENT_TS = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _matrix_settings(monkeypatch):
    monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
    if hasattr(settings, "consensus_legacy_attestation_until_height"):
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", None)
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", ROUND_SECONDS)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 60.0)
    monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 10.0)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_enforce_proposer_schedule", False)
    monkeypatch.setattr(settings, "chain_id", CHAIN)
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _keys() -> tuple[str, str, str, str]:
    from eth_keys import keys

    our_key = "0x" + "11" * 32
    proposer_key = "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr, proposer_key


def _header_msg(block_hash: str, proposer: str, *, height: int = H, chain_id: str = CHAIN) -> dict:
    """The canonical 7-field consensus message (no round)."""
    return {
        "chain_id": chain_id,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": proposer,
        "state_root": "0x" + "11" * 32,
        "bridge_state_root": "",
    }


def _block(height: int, block_hash: str, proposer: str, signature: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        chain_id=CHAIN,
        height=height,
        hash=block_hash,
        parent_hash="0x" + "00" * 32,
        proposer=proposer,
        state_root="0x" + "11" * 32,
        bridge_state_root="",
        signature=signature,
    )


def _request(height: int, block_hash: str, proposer: str) -> dict:
    """Non-round-lock attest_request shape (mirrors the journal tests)."""
    return {
        "header": {
            "chain_id": CHAIN,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
        },
        "timestamp": time.time(),
    }


def _block_ts(round_: int) -> datetime:
    return PARENT_TS + timedelta(seconds=round_ * ROUND_SECONDS + 1)


def _rl_request(height: int, block_hash: str, proposer: str, round_: int, parent_hash: str = "0xparent") -> dict:
    """Round-lock attest_request: header carries timestamp + declared round."""
    return {
        "header": {
            "chain_id": CHAIN,
            "height": height,
            "hash": block_hash,
            "parent_hash": parent_hash,
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


def _service(monkeypatch, tmp_path, chain_id: str = CHAIN) -> tuple[RemoteAttestationService, _StubBroker, str, str, str, str]:
    """Attester service with journal/evidence paths isolated to tmp_path."""
    our_addr, our_key, proposer_addr, proposer_key = _keys()
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
    )
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService(chain_id, {our_addr: our_key})
    svc._round_locks_path = tmp_path / "locks.json"
    svc._signed_attestations_path = tmp_path / "attestation_signed.json"
    return svc, broker, our_addr, our_key, proposer_addr, proposer_key


def _round_lock_service(
    monkeypatch, tmp_path, chain_id: str = CHAIN, parent_ts: object = PARENT_TS
) -> tuple[RemoteAttestationService, _StubBroker, str, str, str, str]:
    """Round-lock-enabled variant with tip/parent stubs (test_round_lock shape)."""
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", True)
    monkeypatch.setattr(settings, "attestation_round_unlock_window_seconds", 16.0)
    # Fixed historical timestamps would trip the #1245 freshness bound.
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 3600.0)
    svc, broker, our_addr, our_key, proposer_addr, proposer_key = _service(monkeypatch, tmp_path, chain_id)
    svc._local_head = lambda: (99, "0xparent")  # type: ignore[method-assign]
    svc._canonical_hash_at = lambda h: {99: "0xparent", 100: "0xaaaa"}.get(h)  # type: ignore[method-assign]
    svc._parent_timestamp = lambda p: parent_ts if p == "0xparent" else None  # type: ignore[method-assign]
    return svc, broker, our_addr, our_key, proposer_addr, proposer_key


def _attestation_records(svc: RemoteAttestationService) -> list[dict]:
    data = json.loads(svc._round_locks_path.read_text())
    return [r for r in data["records"] if r.get("kind") == "attestation"]


def _verdict(mgr, validator: str) -> str | None:
    payload = _v2_payload(mgr, validator)
    return verify_deactivation_evidence(
        payload,
        chain_id=CHAIN,
        validator_addr=payload["validator_address"],
        evidence_hash=payload["evidence_hash"],
    )


# ---------------------------------------------------------------------------
# T1/T2 — cross-domain rejection both directions at >= H
# ---------------------------------------------------------------------------


class TestCrossDomainReject:
    def test_T1_proposal_signature_fails_attestation_verification(self, monkeypatch):
        """T1: a proposal-domain signature presented on the attestation
        channel at >= H is rejected — no legacy or cross-domain fallback."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        msg = _header_msg(HA, V2)
        sig = sign_consensus_message_domain(msg, ADDR_KEY, DOMAIN_BLOCK_PROPOSAL)

        # crypto layer: wrong domain never verifies
        assert not verify_consensus_message_domain(msg, sig, ADDR, DOMAIN_BLOCK_ATTESTATION)
        # attestation verify path refuses it outright (dual-accept unset)
        assert not _verify_attestation(msg, sig, ADDR, H)
        # sanity: it IS valid under its own domain
        assert verify_consensus_message_domain(msg, sig, ADDR, DOMAIN_BLOCK_PROPOSAL)

    def test_T2_attestation_signature_fails_proposal_verification(self, monkeypatch):
        """T2: an attestation-domain signature presented as a block
        (proposal) signature at >= H is rejected by the gated verify."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        block = _block(H, HA, ADDR)
        sig = sign_consensus_message_domain(block_header_message(block), ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)
        block.signature = sig

        assert not _verify_block_signature_gated(block, ADDR)
        # sanity: valid under the attestation domain
        assert verify_consensus_message_domain(block_header_message(block), sig, ADDR, DOMAIN_BLOCK_ATTESTATION)


# ---------------------------------------------------------------------------
# T3/T4 — same-domain conflict vs idempotent retry (proposal domain)
# ---------------------------------------------------------------------------


class TestSameDomainProposal:
    def test_T3_two_proposal_hashes_same_key_height_pairs_as_equivocation(self, monkeypatch):
        """T3 (evidence leg): two different proposal-domain hashes by one key
        at one height >= H form domain-scoped equivocation evidence and the
        FIRST signature remains valid. The refuse-at-sign-time leg is the
        proposer emission gate — see skipped T11."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc, mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)

        msg_a = _header_1278(HA, our_addr)  # height H=100 >= ACTIVATION
        sig_a = sign_consensus_message_domain(msg_a, our_key, DOMAIN_BLOCK_PROPOSAL)
        svc._record_signed_attestation(H, HA, our_addr, msg_a, None, False, sig_a, DOMAIN_BLOCK_PROPOSAL)
        svc._signed_once_add(H, HA, DOMAIN_BLOCK_PROPOSAL)

        msg_b = _header_1278(HB, our_addr)
        sig_b = sign_consensus_message_domain(msg_b, our_key, DOMAIN_BLOCK_PROPOSAL)
        svc.record_proposal_equivocation(msg_b, sig_b, 0)

        assert len(mgr.slashing_events) == 1
        evidence = event_signature_evidence(mgr.slashing_events[0])
        assert evidence is not None
        assert {a["signature_domain"] for a in evidence["attestations"]} == {DOMAIN_BLOCK_PROPOSAL}
        # the first signature still verifies under its domain
        assert verify_consensus_message_domain(msg_a, sig_a, our_addr, DOMAIN_BLOCK_PROPOSAL)
        # and the on-chain verifier accepts the pair
        assert _verdict(mgr, our_addr) is None

    def test_T4_same_proposal_hash_resign_is_idempotent(self, monkeypatch):
        """T4: re-signing/re-submitting the SAME proposal hash at >= H is
        idempotent — deterministic signature, gated verify accepts."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        our_addr, our_key, _, _ = _keys()
        block = _block(H, HA, our_addr)

        sig1 = sign_consensus_message_domain(block_header_message(block), our_key, DOMAIN_BLOCK_PROPOSAL)
        sig2 = sign_consensus_message_domain(block_header_message(block), our_key, DOMAIN_BLOCK_PROPOSAL)
        assert sig1 == sig2  # deterministic preimage -> identical bytes

        block.signature = sig1
        assert _verify_block_signature_gated(block, our_addr)


# ---------------------------------------------------------------------------
# T5/T6 — activation boundary: legacy below H, hard cutover at/above H
# ---------------------------------------------------------------------------


class TestActivationBoundary:
    def test_T5_legacy_verifies_both_directions_below_H(self, monkeypatch):
        """T5: at heights < H every path takes the legacy preimage —
        historical blocks/replays are unaffected."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        our_addr, our_key, _, _ = _keys()

        # proposal path: legacy header signature verifies below H
        block = _block(LOW, HA, our_addr, signature=sign_block_hash(_block(LOW, HA, our_addr), our_key))
        assert _verify_block_signature_gated(block, our_addr)

        # attestation path: legacy message signature verifies below H
        msg = _header_msg(HB, V2, height=LOW)
        sig = sign_consensus_message(msg, our_key)
        assert _verify_attestation(msg, sig, our_addr, LOW)

    def test_T6_legacy_and_raw_hash_rejected_at_or_above_H(self, monkeypatch):
        """T6: at >= H the attestation path has NO legacy acceptance (no
        dual-accept armed) and the gated proposal path rejects both the
        legacy header preimage and the raw-hash fallback."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        our_addr, our_key, _, _ = _keys()

        # legacy attestation signature at >= H -> refused
        msg = _header_msg(HB, V2)
        legacy_sig = sign_consensus_message(msg, our_key)
        assert not _verify_attestation(msg, legacy_sig, our_addr, H)

        # legacy proposal (header-canonical) signature at >= H -> refused
        block = _block(H, HA, our_addr, signature=sign_block_hash(_block(H, HA, our_addr), our_key))
        assert not _verify_block_signature_gated(block, our_addr)

        # raw-hash (str preimage) signature at >= H -> refused on proposal path
        raw_hash = "0x" + "ab" * 32
        raw_block = _block(H, raw_hash, our_addr, signature=sign_block_hash(raw_hash, our_key))
        assert not _verify_block_signature_gated(raw_block, our_addr)
        # ... and on the attestation path (never had a raw-hash mode anyway)
        assert not _verify_attestation(_header_msg(raw_hash, V2), raw_block.signature, our_addr, H)


# ---------------------------------------------------------------------------
# T7 — round handling (T7a skipped: unconditional round auth not landed)
# ---------------------------------------------------------------------------


class TestRoundHandling:
    @pytest.mark.skip(
        reason="T7a depends on round being unconditionally inside the signed "
        "payload post-H (attestation_round_lock_enabled OFF); that slice is "
        "not landed — round only enters the preimage under round_lock today"
    )
    async def test_T7a_cross_round_same_key_attestations_both_accepted(self, monkeypatch, tmp_path):
        """Two honest attestations by one key at one height in DIFFERENT
        authenticated rounds must both verify (distinct uniqueness keys)."""

    @pytest.mark.asyncio
    async def test_T7b_same_round_rival_hash_refused_under_domain(self, monkeypatch, tmp_path):
        """T7b: same (height, round) with a different hash -> equivocation
        refuse, with domain separation armed. Round-lock posture."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", 1)
        svc, broker, our_addr, our_key, proposer_addr, _ = _round_lock_service(monkeypatch, tmp_path)

        await svc._handle_request(_rl_request(H, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 1
        resp = broker.published[0][1]
        # the published attestation is domain-separated and round-bound
        msg = _attestation_message(_rl_request(H, "0xaaaa", proposer_addr, 0)["header"], CHAIN, 0)
        assert verify_consensus_message_domain(msg, resp["signature"], our_addr, DOMAIN_BLOCK_ATTESTATION)
        assert not verify_consensus_message(msg, resp["signature"], our_addr)

        # same round, rival hash -> refused (no second signature released)
        await svc._handle_request(_rl_request(H, "0xbbbb", proposer_addr, 0))
        assert len(broker.published) == 1


# ---------------------------------------------------------------------------
# T8/T9 — evidence pairing scope + index-key coexistence
# ---------------------------------------------------------------------------


class TestEvidenceDomainScoping:
    def _seed_prior(self, svc, signer_addr, signer_key, block_hash, domain):
        """Retained prior signature + prior-hash index entry under ``domain``."""
        msg = _header_1278(block_hash, signer_addr if domain == DOMAIN_BLOCK_PROPOSAL else V2)
        signature = sign_consensus_message_domain(msg, signer_key, domain)
        svc._record_signed_attestation(H, block_hash, signer_addr, msg, None, False, signature, domain)
        svc._signed_once_add(H, block_hash, domain)
        return msg, signature

    def test_T8a_proposal_domain_pair_signs_and_verifies(self, monkeypatch):
        """T8: proposal<->proposal at one height pairs into gate-verifiable
        evidence under the proposal domain."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc, mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)
        self._seed_prior(svc, our_addr, our_key, HA, DOMAIN_BLOCK_PROPOSAL)

        msg_b = _header_1278(HB, our_addr)
        sig_b = sign_consensus_message_domain(msg_b, our_key, DOMAIN_BLOCK_PROPOSAL)
        svc.record_proposal_equivocation(msg_b, sig_b, 0)

        assert len(mgr.slashing_events) == 1
        evidence = event_signature_evidence(mgr.slashing_events[0])
        assert evidence is not None
        assert {a["signature_domain"] for a in evidence["attestations"]} == {DOMAIN_BLOCK_PROPOSAL}
        assert _verdict(mgr, our_addr) is None

    def test_T8b_attestation_domain_pair_signs_and_verifies(self, monkeypatch):
        """T8: attestation<->attestation at one height pairs under the
        attestation domain and verifies on-chain."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc, mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)
        self._seed_prior(svc, our_addr, our_key, HA, DOMAIN_BLOCK_ATTESTATION)

        msg_b = _header_1278(HB, V2)
        sig_b = sign_consensus_message_domain(msg_b, our_key, DOMAIN_BLOCK_ATTESTATION)
        svc._record_signed_attestation(H, HB, our_addr, msg_b, None, False, sig_b, DOMAIN_BLOCK_ATTESTATION)
        svc._record_attestation_equivocation_evidence(H, HB, our_addr, V2, None, signature_domain=DOMAIN_BLOCK_ATTESTATION)

        assert len(mgr.slashing_events) == 1
        evidence = event_signature_evidence(mgr.slashing_events[0])
        assert evidence is not None
        assert {a["signature_domain"] for a in evidence["attestations"]} == {DOMAIN_BLOCK_ATTESTATION}
        assert _verdict(mgr, our_addr) is None

    def test_T8c_cross_role_does_not_pair(self, monkeypatch):
        """T8: a proposal record and an attestation record for the same
        (height, signer) NEVER pair as equivocation — domain-scoped only."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc, mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)
        # prior PROPOSAL-domain signature at this height
        self._seed_prior(svc, our_addr, our_key, HA, DOMAIN_BLOCK_PROPOSAL)

        # now an ATTESTATION-domain rival signing -> pairs only within domain
        msg_b = _header_1278(HB, V2)
        sig_b = sign_consensus_message_domain(msg_b, our_key, DOMAIN_BLOCK_ATTESTATION)
        svc._record_signed_attestation(H, HB, our_addr, msg_b, None, False, sig_b, DOMAIN_BLOCK_ATTESTATION)
        svc._record_attestation_equivocation_evidence(H, HB, our_addr, V2, None, signature_domain=DOMAIN_BLOCK_ATTESTATION)

        # the only event is hash-only advisory — no signature pair across domains
        for event in mgr.slashing_events:
            assert event_signature_evidence(event) is None

    def test_T9_signed_attestation_key_domain_coexistence(self, monkeypatch):
        """T9: proposal and attestation records for the same
        (height, hash, signer) coexist under distinct index keys."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc = RemoteAttestationService(f"{CHAIN}-t9", {ADDR: ADDR_KEY})
        svc._signed_attestations_path = svc._signed_attestations_path.with_name("t9-signed.json")
        msg = _header_msg(HA, V2, chain_id=f"{CHAIN}-t9")

        for domain in (DOMAIN_BLOCK_ATTESTATION, DOMAIN_BLOCK_PROPOSAL):
            svc._record_signed_attestation(
                H,
                HA,
                ADDR,
                msg,
                None,
                False,
                sign_consensus_message_domain(msg, ADDR_KEY, domain),
                domain,
            )

        att_key = svc._signed_attestation_key(H, HA, ADDR, DOMAIN_BLOCK_ATTESTATION)
        prop_key = svc._signed_attestation_key(H, HA, ADDR, DOMAIN_BLOCK_PROPOSAL)
        assert att_key != prop_key
        assert svc._signed_attestations[att_key]["signature_domain"] == DOMAIN_BLOCK_ATTESTATION
        assert svc._signed_attestations[prop_key]["signature_domain"] == DOMAIN_BLOCK_PROPOSAL


# ---------------------------------------------------------------------------
# T10 — journal/lock uniqueness under domain separation (non-round-lock path)
# ---------------------------------------------------------------------------


class TestLockUniqueness:
    @pytest.mark.asyncio
    async def test_T10_second_same_domain_vote_refused_idempotent_same_hash(self, monkeypatch, tmp_path):
        """T10: at >= H the attester signs once per (height, hash) under the
        attestation domain — a rival hash is refused, the same hash
        re-publishes idempotently, and the durable journal record carries
        the domain tag. #1268/#1281 gates are not weakened (journal off in
        this posture; the lock itself is the gate under test)."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", 1)
        svc, broker, our_addr, our_key, proposer_addr, _ = _service(monkeypatch, tmp_path)

        await svc._handle_request(_request(H, "0xaaaa", proposer_addr))
        assert len(broker.published) == 1
        resp = broker.published[0][1]
        msg = _attestation_message(_request(H, "0xaaaa", proposer_addr)["header"], CHAIN)
        assert verify_consensus_message_domain(msg, resp["signature"], our_addr, DOMAIN_BLOCK_ATTESTATION)
        assert not verify_consensus_message(msg, resp["signature"], our_addr)

        # idempotent: same (height, hash) re-publishes, no new journal record
        await svc._handle_request(_request(H, "0xaaaa", proposer_addr))
        assert len(broker.published) == 2

        # rival hash at the same height -> refused outright
        await svc._handle_request(_request(H, "0xbbbb", proposer_addr))
        assert len(broker.published) == 2

        records = _attestation_records(svc)
        assert len(records) == 1
        assert records[0]["signature_domain"] == DOMAIN_BLOCK_ATTESTATION
        assert records[0]["h"] == H and records[0]["hash"] == "0xaaaa"


# ---------------------------------------------------------------------------
# T16 — underivable round is refused-to-count, never round-0
# ---------------------------------------------------------------------------


class TestUnderivableRound:
    @pytest.mark.asyncio
    async def test_T16_underivable_round_refused_never_round_zero(self, monkeypatch, tmp_path):
        """T16: with round_lock ON at >= H, a request whose round cannot be
        derived (parent row absent) is refused BEFORE signing — it is never
        counted as round 0 and releases no signature."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", 1)
        # parent_timestamp -> None makes _derive_request_round underivable
        svc, broker, our_addr, our_key, proposer_addr, _ = _round_lock_service(monkeypatch, tmp_path, parent_ts=None)

        await svc._handle_request(_rl_request(H, "0xaaaa", proposer_addr, 0))

        assert not broker.published
        assert not svc._round_locks  # nothing recorded — not even as round 0


# ---------------------------------------------------------------------------
# T17 — raw-hash fallback gated to height < H on both paths
# ---------------------------------------------------------------------------


class TestRawHashFallbackGate:
    def test_T17_raw_hash_signature_post_H_rejected_both_paths(self, monkeypatch):
        """T17: the legacy raw-SHA256-hash fallback in ``verify_block_signature``
        is unreachable at >= H — the gated proposal path requires the domain
        preimage, and the attestation path never accepts it either. Below H
        the fallback still verifies (historical replay preserved)."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        our_addr, our_key, _, _ = _keys()
        raw_hash = "0x" + "cd" * 32
        raw_sig = sign_block_hash(raw_hash, our_key)

        # proposal path at >= H: rejected
        assert not _verify_block_signature_gated(_block(H, raw_hash, our_addr, signature=raw_sig), our_addr)
        # attestation path at >= H: rejected
        assert not _verify_attestation(_header_msg(raw_hash, V2), raw_sig, our_addr, H)

        # below H the raw-hash fallback still verifies on the proposal path
        assert _verify_block_signature_gated(_block(LOW, raw_hash, our_addr, signature=raw_sig), our_addr)


# ---------------------------------------------------------------------------
# T18 — proposal-sig bytes on the attestation channel (reject legs landed)
# ---------------------------------------------------------------------------


class TestChannelAmbiguity:
    def test_T18_legacy_proposal_signature_rejected_on_attestation_channel(self, monkeypatch):
        """T18 (reject legs): legacy (pre-domain) signature bytes — identical
        for proposal and attestation since they share the preimage — offered
        on the attestation channel at >= H with NO dual-accept window armed
        are rejected, and the same bytes on the proposal path are rejected
        too (no proposal dual-accept, CARD5)."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        our_addr, our_key, _, _ = _keys()
        msg = _header_msg(HA, our_addr)
        legacy_sig = sign_consensus_message(msg, our_key)  # shared legacy preimage

        assert not _verify_attestation(msg, legacy_sig, our_addr, H)
        block = _block(H, HA, our_addr, signature=legacy_sig)
        assert not _verify_block_signature_gated(block, our_addr)

    @pytest.mark.skip(
        reason="T18 accept leg depends on the dual-accept window "
        "[H, S) via consensus_legacy_attestation_until_height — slice in "
        "flight, uncommitted; legacy attestation must count inside the "
        "window and be rejected at >= S"
    )
    def test_T18_legacy_attestation_counts_only_inside_window(self):
        """Inside [H,S) a legacy attestation signature counts toward
        threshold on the attestation channel (status-quo semantics); at
        >= S it is rejected. Metric consensus_legacy_attestation_accepted_total
        increments per acceptance."""


# ---------------------------------------------------------------------------
# T21/T22 — attestation-lock journal restart reseed + refuse-to-sign
# ---------------------------------------------------------------------------


class TestJournalReseedAndFailClosed:
    def _write_journal(self, path, records):
        path.write_text(json.dumps({"version": 1, "chain_id": CHAIN, "records": records}))

    def test_T21_legacy_journal_record_without_round_reseeds_conservatively(self, monkeypatch, tmp_path):
        """T21: a kind='attestation' journal record written by an older build
        (no derived_round / signature_domain fields) still reseeds the lock
        and signed-once memory — conservative full coverage, never a gap."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        our_addr, our_key, proposer_addr, _ = _keys()
        path = tmp_path / "locks.json"
        self._write_journal(
            path,
            [
                {
                    "kind": "attestation",
                    "h": H,
                    "hash": "0xaaaa",
                    "proposer": proposer_addr,
                    "signed_wall": time.time(),
                }
            ],
        )
        svc, _broker, *_ = _service(monkeypatch, tmp_path)
        svc._round_locks_path = path

        lock = svc.attestation_lock(H, float(ROUND_SECONDS))
        assert lock is not None and lock[0] == "0xaaaa"
        assert svc._signed_once_contains(H, "0xaaaa", None)

    @pytest.mark.asyncio
    async def test_T22_persist_failure_releases_no_signature(self, monkeypatch, tmp_path):
        """T22: if the durable journal write fails, the attestation is
        refused BEFORE any signature is released (fail-closed) — a retry
        cannot dedup into an unrecorded signing."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        svc, broker, our_addr, our_key, proposer_addr, _ = _service(monkeypatch, tmp_path)

        def _boom(self):
            raise OSError("disk full")

        monkeypatch.setattr(RemoteAttestationService, "_persist_round_locks", _boom)

        await svc._handle_request(_request(H, "0xaaaa", proposer_addr))

        assert not broker.published
        assert metrics_registry._counters.get("attestation_lock_persist_failure_total", 0.0) == 1.0
        # the in-memory lock was rolled back — nothing counts as signed
        assert svc.attestation_lock(H, float(ROUND_SECONDS)) is None


# ---------------------------------------------------------------------------
# Skipped rows — dependencies on not-yet-landed slices (see module docstring)
# ---------------------------------------------------------------------------


class TestPendingSlices:
    @pytest.mark.skip(
        reason="T11 proposer emission gate (proposal-signature journal refusing "
        "a second different-hash proposal at sign time) — not landed"
    )
    def test_T11_second_proposal_hash_refused_at_sign_time(self):
        """At >= H the proposer must refuse to sign a second different-hash
        proposal at the same height; same-hash resubmission stays idempotent."""

    @pytest.mark.skip(
        reason="T12 pin-expiry/abandon-height behaviour — pending AD ruling and the T11 emission gate / retry-ON semantics"
    )
    def test_T12_pin_expiry_abandon_height(self):
        """When the proposal pin expires or the tx-set drifts at >= H, the
        same proposer key emits nothing further at that height (per AD
        ruling); rotation moves to the next proposer."""

    @pytest.mark.skip(
        reason="T13 bounded dual-accept window [H,S) — depends on "
        "consensus_legacy_attestation_until_height slice (in flight, "
        "uncommitted): legacy attestation accepted inside the window, "
        "rejected at >= S, consensus_legacy_attestation_accepted_total "
        "metric, proposal path never dual-accepts"
    )
    def test_T13_dual_accept_window_bounds(self):
        """Legacy attestation signatures verify for message heights in
        [H, S) only; at >= S they are rejected; metric counts acceptances."""

    @pytest.mark.skip(
        reason="T14 declared-round mismatch refused post-H with round_lock "
        "OFF — depends on unconditional round authentication inside the "
        "signed payload (not landed)"
    )
    def test_T14_declared_round_mismatch_refused_round_lock_off(self):
        """Post-H a request whose declared round mismatches the derived
        round is refused even with attestation_round_lock_enabled OFF."""

    @pytest.mark.skip(
        reason="T15 intra-round lapse — depends on the effective lock-lapse "
        "window widening to round+max_age+future_skew (130 s defaults) "
        "shared by attester attestation_lock and proposer "
        "_honor_attestation_lock; current window is still "
        "consensus_proposer_round_seconds. Includes the future-skewed-header "
        "case and the restart-inside-window leg."
    )
    def test_T15_intra_round_lapse_same_derived_round(self):
        """Two hashes sharing one derived round: the second is refused even
        after the OLD 60 s window but inside the effective 130 s lapse;
        forged variant produces equivocation evidence."""

    @pytest.mark.skip(
        reason="T19 same-key rotation return (proposer round r+4 at the same "
        "height) — pending AD disposition (design v2.2 O5: literal ruling vs "
        "round-in-proposal-key vs expiry-exempt)"
    )
    def test_T19_rotation_return_same_key_r_plus_4(self):
        """When rotation returns the same validator key at round r+4 for the
        same height, proposal-signature behaviour follows the AD ruling."""

    @pytest.mark.skip(
        reason="T20 L4 mixed-version mesh leg — CARD6 sandbox-only leg run "
        "by E against an implementation SHA with per-node versions/flags "
        "recorded; not a unit test"
    )
    def test_T20_mixed_version_mesh_leg(self):
        """One node held on a pre-impl build while the fleet is pinned at H:
        bounded liveness degradation, no safety violation, raw journals "
        preserved."""
