"""#1298 evidence-store slice: ``signature_domain`` labels + domain-aware verify.

Pins the domain label stamped on signed-attestation/equivocation records at
the capture sites, domain-scoped pairing in the ``attestation_signed.json``
index, and the on-chain ``deactivation_evidence`` verifier's per-record
domain handling: labeled records verify under their recorded domain,
unlabeled (legacy) records only below ``consensus_domain_separation_height``.
"""

from __future__ import annotations

import pytest
from aitbc.crypto.consensus_signing import (
    DOMAIN_BLOCK_ATTESTATION,
    DOMAIN_BLOCK_PROPOSAL,
    sign_consensus_message,
    sign_consensus_message_domain,
    verify_consensus_message,
    verify_consensus_message_domain,
)
from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.config import settings
from aitbc_chain.consensus.slashing import SlashingManager, event_signature_evidence
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence

from .test_deactivation_evidence_1263 import (
    ADDR,
    ADDR_KEY,
    HA,
    HB,
    V2,
    _attestation_record,
    _attester_service,
    _request,
    _v2_payload,
)
from .test_proposer_equivocation_1278 import _header, _setup as _setup_1278

ACTIVATION = 50
H = 100  # at/above ACTIVATION — domain-separated territory

OTHER_ADDR = "0x" + "44" * 20


def _message(block_hash: str, proposer: str, *, height: int = H, chain_id: str = "test-chain-1298") -> dict:
    return {
        "chain_id": chain_id,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": proposer,
        "state_root": "0x" + "11" * 32,
        "bridge_state_root": "",
    }


def _domain_record(
    signer_key: str,
    block_hash: str,
    domain: str,
    *,
    height: int = H,
    signer_addr: str | None = None,
) -> dict:
    """One signature-bearing record as ``_record_signed_attestation`` emits it
    post-#1298: the domain tag on the record plus a domain-separated signature."""
    signer = signer_addr or derive_ethereum_address(signer_key)
    msg = _message(block_hash, V2, height=height)
    return {
        "chain_id": msg["chain_id"],
        "height": height,
        "hash": block_hash,
        "parent_hash": msg["parent_hash"],
        "proposer": V2,
        "state_root": msg["state_root"],
        "bridge_state_root": "",
        "round_in_payload": False,
        "request_round": None,
        "signature": sign_consensus_message_domain(msg, signer_key, domain),
        "signer": signer,
        "signature_domain": domain,
    }


def _equivocation_payload(mgr: SlashingManager, validator: str, attestations: list[dict], *, height: int = H):
    mgr.record_attestation_equivocation(
        validator_address=validator,
        height=height,
        round_number=None,
        block_hash_a=HA,
        block_hash_b=HB,
        proposer=V2,
        attestations=attestations,
    )
    return _v2_payload(mgr, validator)


def _verdict(payload: dict) -> str | None:
    return verify_deactivation_evidence(
        payload,
        chain_id="test-chain",
        validator_addr=payload["validator_address"],
        evidence_hash=payload["evidence_hash"],
    )


class TestCaptureStamping:
    @pytest.mark.asyncio
    async def test_attestation_record_stamps_domain_above_activation(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        signer_key = ADDR_KEY
        signer = derive_ethereum_address(signer_key)
        proposer_key = "0x" + "22" * 32
        proposer = derive_ethereum_address(proposer_key)
        svc, _broker = _attester_service(monkeypatch, signer, signer_key, proposer)

        await svc._handle_request(_request(H, HA, proposer))

        key = svc._signed_attestation_key(H, HA, signer, DOMAIN_BLOCK_ATTESTATION)
        rec = svc._signed_attestations[key]
        assert rec["signature_domain"] == DOMAIN_BLOCK_ATTESTATION
        message = {
            "chain_id": rec["chain_id"],
            "height": rec["height"],
            "hash": rec["hash"],
            "parent_hash": rec["parent_hash"],
            "proposer": rec["proposer"],
            "state_root": rec["state_root"],
            "bridge_state_root": rec["bridge_state_root"],
        }
        assert verify_consensus_message_domain(message, rec["signature"], signer, DOMAIN_BLOCK_ATTESTATION)
        # the signature is NOT a legacy shared-preimage signature anymore
        assert not verify_consensus_message(message, rec["signature"], signer)

    @pytest.mark.asyncio
    async def test_attestation_record_unlabeled_below_activation(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", H + 100)
        signer_key = ADDR_KEY
        signer = derive_ethereum_address(signer_key)
        proposer_key = "0x" + "22" * 32
        proposer = derive_ethereum_address(proposer_key)
        svc, _broker = _attester_service(monkeypatch, signer, signer_key, proposer)

        await svc._handle_request(_request(H, HA, proposer))

        key = svc._signed_attestation_key(H, HA, signer)
        rec = svc._signed_attestations[key]
        assert "signature_domain" not in rec  # byte-identical legacy record shape
        message = {
            "chain_id": rec["chain_id"],
            "height": rec["height"],
            "hash": rec["hash"],
            "parent_hash": rec["parent_hash"],
            "proposer": rec["proposer"],
            "state_root": rec["state_root"],
            "bridge_state_root": rec["bridge_state_root"],
        }
        assert verify_consensus_message(message, rec["signature"], signer)

    @pytest.mark.asyncio
    async def test_attestation_record_unlabeled_when_unarmed(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        signer_key = ADDR_KEY
        signer = derive_ethereum_address(signer_key)
        proposer_key = "0x" + "22" * 32
        proposer = derive_ethereum_address(proposer_key)
        svc, _broker = _attester_service(monkeypatch, signer, signer_key, proposer)

        await svc._handle_request(_request(H, HA, proposer))

        key = svc._signed_attestation_key(H, HA, signer)
        rec = svc._signed_attestations[key]
        assert "signature_domain" not in rec

    def test_proposal_equivocation_stamps_proposal_domain(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc, _mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)
        message = _header(HB, our_addr)  # height H >= ACTIVATION
        signature = sign_consensus_message_domain(message, our_key, DOMAIN_BLOCK_PROPOSAL)

        svc.record_proposal_equivocation(message, signature, 0)

        key = svc._signed_attestation_key(H, HB, our_addr, DOMAIN_BLOCK_PROPOSAL)
        rec = svc._signed_attestations[key]
        assert rec["signature_domain"] == DOMAIN_BLOCK_PROPOSAL
        # the legacy key must NOT hold this record — domains never collide
        assert svc._signed_attestation_key(H, HB, our_addr) not in svc._signed_attestations

    def test_proposal_and_attestation_records_coexist_same_hash_signer(self, monkeypatch):
        """T9: one (height, hash, signer) can hold one record per domain."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        signer_key = ADDR_KEY
        signer = derive_ethereum_address(signer_key)
        svc = RemoteAttestationService("test-chain-1298-coexist", {signer: signer_key})
        msg = _message(HA, V2)

        svc._record_signed_attestation(
            H,
            HA,
            signer,
            msg,
            None,
            False,
            sign_consensus_message_domain(msg, signer_key, DOMAIN_BLOCK_ATTESTATION),
            DOMAIN_BLOCK_ATTESTATION,
        )
        svc._record_signed_attestation(
            H,
            HA,
            signer,
            msg,
            None,
            False,
            sign_consensus_message_domain(msg, signer_key, DOMAIN_BLOCK_PROPOSAL),
            DOMAIN_BLOCK_PROPOSAL,
        )

        att_key = svc._signed_attestation_key(H, HA, signer, DOMAIN_BLOCK_ATTESTATION)
        prop_key = svc._signed_attestation_key(H, HA, signer, DOMAIN_BLOCK_PROPOSAL)
        assert att_key != prop_key
        assert svc._signed_attestations[att_key]["signature_domain"] == DOMAIN_BLOCK_ATTESTATION
        assert svc._signed_attestations[prop_key]["signature_domain"] == DOMAIN_BLOCK_PROPOSAL


class TestDomainScopedPairing:
    def _seed_domain_record(self, svc, signer_addr, signer_key, block_hash, domain):
        """A retained prior signature plus the prior-hash index entry."""
        msg = _header(block_hash, OTHER_ADDR if domain == DOMAIN_BLOCK_ATTESTATION else signer_addr)
        signature = sign_consensus_message_domain(msg, signer_key, domain)
        svc._record_signed_attestation(H, block_hash, signer_addr, msg, None, False, signature, domain)
        svc._signed_once.setdefault(H, set()).add(block_hash)

    def test_cross_role_prior_does_not_signature_pair(self, monkeypatch):
        """A proposal record pairs only with proposal records (#1298 v2.3)."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc, mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)
        # prior ATTESTATION-domain signature at this height for the same signer
        self._seed_domain_record(svc, our_addr, our_key, HA, DOMAIN_BLOCK_ATTESTATION)

        message = _header(HB, our_addr)
        signature = sign_consensus_message_domain(message, our_key, DOMAIN_BLOCK_PROPOSAL)
        svc.record_proposal_equivocation(message, signature, 0)

        assert len(mgr.slashing_events) == 1
        # cross-role: advisory hash-only record, no signature pair
        assert event_signature_evidence(mgr.slashing_events[0]) is None

    def test_same_domain_prior_signature_pairs_and_verifies(self, monkeypatch):
        """Two proposal-domain signatures at one height form gate-verifiable evidence."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        svc, mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)
        self._seed_domain_record(svc, our_addr, our_key, HA, DOMAIN_BLOCK_PROPOSAL)

        message = _header(HB, our_addr)
        signature = sign_consensus_message_domain(message, our_key, DOMAIN_BLOCK_PROPOSAL)
        svc.record_proposal_equivocation(message, signature, 0)

        assert len(mgr.slashing_events) == 1
        evidence = event_signature_evidence(mgr.slashing_events[0])
        assert evidence is not None
        domains = {a["signature_domain"] for a in evidence["attestations"]}
        assert domains == {DOMAIN_BLOCK_PROPOSAL}
        payload = _v2_payload(mgr, our_addr)
        assert _verdict(payload) is None

    def test_legacy_pairing_unchanged_when_unarmed(self, monkeypatch):
        """Below/without activation the index key and pairing are untouched."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        svc, mgr, our_addr, our_key, _, _ = _setup_1278(monkeypatch)
        msg = _header(HA, OTHER_ADDR)
        svc._record_signed_attestation(H, HA, our_addr, msg, None, False, sign_consensus_message(msg, our_key))
        svc._signed_once.setdefault(H, set()).add(HA)

        message = _header(HB, our_addr)
        svc.record_proposal_equivocation(message, sign_consensus_message(message, our_key), 0)

        assert len(mgr.slashing_events) == 1
        assert event_signature_evidence(mgr.slashing_events[0]) is not None
        payload = _v2_payload(mgr, our_addr)
        assert _verdict(payload) is None


class TestDomainAwareEvidenceVerify:
    def test_attestation_domain_pair_verifies(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        mgr = SlashingManager()
        payload = _equivocation_payload(
            mgr,
            ADDR,
            [
                _domain_record(ADDR_KEY, HA, DOMAIN_BLOCK_ATTESTATION),
                _domain_record(ADDR_KEY, HB, DOMAIN_BLOCK_ATTESTATION),
            ],
        )
        assert _verdict(payload) is None

    def test_proposal_domain_pair_verifies(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        mgr = SlashingManager()
        payload = _equivocation_payload(
            mgr,
            ADDR,
            [
                _domain_record(ADDR_KEY, HA, DOMAIN_BLOCK_PROPOSAL),
                _domain_record(ADDR_KEY, HB, DOMAIN_BLOCK_PROPOSAL),
            ],
        )
        assert _verdict(payload) is None

    def test_signature_fails_under_wrong_domain_label(self, monkeypatch):
        """Signed under ATTESTATION but labeled PROPOSAL — cross-domain reject."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        mgr = SlashingManager()
        records = [
            _domain_record(ADDR_KEY, HA, DOMAIN_BLOCK_ATTESTATION),
            _domain_record(ADDR_KEY, HB, DOMAIN_BLOCK_ATTESTATION),
        ]
        for rec in records:
            rec["signature_domain"] = DOMAIN_BLOCK_PROPOSAL
        payload = _equivocation_payload(mgr, ADDR, records)
        assert _verdict(payload) is not None

    def test_legacy_signature_with_domain_label_rejected(self, monkeypatch):
        """A pre-domain signature cannot be re-labeled as domain-separated."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        mgr = SlashingManager()
        records = [
            _attestation_record(ADDR_KEY, HA, height=H, round_in_payload=False, request_round=None),
            _attestation_record(ADDR_KEY, HB, height=H, round_in_payload=False, request_round=None),
        ]
        for rec in records:
            rec["signature_domain"] = DOMAIN_BLOCK_ATTESTATION
        payload = _equivocation_payload(mgr, ADDR, records)
        assert _verdict(payload) is not None

    def test_unlabeled_records_rejected_at_or_above_activation(self, monkeypatch):
        """Hard cutover: no legacy fallback for heights >= H."""
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        mgr = SlashingManager()
        payload = _equivocation_payload(
            mgr,
            ADDR,
            [
                _attestation_record(ADDR_KEY, HA, height=H, round_in_payload=False, request_round=None),
                _attestation_record(ADDR_KEY, HB, height=H, round_in_payload=False, request_round=None),
            ],
        )
        assert _verdict(payload) is not None

    def test_unlabeled_records_accepted_below_activation(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        mgr = SlashingManager()
        payload = _equivocation_payload(
            mgr,
            ADDR,
            [
                _attestation_record(ADDR_KEY, HA, height=ACTIVATION - 1, round_in_payload=False, request_round=None),
                _attestation_record(ADDR_KEY, HB, height=ACTIVATION - 1, round_in_payload=False, request_round=None),
            ],
            height=ACTIVATION - 1,
        )
        assert _verdict(payload) is None

    def test_unlabeled_records_accepted_when_unarmed(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        mgr = SlashingManager()
        payload = _equivocation_payload(
            mgr,
            ADDR,
            [
                _attestation_record(ADDR_KEY, HA, height=H, round_in_payload=False, request_round=None),
                _attestation_record(ADDR_KEY, HB, height=H, round_in_payload=False, request_round=None),
            ],
        )
        assert _verdict(payload) is None

    @pytest.mark.parametrize("bad_domain", [123, "", ["x"]])
    def test_malformed_domain_label_rejected(self, monkeypatch, bad_domain):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", ACTIVATION)
        mgr = SlashingManager()
        records = [
            _domain_record(ADDR_KEY, HA, DOMAIN_BLOCK_ATTESTATION),
            _domain_record(ADDR_KEY, HB, DOMAIN_BLOCK_ATTESTATION),
        ]
        for rec in records:
            rec["signature_domain"] = bad_domain
        payload = _equivocation_payload(mgr, ADDR, records)
        assert _verdict(payload) is not None
