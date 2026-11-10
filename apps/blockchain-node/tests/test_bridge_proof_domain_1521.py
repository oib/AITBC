"""#1521 BRIDGE-PROOF-DOMAIN-1: bridge proof header signatures are domain-aware.

Bridge proofs carry the sealed block's consensus signature plus validator
signatures over the same canonical header message. Since #1298 those are
domain-separated at/above ``consensus_domain_separation_height``: the block
signature mints under ``DOMAIN_BLOCK_PROPOSAL`` and validator attestations
under ``DOMAIN_BLOCK_ATTESTATION`` (legacy attestation preimages still
verify inside the bounded dual-accept window). Before this fix every bridge
verify path recovered over the raw legacy preimage only — post-activation
proofs could never verify, and pre-activation the shared preimage let one
signature serve both consensus channels.

These tests pin the height-gated domain table and the end-to-end proof
verify path on a real ``CrossChainBridge`` (same harness as
``test_bridge_proof_signature_augmentation``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc.bridge import build_verification_message
from aitbc.crypto.consensus_signing import (
    DOMAIN_BLOCK_ATTESTATION,
    DOMAIN_BLOCK_PROPOSAL,
    sign_consensus_message,
    sign_consensus_message_domain,
)
from aitbc_chain.config import bridge_header_signature_domains, bridge_header_signing_domain, settings
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block

# Sibling test-module import: only resolves under the app's own pyproject
# (pythonpath includes tests/). Under the repo-root pytest config the
# tests dir is not importable, so put it on sys.path explicitly (#1655).
_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from test_bridge_proof_signature_augmentation import (
    HEIGHT,
    SOURCE,
    TARGET,
    THRESHOLD,
    _header_message,
    _lock,
    _seal,
)

H = 5  # armed below HEIGHT=7 so the sealed test block sits post-activation


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    yield engine
    chain_metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def bridge(engine) -> CrossChainBridge:
    return CrossChainBridge(lambda: Session(engine))


@pytest.fixture
def proposer() -> EthAccount:
    return EthAccount.create()


@pytest.fixture
def validator_b() -> EthAccount:
    return EthAccount.create()


@pytest.fixture(autouse=True)
def _settings():
    with (
        patch("aitbc_chain.config.settings.supported_chains", f"{SOURCE},{TARGET}"),
        patch("aitbc_chain.config.settings.chain_id", SOURCE),
        patch("aitbc_chain.config.settings.block_scoped_preregistered_transactions", False),
        patch("aitbc_chain.config.settings.bridge_release_enabled", False),
        patch("aitbc_chain.config.settings.bridge_multisig_enabled", True),
        patch("aitbc_chain.config.settings.bridge_multisig_threshold", THRESHOLD),
        patch("aitbc_chain.config.settings.bridge_block_signature_required", True),
        patch("aitbc_chain.config.settings.bridge_lock_leaf_v2_height", None),
        patch("aitbc_chain.config.settings.validator_keys", ""),
        patch("aitbc_chain.config.settings.validator_set", ""),
        patch("aitbc_chain.config.settings.bridge_proof_attestation_timeout_seconds", 0.1),
        patch("aitbc_chain.config.settings.consensus_domain_separation_height", None),
        patch("aitbc_chain.config.settings.consensus_legacy_attestation_until_height", None),
    ):
        yield


def _arm(height: int | None, until: int | None = None) -> None:
    settings.consensus_domain_separation_height = height
    settings.consensus_legacy_attestation_until_height = until


def _sign_header(block: Block, private_key: str, domain: str | None) -> str:
    """Sign the canonical header message under ``domain`` (None = legacy)."""
    message = _header_message(block)
    if domain is None:
        return sign_consensus_message(message, private_key)
    return sign_consensus_message_domain(message, private_key, domain)


def _reseal_with_signature(engine, block: Block, signature: str, attestations: list[dict[str, str]] | None) -> None:
    """Rewrite the sealed block's signature/metadata in place (same hash)."""
    from sqlmodel import select

    with Session(engine) as session:
        row = session.exec(select(Block).where(Block.chain_id == SOURCE, Block.height == HEIGHT)).one()
        row.signature = signature
        row.block_metadata = json.dumps({"attestations": attestations}) if attestations is not None else None
        session.add(row)
        session.commit()


class TestDomainTable:
    """``bridge_header_signature_domains`` truth table."""

    def test_unset_activation_is_legacy_only(self):
        _arm(None)
        assert bridge_header_signature_domains(HEIGHT, "proposal") == [None]
        assert bridge_header_signature_domains(HEIGHT, "attestation") == [None]
        assert bridge_header_signing_domain(HEIGHT, "attestation") is None

    def test_below_activation_is_legacy_only(self):
        _arm(H)
        assert bridge_header_signature_domains(4, "proposal") == [None]  # 4 < H=5
        assert bridge_header_signature_domains(0, "attestation") == [None]

    def test_post_activation_hard_cutover_without_window(self):
        _arm(H)  # until=None -> no dual-accept window
        assert bridge_header_signature_domains(HEIGHT, "proposal") == [DOMAIN_BLOCK_PROPOSAL]
        assert bridge_header_signature_domains(HEIGHT, "attestation") == [DOMAIN_BLOCK_ATTESTATION]
        assert bridge_header_signing_domain(HEIGHT, "proposal") == DOMAIN_BLOCK_PROPOSAL
        assert bridge_header_signing_domain(HEIGHT, "attestation") == DOMAIN_BLOCK_ATTESTATION

    def test_dual_accept_window_keeps_legacy_attestation(self):
        _arm(H, until=H + 100)
        assert bridge_header_signature_domains(HEIGHT, "proposal") == [DOMAIN_BLOCK_PROPOSAL]
        assert bridge_header_signature_domains(HEIGHT, "attestation") == [DOMAIN_BLOCK_ATTESTATION, None]

    def test_past_window_is_domain_only(self):
        _arm(H, until=H + 1)
        assert bridge_header_signature_domains(H + 1, "attestation") == [DOMAIN_BLOCK_ATTESTATION]


class TestPostActivationProofVerification:
    """End-to-end: domain-signed proofs verify, legacy ones do not."""

    def _register(self, bridge: CrossChainBridge, proposer: EthAccount, validator_b: EthAccount) -> None:
        bridge.register_validator(SOURCE, proposer.address.lower(), "0x", 0)
        bridge.register_validator(SOURCE, validator_b.address.lower(), "0x", 0)

    def test_domain_signed_proof_verifies_post_activation(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        _arm(H)
        self._register(bridge, proposer, validator_b)
        tid = _lock(bridge, engine)
        block = _seal(bridge, engine, proposer, [tid], attestations=[])
        # Re-sign the block under the proposal domain and attest validator_b
        # under the attestation domain — what a post-activation fleet mints.
        sig_p = _sign_header(block, proposer.key.hex(), DOMAIN_BLOCK_PROPOSAL)
        sig_b = _sign_header(block, validator_b.key.hex(), DOMAIN_BLOCK_ATTESTATION)
        _reseal_with_signature(engine, block, sig_p, [{"validator": validator_b.address, "signature": sig_b}])
        # Refresh the mirrored header row the verifier reads.
        bridge.store_block_header(
            {
                "chain_id": SOURCE,
                "height": block.height,
                "hash": block.hash,
                "parent_hash": block.parent_hash,
                "proposer": block.proposer,
                "state_root": block.state_root or "",
                "bridge_state_root": block.bridge_state_root or "",
                "signature": sig_p,
                "confirmation_count": 10,
                "finality_confirmed": True,
            }
        )
        proof = bridge.build_proof(tid, source_chain=SOURCE)
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert header is not None
        assert bridge._verify_block_header_signature(header)
        assert bridge._verify_threshold_signatures(proof, header=header)

    def test_legacy_signed_proof_fails_post_activation(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        """Hard cutover: with S unset, a legacy preimage verifies nowhere."""
        _arm(H)
        self._register(bridge, proposer, validator_b)
        tid = _lock(bridge, engine)
        block = _seal(bridge, engine, proposer, [tid], attestations=[])
        sig_p = _sign_header(block, proposer.key.hex(), None)
        sig_b = _sign_header(block, validator_b.key.hex(), None)
        _reseal_with_signature(engine, block, sig_p, [{"validator": validator_b.address, "signature": sig_b}])
        bridge.store_block_header(
            {
                "chain_id": SOURCE,
                "height": block.height,
                "hash": block.hash,
                "parent_hash": block.parent_hash,
                "proposer": block.proposer,
                "state_root": block.state_root or "",
                "bridge_state_root": block.bridge_state_root or "",
                "signature": sig_p,
                "confirmation_count": 10,
                "finality_confirmed": True,
            }
        )
        proof = bridge.build_proof(tid, source_chain=SOURCE)
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert header is not None
        assert not bridge._verify_block_header_signature(header)
        assert not bridge._verify_threshold_signatures(proof, header=header)

    def test_below_activation_legacy_still_verifies(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        """Pre-activation behaviour is byte-identical: legacy preimage only."""
        _arm(HEIGHT + 1)  # armed above the sealed block's height
        self._register(bridge, proposer, validator_b)
        tid = _lock(bridge, engine)
        _seal(bridge, engine, proposer, [tid], attestations=[])
        with patch(
            "aitbc_chain.config.settings.validator_keys",
            json.dumps({validator_b.address: validator_b.key.hex()}),
        ):
            proof = bridge.build_proof(tid, source_chain=SOURCE)
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert header is not None
        assert bridge._verify_block_header_signature(header)
        assert bridge._verify_threshold_signatures(proof, header=header)

    def test_local_augmentation_signs_attestation_domain_post_activation(
        self, bridge: CrossChainBridge, engine: Any, proposer: EthAccount, validator_b: EthAccount
    ) -> None:
        """Empty sealed attestations: the top-up signature must mint under the
        attestation domain post-activation or the verifier cannot count it."""
        _arm(H)
        self._register(bridge, proposer, validator_b)
        tid = _lock(bridge, engine)
        block = _seal(bridge, engine, proposer, [tid], attestations=[])
        sig_p = _sign_header(block, proposer.key.hex(), DOMAIN_BLOCK_PROPOSAL)
        _reseal_with_signature(engine, block, sig_p, [])
        bridge.store_block_header(
            {
                "chain_id": SOURCE,
                "height": block.height,
                "hash": block.hash,
                "parent_hash": block.parent_hash,
                "proposer": block.proposer,
                "state_root": block.state_root or "",
                "bridge_state_root": block.bridge_state_root or "",
                "signature": sig_p,
                "confirmation_count": 10,
                "finality_confirmed": True,
            }
        )
        with patch(
            "aitbc_chain.config.settings.validator_keys",
            json.dumps({validator_b.address: validator_b.key.hex()}),
        ):
            proof = bridge.build_proof(tid, source_chain=SOURCE)
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert header is not None
        assert proof["validator_signatures"], "augmentation should have added a signature"
        assert bridge._verify_threshold_signatures(proof, header=header)


class TestSdkValidateBlockHeader:
    """``aitbc.bridge.validation.validate_block_header`` honours signature_domains."""

    def test_domain_signature_verifies_only_under_its_domain(self) -> None:
        from aitbc.bridge.types import BridgeBlockHeader, ValidatorInfo, ValidatorSet
        from aitbc.bridge.verification import validate_block_header

        account = EthAccount.create()
        key = account.key.hex()
        address = account.address
        header = BridgeBlockHeader(
            chain_id="c1",
            height=10,
            hash="0x" + "ab" * 32,
            parent_hash="0x" + "00" * 32,
            proposer=address.lower(),
            state_root="0x" + "11" * 32,
            bridge_state_root="",
        )
        vset = ValidatorSet(
            chain_id="c1",
            epoch=0,
            validators=[ValidatorInfo(address=address, public_key="0x", chain_id="c1", epoch=0)],
            threshold=1,
            total=1,
        )
        message = build_verification_message(header)
        header.signature = sign_consensus_message_domain(message, key, DOMAIN_BLOCK_PROPOSAL)

        valid, _err, _rec = validate_block_header(header, vset, signature_domains=[DOMAIN_BLOCK_PROPOSAL])
        assert valid
        # Legacy preimage recovers a DIFFERENT address — not a member -> invalid.
        valid, _err, _rec = validate_block_header(header, vset, signature_domains=[None])
        assert not valid
        valid, _err, _rec = validate_block_header(header, vset)  # default: legacy only
        assert not valid
