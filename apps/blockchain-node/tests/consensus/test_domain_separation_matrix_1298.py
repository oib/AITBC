"""#1298 T1–T22 domain-separation test matrix (design v2.5/v2.6).

One pin per matrix row from the #1298 implementation plan (c23018 T1–T20,
c23383 +T21/T22). Rows that depend on not-yet-landed slices are
``pytest.mark.skip`` with the dependency named — they must NOT fake-pass:

- T11  proposer emission gate (proposal-signature journal refusing a second
       different-hash proposal at sign time)
- T12  pin-expiry / abandon-height behaviour (AD ruling + emission gate)
- T19  same-key rotation return at r+4 — pending AD disposition (v2.2 O5)
- T20  L4 mixed-version mesh leg (CARD6, sandbox-only, needs impl SHA)

Landed slices covered here: S0 domain helpers, S1 sign/verify gating,
S2 evidence ``signature_domain`` labels + attestation-lock journal,
S3 acceptance-key + bounded dual-accept window ``[H, S)`` via
``consensus_legacy_attestation_until_height`` (T13, T18w un-skipped),
T15 shared attestation-lock lapse constant (attester + proposer coupling,
height-gated on ``consensus_domain_separation_height``), and unconditional
round authentication post-H (T7a/T14: round inside the signed payload and
the declared-vs-derived refusal run whether or not
``attestation_round_lock_enabled`` is set).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

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
from aitbc_chain.config import ProposerConfig, legacy_attestation_dual_accept_open, settings
from aitbc_chain.consensus import poa as poa_module
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.multi_validator_poa import _verify_block_signature_gated
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.consensus.remote_attestation import (
    RemoteAttestationService,
    _attestation_message,
    _lock_lapse_seconds,
    _verify_attestation,
    attestation_lock_window_seconds,
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
# T7 — round handling
# ---------------------------------------------------------------------------


def _round_auth_service(
    monkeypatch, tmp_path, chain_id: str = CHAIN
) -> tuple[RemoteAttestationService, _StubBroker, str, str, str, str]:
    """Post-H round-auth posture: domain separation armed, round_lock OFF,
    parent timestamp resolvable, freshness bound off (fixed 2026 timestamps)."""
    monkeypatch.setattr(settings, "consensus_domain_separation_height", 1)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
    # skew stays at the 10s default: it feeds _lock_lapse_seconds(), so a
    # large value would stretch the post-H lock lapse the tests age against.
    monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 10.0)
    svc, broker, our_addr, our_key, proposer_addr, proposer_key = _service(monkeypatch, tmp_path, chain_id)
    svc._parent_timestamp = lambda p: PARENT_TS if p == "0xparent" else None  # type: ignore[method-assign]
    return svc, broker, our_addr, our_key, proposer_addr, proposer_key


class TestRoundHandling:
    @pytest.mark.asyncio
    async def test_T7a_cross_round_same_key_attestations_both_accepted(self, monkeypatch, tmp_path):
        """T7a: two honest attestations by one key at one height in DIFFERENT
        authenticated rounds both verify — each signature binds its own
        (hash, round) preimage, so the uniqueness keys are distinct. Runs
        with ``attestation_round_lock_enabled`` OFF: round authentication is
        unconditional post-H."""
        svc, broker, our_addr, our_key, proposer_addr, _ = _round_auth_service(monkeypatch, tmp_path)

        # round 0 attestation for hash A
        await svc._handle_request(_rl_request(H, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 1
        resp0 = broker.published[0][1]
        assert resp0["round"] == 0

        # lapse the attestation lock past its effective window, then a
        # round-1 attestation for a different hash — the honest
        # rotation/lapse case
        domain = DOMAIN_BLOCK_ATTESTATION
        svc._attested[H][domain] = (
            "0xaaaa",
            proposer_addr,
            time.monotonic() - (attestation_lock_window_seconds(H) + 1.0),
        )
        await svc._handle_request(_rl_request(H, "0xbbbb", proposer_addr, 1))
        assert len(broker.published) == 2
        resp1 = broker.published[1][1]
        assert resp1["round"] == 1

        # both signatures verify under their OWN (hash, round) preimage via
        # the real verify entry — distinct authenticated rounds, distinct
        # uniqueness keys
        msg0 = _attestation_message(_rl_request(H, "0xaaaa", proposer_addr, 0)["header"], CHAIN, 0)
        msg1 = _attestation_message(_rl_request(H, "0xbbbb", proposer_addr, 1)["header"], CHAIN, 1)
        assert _verify_attestation(msg0, resp0["signature"], our_addr, H)
        assert _verify_attestation(msg1, resp1["signature"], our_addr, H)
        # cross-binding fails: round-0 sig does not verify the round-1
        # preimage of either hash, and not even its own hash under round 1
        assert not verify_consensus_message_domain(msg1, resp0["signature"], our_addr, DOMAIN_BLOCK_ATTESTATION)
        assert not verify_consensus_message_domain(
            _attestation_message(_rl_request(H, "0xaaaa", proposer_addr, 0)["header"], CHAIN, 1),
            resp0["signature"],
            our_addr,
            DOMAIN_BLOCK_ATTESTATION,
        )
        # the durable journal records carry the authenticated rounds
        rounds = {r.get("derived_round") for r in _attestation_records(svc)}
        assert rounds == {0, 1}

        # import-side (sync_validator): sealed attestation entries verify per
        # their authenticated round — round-bound entries count, a
        # round-bound signature offered against the wrong round's block
        # does not, and an unbound 7-field domain attestation still verifies
        # through the msg7 fallback (mixed round-bound/unbound handling).
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        sv = ProposerSignatureValidator(parent_timestamp_resolver=lambda p: PARENT_TS)
        block_a = {
            "chain_id": CHAIN,
            "height": H,
            "hash": "0xaaaa",
            "parent_hash": "0xparent",
            "proposer": proposer_addr,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "timestamp": _block_ts(0).isoformat(),
        }
        block_b = {**block_a, "hash": "0xbbbb", "timestamp": _block_ts(1).isoformat()}
        assert sv._attestation_sig_ok(block_a, {"validator": our_addr, "signature": resp0["signature"], "round": 0}, our_addr)
        assert sv._attestation_sig_ok(block_b, {"validator": our_addr, "signature": resp1["signature"], "round": 1}, our_addr)
        assert not sv._attestation_sig_ok(
            block_b, {"validator": our_addr, "signature": resp0["signature"], "round": 0}, our_addr
        )
        unbound_sig = sign_consensus_message_domain(_attestation_message(block_a, CHAIN), our_key, DOMAIN_BLOCK_ATTESTATION)
        assert sv._attestation_sig_ok(block_a, {"validator": our_addr, "signature": unbound_sig}, our_addr)

    @pytest.mark.asyncio
    async def test_T7a_local_attestations_bind_round_post_H(self, monkeypatch):
        """T7a proposer leg: ``PoAProposer._collect_attestations`` signs the
        LOCAL attestation over the round-bound preimage at/above H even with
        round_lock OFF, seals the ``round`` hint importers need, and stays
        byte-identical legacy below H."""
        from aitbc_chain.base_models import Block
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        monkeypatch.setattr(settings, "consensus_domain_separation_height", 1)
        config = ProposerConfig(
            chain_id=CHAIN,
            proposer_id=V2,
            interval_seconds=5,
            max_block_size_bytes=1_000_000,
            max_txs_per_block=100,
        )
        proposer = PoAProposer(config=config, session_factory=lambda: None)  # type: ignore[arg-type,return-value]
        proposer._validator_keys = {ADDR: ADDR_KEY}
        proposer._remote_attestation = None

        def _block(height: int, block_hash: str, ts: datetime) -> Block:
            return Block(
                chain_id=CHAIN,
                height=height,
                hash=block_hash,
                parent_hash="0xparent",
                proposer=V2,
                timestamp=ts,
                tx_count=0,
                state_root="0xroot",
                bridge_state_root="",
            )

        # post-H: round 2 bound into the signed payload + sealed hint
        block = _block(H, "0xdddd", PARENT_TS + timedelta(seconds=121))
        attestations = await proposer._collect_attestations(block, round_number=2)
        assert len(attestations) == 1
        att = attestations[0]
        assert att["validator"] == ADDR
        assert att["round"] == "2"
        msg8 = {
            "chain_id": CHAIN,
            "height": H,
            "hash": "0xdddd",
            "parent_hash": "0xparent",
            "proposer": V2,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "round": 2,
        }
        assert verify_consensus_message_domain(msg8, att["signature"], ADDR, DOMAIN_BLOCK_ATTESTATION)
        # not the unbound preimage, not the legacy shared preimage
        msg7 = {k: v for k, v in msg8.items() if k != "round"}
        assert not verify_consensus_message_domain(msg7, att["signature"], ADDR, DOMAIN_BLOCK_ATTESTATION)
        assert not verify_consensus_message(msg7, att["signature"], ADDR)
        # import-side accepts the sealed entry (round hint present)
        sv = ProposerSignatureValidator()
        block_data = {
            "chain_id": CHAIN,
            "height": H,
            "hash": "0xdddd",
            "parent_hash": "0xparent",
            "proposer": V2,
            "state_root": "0xroot",
            "bridge_state_root": "",
            "timestamp": block.timestamp.isoformat(),
        }
        assert sv._attestation_sig_ok(block_data, att, ADDR)
        # ...and rejects it against a different declared round
        wrong = {**att, "round": "3"}
        assert not sv._attestation_sig_ok(block_data, wrong, ADDR)

        # below H: legacy 7-field shared preimage, no round anywhere
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        low_block = _block(LOW, "0xeeee", PARENT_TS + timedelta(seconds=121))
        low_atts = await proposer._collect_attestations(low_block, round_number=2)
        assert len(low_atts) == 1
        low_att = low_atts[0]
        assert "round" not in low_att
        low_msg = {
            "chain_id": CHAIN,
            "height": LOW,
            "hash": "0xeeee",
            "parent_hash": "0xparent",
            "proposer": V2,
            "state_root": "0xroot",
            "bridge_state_root": "",
        }
        assert verify_consensus_message(low_msg, low_att["signature"], ADDR)
        assert not verify_consensus_message_domain(low_msg, low_att["signature"], ADDR, DOMAIN_BLOCK_ATTESTATION)

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

    @pytest.mark.asyncio
    async def test_T14_declared_round_mismatch_refused_round_lock_off(self, monkeypatch, tmp_path):
        """T14: post-H a request whose declared round mismatches the derived
        round is refused even with ``attestation_round_lock_enabled`` OFF —
        the declared-vs-derived check is unconditional at/above the armed
        height. Underivable round and a missing declared round refuse the
        same way; below H the same mismatched request signs legacy."""
        svc, broker, our_addr, our_key, proposer_addr, _ = _round_auth_service(monkeypatch, tmp_path)

        # derived round is 0 (_block_ts(0)); declaring 1 must refuse
        bad = _rl_request(H, "0xaaaa", proposer_addr, 0)
        bad["header"]["round"] = 1
        await svc._handle_request(bad)
        assert not broker.published

        # no declared round at all -> declared=-1 != derived -> refuse
        undeclared = _rl_request(H, "0xaaaa", proposer_addr, 0)
        del undeclared["header"]["round"]
        await svc._handle_request(undeclared)
        assert not broker.published

        # underivable round (parent row absent) -> refuse, never round-0
        svc._parent_timestamp = lambda p: None  # type: ignore[method-assign]
        await svc._handle_request(_rl_request(H, "0xaaaa", proposer_addr, 0))
        assert not broker.published
        # nothing signed, so the durable lock journal was never written
        assert not svc._round_locks_path.exists()

        # below the armed height the identical mismatched request is legacy:
        # round is transport metadata only, the 7-field signature is released
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        low_req = _rl_request(LOW, "0xaaaa", proposer_addr, 0)
        low_req["header"]["round"] = 7  # bogus declared round — ignored below H
        await svc._handle_request(low_req)
        assert len(broker.published) == 1
        resp = broker.published[0][1]
        assert "round" not in resp  # legacy responses carry no round
        low_msg = _attestation_message(low_req["header"], CHAIN)
        assert verify_consensus_message(low_msg, resp["signature"], our_addr)
        assert not verify_consensus_message_domain(low_msg, resp["signature"], our_addr, DOMAIN_BLOCK_ATTESTATION)


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
        # Post-H requests must declare the derived round and carry the signed
        # block timestamp it derives from (T7a/T14 round authentication).
        # max_age=0 disables the freshness bound for the fixed 2026
        # timestamps; skew=70 keeps the effective lapse at 130s (60+0+70) so
        # the 70s/131s agings below land inside/outside it as intended.
        monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
        monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 70.0)
        svc, broker, our_addr, our_key, proposer_addr, _ = _service(monkeypatch, tmp_path)
        svc._parent_timestamp = lambda p: PARENT_TS if p == "0xparent" else None  # type: ignore[method-assign]

        await svc._handle_request(_rl_request(H, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 1
        resp = broker.published[0][1]
        assert resp["round"] == 0  # round-auth responses carry the round post-H
        req_header = _rl_request(H, "0xaaaa", proposer_addr, 0)["header"]
        # the attestation signature covers the round-bound 8-field message
        msg = _attestation_message(req_header, CHAIN, 0)
        assert verify_consensus_message_domain(msg, resp["signature"], our_addr, DOMAIN_BLOCK_ATTESTATION)
        assert not verify_consensus_message(msg, resp["signature"], our_addr)
        # ... and does NOT verify against the unbound 7-field preimage
        assert not verify_consensus_message_domain(
            _attestation_message(req_header, CHAIN), resp["signature"], our_addr, DOMAIN_BLOCK_ATTESTATION
        )

        # idempotent: same (height, hash) re-publishes, no new journal record
        await svc._handle_request(_rl_request(H, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 2

        # rival hash at the same height -> refused outright
        await svc._handle_request(_rl_request(H, "0xbbbb", proposer_addr, 0))
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

    def test_T18_legacy_attestation_counts_only_inside_window(self, monkeypatch):
        """Inside [H,S) a legacy attestation signature counts toward
        threshold on the attestation channel (status-quo semantics); at
        >= S it is rejected. Metric consensus_legacy_attestation_accepted_total
        increments per acceptance."""
        S = H + 50  # window [ACTIVATION, S) — H=100 sits inside it
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", S)
        our_addr, our_key, _, _ = _keys()
        legacy_metric = "consensus_legacy_attestation_accepted_total"
        before = metrics_registry._counters.get(legacy_metric, 0.0)

        # in-window: domain preimage verifies without touching the metric
        in_msg = _header_msg(HA, V2)
        domain_sig = sign_consensus_message_domain(in_msg, our_key, DOMAIN_BLOCK_ATTESTATION)
        assert _verify_attestation(in_msg, domain_sig, our_addr, H)
        assert metrics_registry._counters.get(legacy_metric, 0.0) == before

        # in-window: legacy shared preimage still counts — and is metered
        legacy_sig = sign_consensus_message(in_msg, our_key)
        assert _verify_attestation(in_msg, legacy_sig, our_addr, H)
        assert metrics_registry._counters.get(legacy_metric, 0.0) == before + 1

        # at >= S the same legacy signature is rejected outright
        past_msg = _header_msg(HB, V2, height=S)
        past_legacy = sign_consensus_message(past_msg, our_key)
        assert not _verify_attestation(past_msg, past_legacy, our_addr, S)
        past_domain = sign_consensus_message_domain(past_msg, our_key, DOMAIN_BLOCK_ATTESTATION)
        assert _verify_attestation(past_msg, past_domain, our_addr, S)


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
# T15 — shared attestation-lock lapse constant (design v2.2/v2.6)
# ---------------------------------------------------------------------------


class TestLapseWindow:
    def _proposer_with_attestation(self, svc: RemoteAttestationService) -> PoAProposer:
        sm = Mock()
        sm.pull_from_peer.return_value = True
        sm.pull_in_flight.return_value = False
        config = ProposerConfig(
            chain_id=CHAIN,
            proposer_id="test-proposer",
            interval_seconds=1.0,
            max_txs_per_block=10,
            max_block_size_bytes=1_000_000,
        )
        proposer = PoAProposer(config=config, session_factory=lambda: Mock(), sync_manager=sm)
        proposer._remote_attestation = svc  # type: ignore[attr-defined]
        return proposer

    def test_T15_shared_constant_attester_and_proposer_move_together(self, monkeypatch):
        """T15 core: ONE derived constant feeds both sides. At/above the
        armed activation height the binding window is the lapse
        (round+max_age+future_skew = 130s at defaults); below it the legacy
        60s round window stays. The proposer imports the identical function
        object, and moving the skew moves the shared value — attester and
        proposer cannot drift."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)

        # same function object on both sides — drift is impossible by construction
        assert poa_module.attestation_lock_window_seconds is attestation_lock_window_seconds
        assert attestation_lock_window_seconds is ra_module.attestation_lock_window_seconds

        # post-activation: the effective lapse, derived not literal
        assert attestation_lock_window_seconds(H) == pytest.approx(_lock_lapse_seconds())
        assert attestation_lock_window_seconds(H) == pytest.approx(130.0)
        # the crossing guarantee: lapse - max_age - future_skew == round window
        assert attestation_lock_window_seconds(H) - float(settings.attestation_header_max_age_seconds) - float(
            settings.attestation_header_future_skew_seconds
        ) == pytest.approx(float(ROUND_SECONDS))
        # pre-activation / unarmed: legacy round window, byte-identical
        assert attestation_lock_window_seconds(LOW) == pytest.approx(float(ROUND_SECONDS))
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        assert attestation_lock_window_seconds(H) == pytest.approx(float(ROUND_SECONDS))
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)

        # derived from settings: a future-skew change (the T15
        # future-skewed-header case) moves the shared window on both sides
        monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 25.0)
        assert attestation_lock_window_seconds(H) == pytest.approx(145.0)
        assert attestation_lock_window_seconds(LOW) == pytest.approx(float(ROUND_SECONDS))

    @pytest.mark.asyncio
    async def test_T15_attester_lock_binds_past_old_window_inside_lapse(self, monkeypatch, tmp_path):
        """T15 attester leg: at >= H a rival hash at the same height is
        still refused 70s after signing — past the OLD 60s window but inside
        the effective 130s lapse — and is accepted only after the lapse.
        Below H the legacy 60s window still releases at 70s (the resize is
        gated on the activation height, so pre-activation replay is
        unchanged)."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        # Post-H requests must declare the derived round (T7a/T14); the fixed
        # historical timestamps need the freshness bound off. skew=70 keeps
        # the effective lapse at 130s (60+0+70) so the 70s/131s agings land
        # inside/outside it as the test intends.
        monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
        monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 70.0)
        svc, broker, our_addr, our_key, proposer_addr, _ = _service(monkeypatch, tmp_path)
        svc._parent_timestamp = lambda p: PARENT_TS if p == "0xparent" else None  # type: ignore[method-assign]

        await svc._handle_request(_rl_request(H, "0xaaaa", proposer_addr, 0))
        assert len(broker.published) == 1

        # age the lock to 70s: past the old 60s round window, inside the lapse
        domain = DOMAIN_BLOCK_ATTESTATION
        svc._attested[H][domain] = ("0xaaaa", proposer_addr, time.monotonic() - 70.0)

        await svc._handle_request(_rl_request(H, "0xdddd", proposer_addr, 0))
        assert len(broker.published) == 1  # still refused — lapse binds

        # past the lapse the rival is accepted
        svc._attested[H][domain] = ("0xaaaa", proposer_addr, time.monotonic() - 131.0)
        await svc._handle_request(_rl_request(H, "0xdddd", proposer_addr, 0))
        assert len(broker.published) == 2

        # below the armed height the legacy 60s window applies unchanged
        await svc._handle_request(_request(LOW, "0xcccc", proposer_addr))
        assert len(broker.published) == 3
        svc._attested[LOW][None] = ("0xcccc", proposer_addr, time.monotonic() - 70.0)
        await svc._handle_request(_request(LOW, "0xeeee", proposer_addr))
        assert len(broker.published) == 4  # 70s > 60s legacy window -> accepted

    @pytest.mark.asyncio
    async def test_T15_proposer_honor_uses_same_lapse_window(self, monkeypatch, tmp_path):
        """T15 proposer leg: ``_honor_attestation_lock`` consults
        ``attestation_lock`` with the SAME ``attestation_lock_window_seconds``
        — a lock aged 70s at a post-activation height still suppresses the
        proposal (the old 60s window would have released it), while the
        same-aged lock below H does not."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        monkeypatch.setattr(settings, "gossip_mesh_peer_urls", "")
        svc, _broker, _our_addr, _our_key, proposer_addr, _ = _service(monkeypatch, tmp_path)
        proposer = self._proposer_with_attestation(svc)

        svc._attested[H] = {DOMAIN_BLOCK_ATTESTATION: ("0xaaaa", proposer_addr, time.monotonic() - 70.0)}
        assert await proposer._honor_attestation_lock(H) is True

        svc._attested[LOW] = {None: ("0xcccc", proposer_addr, time.monotonic() - 70.0)}
        assert await proposer._honor_attestation_lock(LOW) is False

    def test_T15_restart_inside_lapse_window_still_locked(self, monkeypatch, tmp_path):
        """T15 restart leg: a durable attestation-lock journal record 70s old
        (past the old 60s window, inside the 130s lapse) reseeds a LIVE lock
        at a post-activation height — and stays dead under the legacy window
        and at pre-activation heights."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        _our_addr, _our_key, proposer_addr, _ = _keys()
        path = tmp_path / "locks.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "chain_id": CHAIN,
                    "records": [
                        {
                            "kind": "attestation",
                            "h": H,
                            "hash": "0xaaaa",
                            "proposer": proposer_addr,
                            "signed_wall": time.time() - 70.0,
                            "derived_round": 1,
                            "signature_domain": DOMAIN_BLOCK_ATTESTATION,
                        },
                        {
                            "kind": "attestation",
                            "h": LOW,
                            "hash": "0xcccc",
                            "proposer": proposer_addr,
                            "signed_wall": time.time() - 70.0,
                        },
                    ],
                }
            )
        )
        svc, *_ = _service(monkeypatch, tmp_path)  # _round_locks_path already == path

        # post-activation height: 70s-old record still binds under the lapse
        lock = svc.attestation_lock(H, attestation_lock_window_seconds(H))
        assert lock is not None and lock[0] == "0xaaaa"
        # pre-activation height: same-aged record is dead under the 60s window
        assert svc.attestation_lock(LOW, attestation_lock_window_seconds(LOW)) is None

        # a fresh service proves the record only binds under the lapse:
        # the legacy 60s window drops it even at the post-activation height
        # (_service points _round_locks_path at tmp_path/"locks.json" == path)
        svc2, *_ = _service(monkeypatch, tmp_path)
        assert svc2.attestation_lock(H, float(ROUND_SECONDS)) is None


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

    def test_T13_dual_accept_window_bounds(self, monkeypatch):
        """Legacy attestation signatures verify for message heights in
        [H, S) only; at >= S they are rejected; metric counts acceptances.
        The proposal path never dual-accepts (CARD5)."""
        S = H + 50  # window [ACTIVATION, S); H=100 sits inside it
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", S)
        our_addr, our_key, _, _ = _keys()
        legacy_metric = "consensus_legacy_attestation_accepted_total"
        before = metrics_registry._counters.get(legacy_metric, 0.0)

        # config-level window truth table
        assert not legacy_attestation_dual_accept_open(LOW)
        assert legacy_attestation_dual_accept_open(H)
        assert legacy_attestation_dual_accept_open(S - 1)
        assert not legacy_attestation_dual_accept_open(S)
        assert not legacy_attestation_dual_accept_open(H + 10_000)

        # below H: legacy preimage only — the domain preimage is NOT accepted
        low_msg = _header_msg(HB, V2, height=LOW)
        assert _verify_attestation(low_msg, sign_consensus_message(low_msg, our_key), our_addr, LOW)
        assert not _verify_attestation(
            low_msg,
            sign_consensus_message_domain(low_msg, our_key, DOMAIN_BLOCK_ATTESTATION),
            our_addr,
            LOW,
        )

        # inside [H, S): BOTH preimages verify on the attestation channel;
        # only the legacy acceptance increments the migration metric
        in_msg = _header_msg(HA, V2)
        assert _verify_attestation(
            in_msg,
            sign_consensus_message_domain(in_msg, our_key, DOMAIN_BLOCK_ATTESTATION),
            our_addr,
            H,
        )
        assert _verify_attestation(in_msg, sign_consensus_message(in_msg, our_key), our_addr, H)
        assert metrics_registry._counters.get(legacy_metric, 0.0) == before + 1

        # at >= S: domain preimage only — legacy is rejected
        past_msg = _header_msg(HB, V2, height=S)
        assert not _verify_attestation(past_msg, sign_consensus_message(past_msg, our_key), our_addr, S)
        assert _verify_attestation(
            past_msg,
            sign_consensus_message_domain(past_msg, our_key, DOMAIN_BLOCK_ATTESTATION),
            our_addr,
            S,
        )

        # the proposal path NEVER dual-accepts: a legacy (shared-preimage)
        # signature at an in-window height is still rejected by the gated
        # proposal verify — sign over the block's own proposer field
        prop_msg = _header_msg(HA, our_addr)
        block = _block(H, HA, our_addr, signature=sign_consensus_message(prop_msg, our_key))
        assert not _verify_block_signature_gated(block, our_addr)

        # S unset = empty window: hard cutover, byte-identical to pre-window
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", None)
        assert not _verify_attestation(in_msg, sign_consensus_message(in_msg, our_key), our_addr, H)
        assert _verify_attestation(
            in_msg,
            sign_consensus_message_domain(in_msg, our_key, DOMAIN_BLOCK_ATTESTATION),
            our_addr,
            H,
        )

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
