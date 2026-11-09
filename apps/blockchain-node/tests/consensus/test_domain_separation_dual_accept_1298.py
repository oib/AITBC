"""#1298 dual-accept migration window ``[H, S)`` — legacy attestation acceptance.

Pins ``consensus_legacy_attestation_until_height`` (S) semantics per design
v2.2 CARD5 / v2.6: inside ``[consensus_domain_separation_height, S)``
attestation-channel verification accepts EITHER the domain-separated
preimage OR the legacy shared preimage; at ``height >= S`` only the domain
preimage verifies; below H only the legacy preimage does; with S unset the
window never opens (hard cutover, byte-identical to the pre-window build).
Proposal signatures NEVER dual-accept — the proposal path stays hard
cutover at H regardless of S.
"""

from __future__ import annotations

from aitbc.crypto.consensus_signing import (
    DOMAIN_BLOCK_ATTESTATION,
    DOMAIN_BLOCK_PROPOSAL,
    sign_block_hash,
    sign_consensus_message,
    sign_consensus_message_domain,
)
from aitbc_chain.config import legacy_attestation_dual_accept_open, settings
from aitbc_chain.consensus.remote_attestation import _attestation_message, _verify_attestation
from aitbc_chain.consensus.slashing import SlashingManager
from aitbc_chain.sync import ProposerSignatureValidator
from aitbc_chain.metrics import metrics_registry
from aitbc_chain.state.deactivation_evidence import verify_deactivation_evidence

from .test_deactivation_evidence_1263 import (
    ADDR,
    ADDR_KEY,
    HA,
    HB,
    V2,
    _attestation_record,
    _v2_payload,
)

H = 50  # consensus_domain_separation_height
S = 150  # consensus_legacy_attestation_until_height — window [50, 150)
IN_WINDOW = 100
PAST_S = 200
BELOW_H = 40

LEGACY_METRIC = "consensus_legacy_attestation_accepted_total"


def _legacy_metric() -> float:
    return metrics_registry._counters.get(LEGACY_METRIC, 0.0)


def _arm(monkeypatch, *, until: int | None = S) -> None:
    monkeypatch.setattr(settings, "consensus_domain_separation_height", H)
    monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", until)


def _message(block_hash: str, *, height: int = IN_WINDOW, chain_id: str = "test-chain-1298") -> dict:
    return {
        "chain_id": chain_id,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x" + "00" * 32,
        "proposer": V2,
        "state_root": "0x" + "11" * 32,
        "bridge_state_root": "",
    }


def _sign(message: dict, key: str, domain: str | None) -> str:
    if domain is None:
        return sign_consensus_message(message, key)
    return sign_consensus_message_domain(message, key, domain)


class TestWindowHelper:
    """Truth table for ``legacy_attestation_dual_accept_open``."""

    def test_both_unset_is_inert(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", None)
        assert not legacy_attestation_dual_accept_open(IN_WINDOW)
        assert not legacy_attestation_dual_accept_open(H)
        assert not legacy_attestation_dual_accept_open(10**9)

    def test_until_unset_means_no_window(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", H)
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", None)
        assert not legacy_attestation_dual_accept_open(IN_WINDOW)
        assert not legacy_attestation_dual_accept_open(H)

    def test_activation_unset_means_no_window(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", S)
        assert not legacy_attestation_dual_accept_open(IN_WINDOW)

    def test_window_bounds(self, monkeypatch):
        _arm(monkeypatch)
        assert not legacy_attestation_dual_accept_open(BELOW_H)
        assert not legacy_attestation_dual_accept_open(H - 1)
        assert legacy_attestation_dual_accept_open(H)  # window is [H, S)
        assert legacy_attestation_dual_accept_open(IN_WINDOW)
        assert legacy_attestation_dual_accept_open(S - 1)
        assert not legacy_attestation_dual_accept_open(S)  # closed at S
        assert not legacy_attestation_dual_accept_open(PAST_S)
        assert not legacy_attestation_dual_accept_open(None)

    def test_until_at_or_below_activation_is_empty(self, monkeypatch):
        _arm(monkeypatch, until=H)
        assert not legacy_attestation_dual_accept_open(H)
        _arm(monkeypatch, until=H - 10)
        assert not legacy_attestation_dual_accept_open(IN_WINDOW)


class TestRemoteAttestationVerifyHelper:
    """``_verify_attestation`` — the collect-side attestation verify entry."""

    def _header(self, block_hash: str, *, height: int) -> dict:
        return {
            "chain_id": "test-chain-1298",
            "height": height,
            "hash": block_hash,
            "parent_hash": "0x" + "00" * 32,
            "proposer": V2,
            "state_root": "0x" + "11" * 32,
            "bridge_state_root": "",
        }

    def test_window_open_accepts_both_preimages(self, monkeypatch):
        _arm(monkeypatch)
        msg = _attestation_message(self._header(HA, height=IN_WINDOW), "test-chain-1298")
        legacy_sig = sign_consensus_message(msg, ADDR_KEY)
        domain_sig = sign_consensus_message_domain(msg, ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)
        proposal_sig = sign_consensus_message_domain(msg, ADDR_KEY, DOMAIN_BLOCK_PROPOSAL)

        before = _legacy_metric()
        assert _verify_attestation(msg, domain_sig, ADDR, IN_WINDOW)
        assert _legacy_metric() == before  # domain accept is not a legacy accept
        assert _verify_attestation(msg, legacy_sig, ADDR, IN_WINDOW)
        assert _legacy_metric() == before + 1
        # cross-domain never verifies, window or not
        assert not _verify_attestation(msg, proposal_sig, ADDR, IN_WINDOW)

    def test_window_closed_rejects_legacy(self, monkeypatch):
        _arm(monkeypatch)
        msg = _attestation_message(self._header(HA, height=PAST_S), "test-chain-1298")
        legacy_sig = sign_consensus_message(msg, ADDR_KEY)
        domain_sig = sign_consensus_message_domain(msg, ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)

        before = _legacy_metric()
        assert _verify_attestation(msg, domain_sig, ADDR, PAST_S)
        assert not _verify_attestation(msg, legacy_sig, ADDR, PAST_S)
        assert _legacy_metric() == before

    def test_below_activation_legacy_only(self, monkeypatch):
        _arm(monkeypatch)
        msg = _attestation_message(self._header(HA, height=BELOW_H), "test-chain-1298")
        legacy_sig = sign_consensus_message(msg, ADDR_KEY)
        domain_sig = sign_consensus_message_domain(msg, ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)

        assert _verify_attestation(msg, legacy_sig, ADDR, BELOW_H)
        assert not _verify_attestation(msg, domain_sig, ADDR, BELOW_H)

    def test_window_unset_is_hard_cutover(self, monkeypatch):
        _arm(monkeypatch, until=None)
        msg = _attestation_message(self._header(HA, height=IN_WINDOW), "test-chain-1298")
        legacy_sig = sign_consensus_message(msg, ADDR_KEY)
        domain_sig = sign_consensus_message_domain(msg, ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)

        assert _verify_attestation(msg, domain_sig, ADDR, IN_WINDOW)
        assert not _verify_attestation(msg, legacy_sig, ADDR, IN_WINDOW)

    def test_unarmed_byte_identical_legacy(self, monkeypatch):
        monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
        monkeypatch.setattr(settings, "consensus_legacy_attestation_until_height", None)
        msg = _attestation_message(self._header(HA, height=PAST_S), "test-chain-1298")
        legacy_sig = sign_consensus_message(msg, ADDR_KEY)
        domain_sig = sign_consensus_message_domain(msg, ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)

        assert _verify_attestation(msg, legacy_sig, ADDR, PAST_S)
        assert not _verify_attestation(msg, domain_sig, ADDR, PAST_S)


class TestSyncValidatorAttestationWindow:
    """``ProposerSignatureValidator._attestation_sig_ok`` import-side verify."""

    def _block(self, *, height: int, block_hash: str = HA) -> dict:
        return {
            "chain_id": "test-chain-1298",
            "height": height,
            "hash": block_hash,
            "parent_hash": "0x" + "00" * 32,
            "proposer": V2,
            "state_root": "0x" + "11" * 32,
            "bridge_state_root": "",
        }

    def _msg7(self, block: dict) -> dict:
        return {
            k: block[k] for k in ("chain_id", "height", "hash", "parent_hash", "proposer", "state_root", "bridge_state_root")
        }

    def _msg8(self, block: dict, round_: int) -> dict:
        msg = self._msg7(block)
        msg["round"] = round_
        return msg

    def test_window_accepts_legacy_and_domain(self, monkeypatch):
        _arm(monkeypatch)
        validator = ProposerSignatureValidator()
        block = self._block(height=IN_WINDOW)
        legacy_sig = sign_consensus_message(self._msg7(block), ADDR_KEY)
        domain_sig = sign_consensus_message_domain(self._msg7(block), ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)
        proposal_sig = sign_consensus_message_domain(self._msg7(block), ADDR_KEY, DOMAIN_BLOCK_PROPOSAL)

        before = _legacy_metric()
        assert validator._attestation_sig_ok(block, {"signature": domain_sig}, ADDR)
        assert _legacy_metric() == before
        assert validator._attestation_sig_ok(block, {"signature": legacy_sig}, ADDR)
        assert _legacy_metric() == before + 1
        assert not validator._attestation_sig_ok(block, {"signature": proposal_sig}, ADDR)

    def test_window_round_bound_legacy_accepted(self, monkeypatch):
        """A legacy 8-field (round-in-payload) attestation verifies in-window."""
        _arm(monkeypatch)
        validator = ProposerSignatureValidator()
        block = self._block(height=IN_WINDOW)
        msg8 = self._msg8(block, 2)
        legacy_sig = sign_consensus_message(msg8, ADDR_KEY)
        domain_sig = sign_consensus_message_domain(msg8, ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)

        assert validator._attestation_sig_ok(block, {"signature": legacy_sig, "round": 2}, ADDR)
        assert validator._attestation_sig_ok(block, {"signature": domain_sig, "round": 2}, ADDR)

    def test_window_closed_rejects_legacy(self, monkeypatch):
        _arm(monkeypatch)
        validator = ProposerSignatureValidator()
        block = self._block(height=PAST_S)
        legacy_sig = sign_consensus_message(self._msg7(block), ADDR_KEY)
        domain_sig = sign_consensus_message_domain(self._msg7(block), ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)

        assert validator._attestation_sig_ok(block, {"signature": domain_sig}, ADDR)
        assert not validator._attestation_sig_ok(block, {"signature": legacy_sig}, ADDR)

    def test_below_activation_legacy_only(self, monkeypatch):
        _arm(monkeypatch)
        validator = ProposerSignatureValidator()
        block = self._block(height=BELOW_H)
        legacy_sig = sign_consensus_message(self._msg7(block), ADDR_KEY)
        domain_sig = sign_consensus_message_domain(self._msg7(block), ADDR_KEY, DOMAIN_BLOCK_ATTESTATION)

        assert validator._attestation_sig_ok(block, {"signature": legacy_sig}, ADDR)
        assert not validator._attestation_sig_ok(block, {"signature": domain_sig}, ADDR)

    def test_window_does_not_open_raw_hash_fallback(self, monkeypatch):
        """Raw-hash-signed attestations stay rejected at/above H (design O4)."""
        _arm(monkeypatch)
        validator = ProposerSignatureValidator()
        block = self._block(height=IN_WINDOW)
        # sign_block_hash over a bare hash string = the legacy raw-hash preimage
        raw_sig = sign_block_hash(HA, ADDR_KEY)
        assert not validator._attestation_sig_ok(block, {"signature": raw_sig}, ADDR)


class TestProposalPathNeverDualAccepts:
    """CARD5/O4: the proposal verify path has NO window — legacy proposal
    signatures are rejected at/above H even inside [H, S)."""

    def _block(self, *, height: int) -> dict:
        return {
            "chain_id": "test-chain-1298",
            "height": height,
            "hash": HA,
            "parent_hash": "0x" + "00" * 32,
            "proposer": ADDR,
            "timestamp": "2026-01-01T00:00:00",
            "state_root": "0x" + "11" * 32,
            "bridge_state_root": "",
        }

    def test_legacy_proposal_signature_rejected_in_window(self, monkeypatch):
        _arm(monkeypatch)
        monkeypatch.setattr(settings, "bridge_block_signature_required", True)
        monkeypatch.setattr(settings, "multi_validator_consensus_enabled", False)
        validator = ProposerSignatureValidator()
        block = self._block(height=IN_WINDOW)
        legacy_sig = sign_block_hash(block, ADDR_KEY)
        domain_sig = sign_consensus_message_domain(
            {
                k: block[k]
                for k in ("chain_id", "height", "hash", "parent_hash", "proposer", "state_root", "bridge_state_root")
            },
            ADDR_KEY,
            DOMAIN_BLOCK_PROPOSAL,
        )

        ok, _ = validator.validate_block_signature({**block, "signature": legacy_sig})
        assert not ok
        ok, _ = validator.validate_block_signature({**block, "signature": domain_sig})
        assert ok


class TestDeactivationEvidenceWindow:
    """``_verify_stored_signature`` — unlabeled legacy records inside [H,S)."""

    def _equivocation_payload(self, mgr: SlashingManager, validator: str, attestations: list[dict], *, height: int):
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

    def _verdict(self, payload: dict) -> str | None:
        return verify_deactivation_evidence(
            payload,
            chain_id="test-chain",
            validator_addr=payload["validator_address"],
            evidence_hash=payload["evidence_hash"],
        )

    def _legacy_pair(self, *, height: int, round_in_payload: bool = False, request_round: int | None = None):
        return [
            _attestation_record(ADDR_KEY, HA, height=height, round_in_payload=round_in_payload, request_round=request_round),
            _attestation_record(ADDR_KEY, HB, height=height, round_in_payload=round_in_payload, request_round=request_round),
        ]

    def _domain_pair(self, *, height: int):
        def rec(block_hash: str) -> dict:
            message = _message(block_hash, height=height)
            return {
                "chain_id": message["chain_id"],
                "height": height,
                "hash": block_hash,
                "parent_hash": message["parent_hash"],
                "proposer": message["proposer"],
                "state_root": message["state_root"],
                "bridge_state_root": "",
                "round_in_payload": False,
                "request_round": None,
                "signature": sign_consensus_message_domain(message, ADDR_KEY, DOMAIN_BLOCK_ATTESTATION),
                "signer": ADDR,
                "signature_domain": DOMAIN_BLOCK_ATTESTATION,
            }

        return [rec(HA), rec(HB)]

    def test_window_open_accepts_unlabeled_legacy(self, monkeypatch):
        _arm(monkeypatch)
        mgr = SlashingManager()
        payload = self._equivocation_payload(mgr, ADDR, self._legacy_pair(height=IN_WINDOW), height=IN_WINDOW)
        assert self._verdict(payload) is None

    def test_window_open_accepts_round_bound_legacy(self, monkeypatch):
        _arm(monkeypatch)
        mgr = SlashingManager()
        payload = self._equivocation_payload(
            mgr,
            ADDR,
            self._legacy_pair(height=IN_WINDOW, round_in_payload=True, request_round=2),
            height=IN_WINDOW,
        )
        assert self._verdict(payload) is None

    def test_window_open_still_accepts_domain_labeled(self, monkeypatch):
        _arm(monkeypatch)
        mgr = SlashingManager()
        payload = self._equivocation_payload(mgr, ADDR, self._domain_pair(height=IN_WINDOW), height=IN_WINDOW)
        assert self._verdict(payload) is None

    def test_window_closed_rejects_unlabeled_legacy(self, monkeypatch):
        _arm(monkeypatch)
        mgr = SlashingManager()
        payload = self._equivocation_payload(mgr, ADDR, self._legacy_pair(height=PAST_S), height=PAST_S)
        assert self._verdict(payload) is not None

    def test_below_activation_accepts_unlabeled_legacy(self, monkeypatch):
        _arm(monkeypatch)
        mgr = SlashingManager()
        payload = self._equivocation_payload(mgr, ADDR, self._legacy_pair(height=BELOW_H), height=BELOW_H)
        assert self._verdict(payload) is None

    def test_window_unset_rejects_unlabeled_at_or_above_h(self, monkeypatch):
        _arm(monkeypatch, until=None)
        mgr = SlashingManager()
        payload = self._equivocation_payload(mgr, ADDR, self._legacy_pair(height=IN_WINDOW), height=IN_WINDOW)
        assert self._verdict(payload) is not None

    def test_empty_window_until_equals_h_rejects(self, monkeypatch):
        _arm(monkeypatch, until=H)
        mgr = SlashingManager()
        payload = self._equivocation_payload(mgr, ADDR, self._legacy_pair(height=IN_WINDOW), height=IN_WINDOW)
        assert self._verdict(payload) is not None
