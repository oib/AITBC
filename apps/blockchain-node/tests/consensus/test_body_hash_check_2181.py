"""#2181 — every proposal body must recompute to its block hash before it is stored.

The author's header signature covers the hash label and roots, not the
transaction list, so a signed, height-bound body can still carry a substituted
tx set. Followers would store it, PREPARE and commit-lock a hash no body matches
(importers reject it, the height wedges). Armed by ``pbft_body_hash_check_height``
on top of an active view-change gate; dormant otherwise.
"""

from __future__ import annotations

import pytest
from aitbc.crypto.consensus_signing import sign_block_hash
from aitbc_chain.config import settings
from aitbc_chain.consensus.pbft import PBFTMessage, PBFTMessageType
from aitbc_chain.consensus.pbft_view_change import body_hash_check_active
from aitbc_chain.metrics import metrics_registry

from .test_locked_cross_author_2171 import _real_body
from .test_pbft_view_change_2005 import (  # noqa: F401
    KEYS,
    MEMBERS,
    SEQ,
    _fresh_chain,  # fixture, used via usefixtures
    _make_consensus,
    _pbft,
    _proposal_body,
    _proposer,
)

PROPOSER = _proposer(SEQ, 0)

pytestmark = pytest.mark.usefixtures("_fresh_chain")


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()


@pytest.fixture
def vc_armed(monkeypatch):
    monkeypatch.setattr(settings, "pbft_view_change_height", 0)


@pytest.fixture
def armed(vc_armed, monkeypatch):
    monkeypatch.setattr(settings, "pbft_body_hash_check_height", 0)


def _substituted(author: str) -> dict:
    """A properly signed, height-bound body whose tx list was swapped after hashing."""
    body = _real_body(author)
    body["transactions"] = [{"tx_hash": "0xbbbb"}]  # hash label still covers 0xaa01/0xaa02
    body["tx_count"] = 1
    body["signature"] = sign_block_hash(body, KEYS[author])
    return body


def _engine():
    consensus = _make_consensus()
    return consensus, _pbft(consensus, MEMBERS[0], KEYS[MEMBERS[0]])


def _pp(body, sender=PROPOSER) -> PBFTMessage:
    return PBFTMessage(
        message_type=PBFTMessageType.PRE_PREPARE,
        sender=sender,
        view_number=0,
        sequence_number=SEQ,
        digest="d",
        signature="",
        timestamp=0.0,
        block_hash=body["hash"],
        block=body,
    )


def test_gate_requires_both_heights(monkeypatch):
    monkeypatch.setattr(settings, "pbft_view_change_height", None)
    monkeypatch.setattr(settings, "pbft_body_hash_check_height", 0)
    assert not body_hash_check_active(SEQ)  # view-change gate off
    monkeypatch.setattr(settings, "pbft_view_change_height", 0)
    monkeypatch.setattr(settings, "pbft_body_hash_check_height", None)
    assert not body_hash_check_active(SEQ)  # own height unset
    monkeypatch.setattr(settings, "pbft_body_hash_check_height", SEQ)
    assert body_hash_check_active(SEQ)
    assert not body_hash_check_active(SEQ - 1)  # below the arm height
    monkeypatch.setattr(settings, "pbft_body_hash_check_height", -1)
    assert not body_hash_check_active(SEQ)  # malformed -> dormant


def test_armed_refuses_a_substituted_own_author_body(armed):
    consensus, pbft = _engine()
    body = _substituted(PROPOSER)
    assert not pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER)
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is None
    assert metrics_registry._counters["pbft_view_change_proposal_hash_mismatch_total"] == 1


def test_armed_stores_an_honest_own_author_body(armed):
    consensus, pbft = _engine()
    body = _real_body(PROPOSER)
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER)
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is not None
    assert "pbft_view_change_proposal_hash_mismatch_total" not in metrics_registry._counters


def test_dormant_keeps_the_old_behaviour_byte_identical(vc_armed):
    """View-change armed but no body-hash height: the substituted body is stored as before."""
    consensus, pbft = _engine()
    body = _substituted(PROPOSER)
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER)
    assert "pbft_view_change_proposal_hash_mismatch_total" not in metrics_registry._counters


def test_heights_below_the_arm_height_are_dormant(vc_armed, monkeypatch):
    monkeypatch.setattr(settings, "pbft_body_hash_check_height", SEQ + 1)
    _consensus, pbft = _engine()
    body = _substituted(PROPOSER)
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER)


def test_body_with_a_fake_hash_label_is_refused_when_armed(armed):
    """The pre-existing test helper's bodies carry an arbitrary hash and do not recompute."""
    _consensus, pbft = _engine()
    body = _proposal_body(PROPOSER)
    assert not pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER)


@pytest.mark.asyncio
async def test_no_prepare_for_a_substituted_body_when_armed(armed):
    consensus, pbft = _engine()
    body = _substituted(PROPOSER)
    assert not await pbft._view_change_prepare_allows(SEQ, 0, _pp(body))
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is None


def test_proposer_refuses_to_pre_prepare_its_own_mismatching_body(armed):
    """The producer path stores its own body through the same check (fail closed)."""
    _consensus, pbft = _engine()
    local = pbft._local_validator
    body = _substituted(local)
    assert not pbft._vc_proposal_store(SEQ, body["hash"], body, local)
    assert metrics_registry._counters["pbft_view_change_proposal_hash_mismatch_total"] == 1
