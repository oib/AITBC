"""#2171 — a commit-locked height is re-proposed by the round's proposer even when
someone else authored the body.

#2157 only let the lock holder re-propose, and only if it also authored the body
(R4: body.proposer == pre-prepare sender). With lock holder != author the next
proposer built a fresh block that every follower refused (``have=0``). Armed by
``pbft_locked_cross_author_height``: the scheduled proposer re-proposes the
locked hash from a locked NEW_VIEW, fetching the body if it lacks it, and
followers accept the author-signed body under a narrow R4 exemption.
"""

from __future__ import annotations

import pytest
from aitbc.crypto.consensus_signing import sign_block_hash
from aitbc_chain.config import settings
from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.consensus.pbft_view_change import PB_MESSAGE_TYPE, PF_MESSAGE_TYPE
from aitbc_chain.metrics import metrics_registry

from .test_pbft_view_change_2005 import (  # noqa: F401
    HA,
    HB,
    KEYS,
    MEMBERS,
    SEQ,
    VIEW,
    _fresh_chain,  # fixture, used via usefixtures
    _FakeGossip,
    _make_consensus,
    _nv,
    _pbft,
    _proposal_body,
    _proposer,
    _true,
    _vc_set,
)

PROPOSER = _proposer(SEQ, VIEW)
AUTHOR = next(m for m in MEMBERS if m != PROPOSER)
OTHER = next(m for m in MEMBERS if m not in (PROPOSER, AUTHOR))


pytestmark = pytest.mark.usefixtures("_fresh_chain")


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()


def _real_body(author: str, tx_hashes=("0xaa01", "0xaa02"), seq: int = SEQ) -> dict:
    """An author-signed proposal body whose ``hash`` really recomputes (#2171 rework)."""
    body = _proposal_body(author)
    body["transactions"] = [{"tx_hash": h} for h in tx_hashes]
    body["tx_count"] = len(tx_hashes)
    body["height"] = seq
    body["hash"] = compute_block_hash(
        body["chain_id"],
        seq,
        body["parent_hash"],
        body["timestamp"],
        list(tx_hashes),
        author,
        body["state_root"],
        body["bridge_state_root"],
        body["aux_state_root"],
    )
    body["signature"] = sign_block_hash(body, KEYS[author])
    return body


@pytest.fixture
def body(_fresh_chain):  # noqa: F811
    """The author's real locked body; ``body["hash"]`` is the locked hash."""
    return _real_body(AUTHOR)


@pytest.fixture
def vc_armed(monkeypatch):
    monkeypatch.setattr(settings, "pbft_view_change_height", 0)


@pytest.fixture
def armed(vc_armed, monkeypatch):
    monkeypatch.setattr(settings, "pbft_locked_cross_author_height", 0)


async def _locked_nv(pbft, locked_hash, seq=SEQ, view=VIEW):
    senders = [m for m in MEMBERS if m != PROPOSER][:3]
    vcs = _vc_set(seq, view, senders, locked_hash=locked_hash, lock_view=0)
    nv = _nv(PROPOSER, seq, view, vcs, locked_hash)
    await pbft._handle_new_view_payload(nv)
    assert (seq, view) in pbft._new_views
    return nv


async def _free_nv(pbft):
    senders = [m for m in MEMBERS if m != PROPOSER][:3]
    nv = _nv(PROPOSER, SEQ, VIEW, _vc_set(SEQ, VIEW, senders), None)
    await pbft._handle_new_view_payload(nv)
    return nv


async def _run_proposal(pbft, monkeypatch):
    calls = []

    async def fake_pre_prepare(proposer, block_hash, sequence=None, view=None, block_payload=None, new_view_payload=None):
        calls.append((block_hash, block_payload))
        return True

    monkeypatch.setattr(pbft, "pre_prepare_phase", fake_pre_prepare)
    monkeypatch.setattr(pbft, "_ensure_synced", lambda: _true())
    await pbft.propose_and_wait(
        PROPOSER, HB, timeout=0.01, sequence=SEQ, view=VIEW, block_payload=_proposal_body(PROPOSER, HB)
    )
    return calls


def _proposer_engine(body=None):
    consensus = _make_consensus()
    pbft = _pbft(consensus, PROPOSER, KEYS[PROPOSER])
    pbft._gossip_backend = _FakeGossip()
    if body is not None:
        assert consensus.pbft_vc_proposal_store(SEQ, body["hash"], body)
    return consensus, pbft


def _pb(body, block_hash=None):
    return {
        "message_type": PB_MESSAGE_TYPE,
        "sequence_number": SEQ,
        "block_hash": block_hash or body["hash"],
        "block": body,
    }


# --- proposer side -----------------------------------------------------------


@pytest.mark.asyncio
async def test_non_author_proposer_reproposes_the_locked_block(armed, body, monkeypatch):
    _c, pbft = _proposer_engine(body)
    await _locked_nv(pbft, body["hash"])
    calls = await _run_proposal(pbft, monkeypatch)
    assert calls[0][0] == body["hash"]
    assert calls[0][1]["proposer"] == AUTHOR  # the author's signed body, untouched


@pytest.mark.asyncio
async def test_unarmed_cross_author_keeps_the_fresh_block(vc_armed, body, monkeypatch):
    monkeypatch.setattr(settings, "pbft_locked_cross_author_height", None)
    _c, pbft = _proposer_engine(body)
    await _locked_nv(pbft, body["hash"])
    calls = await _run_proposal(pbft, monkeypatch)
    assert calls[0][0] == HB


@pytest.mark.asyncio
async def test_height_below_the_arm_height_is_dormant(vc_armed, body, monkeypatch):
    monkeypatch.setattr(settings, "pbft_locked_cross_author_height", SEQ + 1)
    _c, pbft = _proposer_engine(body)
    await _locked_nv(pbft, body["hash"])
    assert (await _run_proposal(pbft, monkeypatch))[0][0] == HB


@pytest.mark.asyncio
async def test_free_new_view_proposes_the_fresh_block(armed, body, monkeypatch):
    _c, pbft = _proposer_engine(body)
    await _free_nv(pbft)
    assert (await _run_proposal(pbft, monkeypatch))[0][0] == HB


@pytest.mark.asyncio
async def test_missing_body_is_fetched_then_reproposed(armed, body, monkeypatch):
    _c, pbft = _proposer_engine()
    await _locked_nv(pbft, body["hash"])
    gossip = pbft._gossip_backend
    publish = gossip.publish

    async def publish_and_answer(topic, payload):
        await publish(topic, payload)
        if payload.get("message_type") == PF_MESSAGE_TYPE:
            await pbft.handle_incoming_message(_pb(body))

    monkeypatch.setattr(gossip, "publish", publish_and_answer)
    calls = await _run_proposal(pbft, monkeypatch)
    assert calls[0][0] == body["hash"]
    assert any(p["message_type"] == PF_MESSAGE_TYPE for _t, p in gossip.published)
    assert metrics_registry._counters["pbft_locked_body_fetch_stored_total"] == 1


@pytest.mark.asyncio
async def test_fetch_gives_up_and_proposes_fresh_when_nobody_answers(armed, body, monkeypatch):
    from aitbc_chain.consensus import pbft as pbft_mod

    monkeypatch.setattr(pbft_mod, "BODY_FETCH_WAIT_SECONDS", 0.3)
    _c, pbft = _proposer_engine()
    await _locked_nv(pbft, body["hash"])
    assert (await _run_proposal(pbft, monkeypatch))[0][0] == HB
    assert not pbft._body_wanted  # bookkeeping cleaned up


# --- fetch bookkeeping -------------------------------------------------------


@pytest.mark.asyncio
async def test_unsolicited_body_is_ignored(armed, body):
    consensus, pbft = _proposer_engine()
    await pbft.handle_incoming_message(_pb(body))
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is None


@pytest.mark.asyncio
async def test_solicited_but_unsigned_or_unbound_body_is_refused(armed, body):
    consensus, pbft = _proposer_engine()
    pbft._body_wanted[(SEQ, body["hash"])] = VIEW
    bad_sig = dict(body)
    bad_sig["signature"] = "0xdeadbeef"
    unbound = _real_body(AUTHOR)
    unbound["hash"] = HB
    for bad in (bad_sig, unbound):
        await pbft.handle_incoming_message(_pb(bad, body["hash"]))
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is None
    assert metrics_registry._counters["pbft_locked_body_fetch_refused_total"] == 2


@pytest.mark.asyncio
async def test_substituted_tx_set_under_a_valid_header_is_refused(armed, body):
    """Validator PoC: label + header signature intact, transactions swapped."""
    consensus, pbft = _proposer_engine()
    pbft._body_wanted[(SEQ, body["hash"])] = VIEW
    forged = dict(body)
    forged["transactions"] = [{"tx_hash": "0xbad1"}]
    from aitbc_chain.consensus.pbft_view_change import proposal_body_bound, proposal_body_signed

    assert proposal_body_bound(forged, body["hash"], SEQ) and proposal_body_signed(forged)  # old checks pass
    await pbft.handle_incoming_message(_pb(forged, body["hash"]))
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is None
    assert metrics_registry._counters["pbft_locked_body_fetch_refused_total"] == 1
    pbft._body_wanted[(SEQ, body["hash"])] = VIEW  # the genuine body still lands afterwards
    await pbft.handle_incoming_message(_pb(body))
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is not None


@pytest.mark.asyncio
async def test_holder_answers_a_fetch_once_per_window_and_only_when_armed(armed, body, monkeypatch):
    _c, pbft = _proposer_engine(body)  # holds the body
    await _locked_nv(pbft, body["hash"])
    req = {"message_type": PF_MESSAGE_TYPE, "sequence_number": SEQ, "view_number": VIEW, "block_hash": body["hash"]}
    await pbft.handle_incoming_message(req)
    await pbft.handle_incoming_message(req)  # rate limited
    answers = [p for _t, p in pbft._gossip_backend.published if p["message_type"] == PB_MESSAGE_TYPE]
    assert len(answers) == 1 and answers[0]["block"]["hash"] == body["hash"]
    monkeypatch.setattr(settings, "pbft_locked_cross_author_height", None)
    pbft._fetch_answered.clear()
    await pbft.handle_incoming_message(req)
    assert len([p for _t, p in pbft._gossip_backend.published if p["message_type"] == PB_MESSAGE_TYPE]) == 1


@pytest.mark.asyncio
async def test_holder_serves_only_the_forced_hash(armed, body):
    consensus, pbft = _proposer_engine(body)
    other = _real_body(AUTHOR, tx_hashes=("0xcc01",))
    assert consensus.pbft_vc_proposal_store(SEQ, other["hash"], other)  # held, but not locked
    await _locked_nv(pbft, body["hash"])
    for h in (other["hash"],):
        await pbft.handle_incoming_message(
            {"message_type": PF_MESSAGE_TYPE, "sequence_number": SEQ, "view_number": VIEW, "block_hash": h}
        )
    assert not [p for _t, p in pbft._gossip_backend.published if p["message_type"] == PB_MESSAGE_TYPE]


@pytest.mark.asyncio
async def test_rate_limit_table_is_never_reset_by_a_flood(armed, body):
    from aitbc_chain.consensus.pbft import MAX_BODY_WANTED

    _c, pbft = _proposer_engine(body)
    await _locked_nv(pbft, body["hash"])
    import time as _t

    now = _t.time()
    for i in range(MAX_BODY_WANTED):
        pbft._fetch_answered[(SEQ, f"0x{i:064x}")] = now  # live, fresh entries
    req = {"message_type": PF_MESSAGE_TYPE, "sequence_number": SEQ, "view_number": VIEW, "block_hash": body["hash"]}
    await pbft.handle_incoming_message(req)
    assert len(pbft._fetch_answered) == MAX_BODY_WANTED  # not cleared, request dropped
    assert not [p for _t2, p in pbft._gossip_backend.published if p["message_type"] == PB_MESSAGE_TYPE]


# --- follower side: the narrow R4 exemption ----------------------------------


def _follower():
    consensus = _make_consensus()
    return consensus, _pbft(consensus, OTHER, KEYS[OTHER])


@pytest.mark.asyncio
async def test_follower_accepts_the_authors_body_from_the_scheduled_proposer(armed, body):
    consensus, pbft = _follower()
    await _locked_nv(pbft, body["hash"])
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER, VIEW) is True
    assert consensus.pbft_vc_proposal_get(SEQ, body["hash"]) is not None


@pytest.mark.asyncio
async def test_exemption_refuses_a_substituted_tx_set(armed, body):
    _c, pbft = _follower()
    await _locked_nv(pbft, body["hash"])
    forged = dict(body)
    forged["transactions"] = [{"tx_hash": "0xbad1"}]
    assert pbft._vc_proposal_store(SEQ, body["hash"], forged, PROPOSER, VIEW) is False


@pytest.mark.asyncio
async def test_r4_still_refuses_without_a_locked_new_view(armed, body):
    _c, pbft = _follower()
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER, VIEW) is False


@pytest.mark.asyncio
async def test_r4_still_refuses_under_a_free_new_view(armed, body):
    _c, pbft = _follower()
    await _free_nv(pbft)
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER, VIEW) is False


@pytest.mark.asyncio
async def test_r4_still_refuses_a_hash_the_new_view_did_not_force(armed, body):
    _c, pbft = _follower()
    await _locked_nv(pbft, HB)
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER, VIEW) is False


@pytest.mark.asyncio
async def test_r4_still_refuses_a_sender_that_is_not_the_new_view_proposer(armed, body):
    _c, pbft = _follower()
    await _locked_nv(pbft, body["hash"])
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, OTHER, VIEW) is False


@pytest.mark.asyncio
async def test_r4_still_refuses_a_body_the_author_did_not_sign(armed, body):
    _c, pbft = _follower()
    await _locked_nv(pbft, body["hash"])
    forged = dict(body)
    forged["signature"] = "0xdeadbeef"
    assert pbft._vc_proposal_store(SEQ, body["hash"], forged, PROPOSER, VIEW) is False


@pytest.mark.asyncio
async def test_r4_unchanged_when_unarmed(vc_armed, body, monkeypatch):
    monkeypatch.setattr(settings, "pbft_locked_cross_author_height", None)
    _c, pbft = _follower()
    await _locked_nv(pbft, body["hash"])
    assert pbft._vc_proposal_store(SEQ, body["hash"], body, PROPOSER, VIEW) is False
    own = _real_body(PROPOSER)
    assert pbft._vc_proposal_store(SEQ, own["hash"], own, PROPOSER, VIEW) is True  # own body: always fine
