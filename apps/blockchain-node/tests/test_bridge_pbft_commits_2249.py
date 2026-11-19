"""#2249: PBFT commit certificate as bridge-proof signer evidence.

VIEW_CHANGE-gated blocks are sealed from the PBFT commit certificate and carry
no attestations, so header signatures alone never reach the multisig threshold.
With ``bridge_pbft_commit_proof_height`` armed the proof carries the block's
commit votes and the verifier counts distinct validator-set committers.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from eth_account import Account as EthAccount
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from aitbc.crypto.consensus_signing import sign_consensus_message
from aitbc_chain.consensus.pbft_vote_signature import pbft_vote_preimage
from aitbc_chain.cross_chain.bridge import CrossChainBridge
from aitbc_chain.cross_chain.bridge_pbft_commits import (
    commit_proof_active,
    commits_from_metadata,
    verified_commit_signers,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Block

_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from test_bridge_proof_signature_augmentation import HEIGHT, SOURCE, TARGET, THRESHOLD, _lock, _seal

BLOCK_HASH = "0x" + "ab" * 32


def _commit(
    acct: EthAccount, block_hash: str = BLOCK_HASH, seq: int = 5, view: int = 1, chain_id: str | None = SOURCE
) -> dict[str, Any]:
    digest = hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest()
    rec: dict[str, Any] = {
        "message_type": "commit",
        "sender": acct.address,
        "view_number": view,
        "sequence_number": seq,
        "digest": digest,
        "block_hash": block_hash,
    }
    rec["signature"] = sign_consensus_message(pbft_vote_preimage(rec, chain_id), acct.key.hex())
    return rec


@pytest.fixture
def accts() -> list[EthAccount]:
    return [EthAccount.create() for _ in range(4)]


@pytest.fixture(autouse=True)
def _armed():
    with patch("aitbc_chain.config.settings.bridge_pbft_commit_proof_height", 1):
        yield


class TestVerifiedCommitSigners:
    def test_valid_commits_count_distinct_members(self, accts):
        commits = [_commit(a) for a in accts[:3]]
        out = verified_commit_signers(commits, BLOCK_HASH, SOURCE, [a.address for a in accts])
        assert {a.lower() for a in out} == {a.address.lower() for a in accts[:3]}

    def test_legacy_preimage_commit_still_verifies(self, accts):
        c = _commit(accts[0], chain_id=None)
        assert verified_commit_signers([c], BLOCK_HASH, SOURCE, [accts[0].address])

    def test_non_member_wrong_hash_bad_digest_bad_sig_rejected(self, accts):
        members = [a.address for a in accts[:2]]
        outsider = _commit(accts[3])
        other_block = _commit(accts[0], block_hash="0x" + "cd" * 32)
        bad_digest = _commit(accts[0])
        bad_digest["digest"] = "00" * 32
        forged = _commit(accts[1])
        forged["signature"] = _commit(accts[0])["signature"]
        assert verified_commit_signers([outsider, other_block, bad_digest, forged], BLOCK_HASH, SOURCE, members) == []

    def test_digest_binding_is_the_block_hash_binding(self, accts):
        """#2249 pin: a validly signed commit for block A replayed into block B.

        The vote preimage covers the digest, not block_hash, so the digest
        check is the sole binding between a commit and the proof's header.
        The commit below is self-consistent (right seq/view, member, valid
        signature over its own digest) but its digest is over a different
        block hash; with ``block_hash`` omitted or relabelled to this block
        it must still be rejected.
        """
        other_hash = "0x" + "cd" * 32
        members = [a.address for a in accts]
        replay_omitted = _commit(accts[0], block_hash=other_hash)
        replay_omitted.pop("block_hash")
        replay_relabelled = _commit(accts[1], block_hash=other_hash)
        replay_relabelled["block_hash"] = BLOCK_HASH
        assert verified_commit_signers([replay_omitted, replay_relabelled], BLOCK_HASH, SOURCE, members) == []
        # control: the same commits are accepted against the block they were signed for
        assert len(verified_commit_signers([replay_omitted], other_hash, SOURCE, members)) == 1

    def test_duplicate_sender_counts_once(self, accts):
        c = _commit(accts[0])
        assert len(verified_commit_signers([c, dict(c)], BLOCK_HASH, SOURCE, [accts[0].address])) == 1

    def test_mixed_views_are_not_unioned(self, accts):
        # one commit in view 1, one in view 2: best coherent group is size 1
        commits = [_commit(accts[0], view=1), _commit(accts[1], view=2)]
        out = verified_commit_signers(commits, BLOCK_HASH, SOURCE, [a.address for a in accts])
        assert len(out) == 1

    def test_non_dict_and_missing_fields_ignored(self, accts):
        commits: list[Any] = ["x", None, {"message_type": "commit"}, {"message_type": "prepare", "sender": accts[0].address}]
        assert verified_commit_signers(commits, BLOCK_HASH, SOURCE, [accts[0].address]) == []


class TestCommitsFromMetadata:
    def test_extracts_only_commits_with_sender_and_signature(self, accts):
        c = _commit(accts[0])
        meta = json.dumps(
            {
                "pbft_certificate": [
                    c,
                    {"message_type": "prepare", "sender": "0x1", "signature": "0x"},
                    {"message_type": "commit"},
                ]
            }
        )
        assert commits_from_metadata(meta) == [c]

    @pytest.mark.parametrize("meta", [None, "", "not json", "[]", json.dumps({"pbft_certificate": "x"})])
    def test_malformed_is_empty(self, meta):
        assert commits_from_metadata(meta) == []


def test_gate_table():
    with patch("aitbc_chain.config.settings.bridge_pbft_commit_proof_height", None):
        assert not commit_proof_active(100)
    with patch("aitbc_chain.config.settings.bridge_pbft_commit_proof_height", 10):
        assert not commit_proof_active(9)
        assert commit_proof_active(10)
        assert not commit_proof_active(None)


# ---- end to end on a real CrossChainBridge (same harness as #670/#1521) ----


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


def _seal_cert_only(bridge: CrossChainBridge, engine: Any, proposer: EthAccount, committers: list[EthAccount], **kw: Any):
    tid = _lock(bridge, engine)
    block = _seal(bridge, engine, proposer, [tid], attestations=[])
    certificate = [_commit(a, block_hash=block.hash, **kw) for a in committers]
    with Session(engine) as session:
        row = session.exec(select(Block).where(Block.chain_id == SOURCE, Block.height == HEIGHT)).one()
        row.block_metadata = json.dumps({"attestations": [], "pbft_certificate": certificate})
        session.add(row)
        session.commit()
    return tid


def _verify(bridge: CrossChainBridge, tid: str) -> tuple[dict[str, Any], bool]:
    proof = bridge.build_proof(tid, source_chain=SOURCE)
    header = bridge._get_block_header(SOURCE, HEIGHT)
    assert header is not None
    return proof, bridge._verify_threshold_signatures(proof, header=header)


class TestEndToEnd:
    def _register(self, bridge, proposer, others):
        for a in [proposer, *others]:
            bridge.register_validator(SOURCE, a.address.lower(), "0x", 0)

    def test_cert_only_block_verifies_with_commits(self, bridge, engine, accts):
        proposer, v1, v2, _ = accts
        self._register(bridge, proposer, [v1, v2])
        tid = _seal_cert_only(bridge, engine, proposer, [v1, v2])
        proof, ok = _verify(bridge, tid)
        assert len(proof["pbft_commits"]) == 2
        assert ok

    def test_gate_off_proof_has_no_field_and_fails(self, bridge, engine, accts):
        proposer, v1, v2, _ = accts
        self._register(bridge, proposer, [v1, v2])
        tid = _seal_cert_only(bridge, engine, proposer, [v1, v2])
        with patch("aitbc_chain.config.settings.bridge_pbft_commit_proof_height", None):
            proof, ok = _verify(bridge, tid)
        assert "pbft_commits" not in proof
        assert not ok  # proposer only: 1/2

    def test_verifier_gate_off_ignores_field_from_armed_builder(self, bridge, engine, accts):
        proposer, v1, v2, _ = accts
        self._register(bridge, proposer, [v1, v2])
        tid = _seal_cert_only(bridge, engine, proposer, [v1, v2])
        proof = bridge.build_proof(tid, source_chain=SOURCE)
        header = bridge._get_block_header(SOURCE, HEIGHT)
        with patch("aitbc_chain.config.settings.bridge_pbft_commit_proof_height", None):
            assert not bridge._verify_threshold_signatures(proof, header=header)

    def test_non_member_committers_do_not_count(self, bridge, engine, accts):
        proposer, v1, outsider, _ = accts
        self._register(bridge, proposer, [v1])
        tid = _seal_cert_only(bridge, engine, proposer, [outsider])
        _, ok = _verify(bridge, tid)
        assert not ok

    def test_tampered_commit_signature_rejected(self, bridge, engine, accts):
        proposer, v1, v2, _ = accts
        self._register(bridge, proposer, [v1, v2])
        tid = _seal_cert_only(bridge, engine, proposer, [v1, v2])
        proof = bridge.build_proof(tid, source_chain=SOURCE)
        a, b = proof["pbft_commits"][0], proof["pbft_commits"][1]
        a["signature"], b["signature"] = b["signature"], a["signature"]  # both now invalid for their sender
        header = bridge._get_block_header(SOURCE, HEIGHT)
        assert not bridge._verify_threshold_signatures(proof, header=header)
