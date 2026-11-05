"""#1142 pin: v21 on-chain agent spend sessions (AGENT-SPEND-B-1).

AGENT_SESSION_GRANT/REVOKE lifecycle, session-bound enforcement on
TRANSFER/ESCROW_LOCK (live session, op allowed, daily cap over the
1290-block day bucket, atomic ledger charge), expiry/revocation,
squatter self-revoke, and pre-v21 inertness for replay.
"""

import pytest
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import Account, AgentSpendLedger, AgentSpendSession
from aitbc_chain.config import settings
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.state.agent_spend import SPEND_DAY_BLOCKS
from aitbc_chain.state.state_transition import StateTransition, get_block_version_for_height

from .test_apply_parity import (
    CHAIN,
    PROVIDER,
    BUYER,
    BUYER_KEY,
    PROVIDER_KEY,
    OTHER_KEY,
    _attach_sender_sig,
    _tx,
    derive_ethereum_address,
)

OWNER = BUYER  # session owner: the account that grants/revokes
AGENT = PROVIDER  # the agent address sessions authorize spends for
OTHER = derive_ethereum_address(OTHER_KEY)
AGENT_KEY = PROVIDER_KEY
OWNER_KEY = BUYER_KEY
V21_HEIGHT = 100
DAY = V21_HEIGHT // SPEND_DAY_BLOCKS


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'spend-v21.db'}", echo=False)
    chain_metadata.create_all(engine)
    return engine


def _seed(session):
    session.add(Account(chain_id=CHAIN, address=OWNER, balance=10**12, nonce=0))
    session.add(Account(chain_id=CHAIN, address=AGENT, balance=10**12, nonce=0))
    session.commit()


def _signed(tx_type, signer_key, payload, nonce=0, value=0, sender=None, recipient=None):
    tx = _tx(sender or OWNER, recipient or OTHER, value, tx_type, payload or {})
    tx["nonce"] = nonce
    return _attach_sender_sig(tx, signer_key)


def _grant(session, st, *, session_id="sess-1", cap=10**9, ops=None, nonce=0, expires=None, key=OWNER_KEY):
    payload = {
        "session_id": session_id,
        "agent_id": "agent-x",
        "agent_address": AGENT,
        "daily_cap": cap,
        "ops": ops if ops is not None else ["wallet.execute", "escrow.fund"],
    }
    if expires is not None:
        payload["expires_at_height"] = expires
    return st.apply_transaction(
        session,
        CHAIN,
        _signed("AGENT_SESSION_GRANT", key, payload, nonce),
        _h("grant", session_id, nonce),
        block_version=21,
        block_height=V21_HEIGHT,
    )


def _h(*parts):
    import hashlib

    return "0x" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _spend(session, st, *, session_id="sess-1", nonce, value, height=V21_HEIGHT, tx_type="TRANSFER", key=AGENT_KEY, tag=None):
    payload = {"session_id": session_id} if session_id else {}
    if tx_type == "ESCROW_LOCK":
        payload = {**payload, "job_id": "job-s1", "provider": PROVIDER}
    return st.apply_transaction(
        session,
        CHAIN,
        _signed(tx_type, key, payload, nonce=nonce, value=value, sender=AGENT, recipient=OWNER),
        _h("spend", nonce, value, tag),
        block_version=21,
        block_height=height,
    )


def _ledger(session, session_id="sess-1", day=DAY):
    return session.get(AgentSpendLedger, (CHAIN, session_id, day))


# ---- lifecycle ------------------------------------------------------------


def test_grant_binds_and_spend_charges_ledger(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        ok, err = _grant(session, st)
        assert ok is True, err
        row = session.get(AgentSpendSession, (CHAIN, "sess-1"))
        assert row is not None and row.owner_address == OWNER and row.revoked_height is None

        ok, err = _spend(session, st, nonce=0, value=500)
        assert ok is True, err
        assert _ledger(session).spent == 500
        assert _ledger(session).last_height == V21_HEIGHT


def test_over_cap_spend_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st, cap=100)[0] is True
        ok, err = _spend(session, st, nonce=0, value=101)
        assert ok is False and "daily cap" in err
        assert _ledger(session) is None


def test_cap_accumulates_across_spends_same_day(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st, cap=1000)[0] is True
        assert _spend(session, st, nonce=0, value=700)[0] is True
        ok, err = _spend(session, st, nonce=1, value=400)
        assert ok is False and "daily cap" in err
        assert _ledger(session).spent == 700


def test_new_day_bucket_resets_cap(tmp_path):
    st = StateTransition()
    next_day_height = (DAY + 1) * SPEND_DAY_BLOCKS
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st, cap=1000)[0] is True
        assert _spend(session, st, nonce=0, value=1000)[0] is True
        ok, err = _spend(session, st, nonce=1, value=1000, height=next_day_height)
        assert ok is True, err
        assert _ledger(session, day=DAY).spent == 1000
        assert _ledger(session, day=DAY + 1).spent == 1000


# ---- enforcement ----------------------------------------------------------


def test_bound_sender_without_session_id_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True
        ok, err = _spend(session, st, session_id=None, nonce=0, value=10)
        assert ok is False and "session-bound" in err


def test_unbound_sender_spend_without_session_passes(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        ok, err = _spend(session, st, session_id=None, nonce=0, value=10)
        assert ok is True, err


def test_session_for_wrong_sender_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True
        # The owner tries to spend under the agent's session — sender mismatch.
        tx = _tx(OWNER, AGENT, 10, "TRANSFER", {"session_id": "sess-1"})
        tx["nonce"] = 1
        ok, err = st.apply_transaction(
            session, CHAIN, _attach_sender_sig(tx, OWNER_KEY), _h("misuse"), block_version=21, block_height=V21_HEIGHT
        )
        assert ok is False and "agent" in err


def test_unknown_session_id_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        ok, err = _spend(session, st, session_id="ghost", nonce=0, value=10)
        assert ok is False and "not found" in err


def test_expired_session_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st, expires=V21_HEIGHT + 10)[0] is True
        assert _spend(session, st, nonce=0, value=10)[0] is True
        ok, err = _spend(session, st, nonce=1, value=10, height=V21_HEIGHT + 10)
        assert ok is False and "expired" in err


def test_ops_gate_escrow_fund(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        # Session allows only wallet.execute — escrow funding must be refused.
        assert _grant(session, st, ops=["wallet.execute"])[0] is True
        ok, err = _spend(session, st, nonce=0, value=100, tx_type="ESCROW_LOCK")
        assert ok is False and "operation" in err
        ok, err = _spend(session, st, nonce=0, value=100, tx_type="TRANSFER")
        assert ok is True, err


def test_ops_gate_transfer(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st, ops=["escrow.fund"])[0] is True
        ok, err = _spend(session, st, nonce=0, value=100, tx_type="TRANSFER")
        assert ok is False and "operation" in err
        ok, err = _spend(session, st, nonce=0, value=100, tx_type="ESCROW_LOCK")
        assert ok is True, err


# ---- revocation / squatter escape -----------------------------------------


def test_owner_revoke_unbinds(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True
        tx = _signed("AGENT_SESSION_REVOKE", OWNER_KEY, {"session_id": "sess-1"}, nonce=1)
        ok, err = st.apply_transaction(session, CHAIN, tx, _h("revoke"), block_version=21, block_height=V21_HEIGHT)
        assert ok is True, err
        assert session.get(AgentSpendSession, (CHAIN, "sess-1")).revoked_height == V21_HEIGHT
        # Bound is lifted: sessionless spend passes again.
        ok, err = _spend(session, st, session_id=None, nonce=0, value=10)
        assert ok is True, err


def test_third_party_revoke_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True
        other = OTHER
        session.add(Account(chain_id=CHAIN, address=other, balance=10**9, nonce=0))
        session.commit()
        tx = _tx(other, OWNER, 0, "AGENT_SESSION_REVOKE", {"session_id": "sess-1"})
        ok, err = st.apply_transaction(
            session, CHAIN, _attach_sender_sig(tx, OTHER_KEY), _h("badrevoke"), block_version=21, block_height=V21_HEIGHT
        )
        assert ok is False and "owner or agent" in err


def test_agent_self_revoke_frees_squatter_binding(tmp_path):
    """A squatter grant on the victim's address binds it — the agent revokes its
    own session and is free again (the anti-front-running escape)."""
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        # Squat: the "victim" AGENT never asked for this — owner granted it.
        assert _grant(session, st, session_id="squat", cap=1)[0] is True
        ok, err = _spend(session, st, session_id=None, nonce=0, value=10)
        assert ok is False and "session-bound" in err
        # Agent unbinds itself.
        tx = _tx(AGENT, OWNER, 0, "AGENT_SESSION_REVOKE", {"session_id": "squat"})
        ok, err = st.apply_transaction(
            session, CHAIN, _attach_sender_sig(tx, AGENT_KEY), _h("selfrevoke"), block_version=21, block_height=V21_HEIGHT
        )
        assert ok is True, err
        ok, err = _spend(session, st, session_id=None, nonce=1, value=10)
        assert ok is True, err


def test_revoked_session_spend_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True
        tx = _signed("AGENT_SESSION_REVOKE", OWNER_KEY, {"session_id": "sess-1"}, nonce=1)
        assert st.apply_transaction(session, CHAIN, tx, _h("revoke"), block_version=21, block_height=V21_HEIGHT)[0] is True
        ok, err = _spend(session, st, nonce=0, value=10)
        assert ok is False and "revoked" in err


# ---- grant shape / replay -------------------------------------------------


def test_duplicate_session_id_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True
        ok, err = _grant(session, st, nonce=1)
        assert ok is False and "already exists" in err


def test_grant_with_value_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        tx = _signed(
            "AGENT_SESSION_GRANT",
            OWNER_KEY,
            {
                "session_id": "s-v",
                "agent_address": AGENT,
                "daily_cap": 10,
                "ops": ["wallet.execute"],
            },
            nonce=0,
            value=1,
        )
        ok, err = st.apply_transaction(session, CHAIN, tx, _h("grantv"), block_version=21, block_height=V21_HEIGHT)
        assert ok is False


@pytest.mark.parametrize(
    "payload",
    [
        {"agent_address": AGENT, "daily_cap": 10, "ops": ["wallet.execute"]},  # no session_id
        {"session_id": "s", "agent_address": "not-an-address", "daily_cap": 10, "ops": ["wallet.execute"]},
        {"session_id": "s", "agent_address": AGENT, "daily_cap": 0, "ops": ["wallet.execute"]},
        {"session_id": "s", "agent_address": AGENT, "daily_cap": 10, "ops": []},
        {"session_id": "s", "agent_address": AGENT, "daily_cap": 10, "ops": ["admin.override"]},
        {"session_id": "s", "agent_address": AGENT, "daily_cap": 10, "ops": ["wallet.execute"], "expires_at_height": 1},
    ],
)
def test_malformed_grants_refused(tmp_path, payload):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        tx = _signed("AGENT_SESSION_GRANT", OWNER_KEY, payload, nonce=0)
        ok, err = st.apply_transaction(session, CHAIN, tx, _h("mal", payload), block_version=21, block_height=V21_HEIGHT)
        assert ok is False, payload


# ---- pre-v21 inertness ----------------------------------------------------


def test_below_v21_session_types_replay_as_transfer(tmp_path):
    """Pre-activation replay: the same envelopes behave as generic txs — no
    session table write, no binding, no ledger charge."""
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        grant_tx = _signed(
            "AGENT_SESSION_GRANT",
            OWNER_KEY,
            {
                "session_id": "sess-1",
                "agent_address": AGENT,
                "daily_cap": 1,
                "ops": ["wallet.execute"],
            },
            nonce=0,
        )
        ok, err = st.apply_transaction(session, CHAIN, grant_tx, _h("pregrant"), block_version=20, block_height=V21_HEIGHT)
        assert ok is True, err
        assert session.get(AgentSpendSession, (CHAIN, "sess-1")) is None
        # And a session-named spend applies uncharged at v20.
        ok, err = _spend_v20(session, st)
        assert ok is True, err
        assert _ledger(session) is None


def _spend_v20(session, st):
    tx = _tx(AGENT, OWNER, 10, "TRANSFER", {"session_id": "sess-1"})
    return st.apply_transaction(
        session, CHAIN, _attach_sender_sig(tx, AGENT_KEY), _h("presp"), block_version=20, block_height=V21_HEIGHT
    )


# ---- replay / fail-closed ---------------------------------------------------


def test_wrong_chain_grant_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        tx = _signed(
            "AGENT_SESSION_GRANT",
            OWNER_KEY,
            {
                "session_id": "sess-1",
                "agent_address": AGENT,
                "daily_cap": 10,
                "ops": ["wallet.execute"],
            },
            nonce=0,
        )
        tx["chain_id"] = "bc-other"
        ok, err = st.apply_transaction(session, CHAIN, tx, _h("xchain"), block_version=21, block_height=V21_HEIGHT)
        assert ok is False and "chain" in err.lower()


def test_nonce_replay_refused(tmp_path):
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True
        assert _spend(session, st, nonce=0, value=10)[0] is True
        ok, err = _spend(session, st, nonce=0, value=10, tag="replay")
        assert ok is False and "nonce" in err.lower()


def test_session_store_failure_fails_closed(tmp_path):
    """Policy-store-down negative: a read error inside the verdict propagates —
    apply must not wave the spend through on a broken policy lookup."""
    st = StateTransition()
    with Session(_engine(tmp_path)) as session:
        _seed(session)
        assert _grant(session, st)[0] is True

        def _boom(*a, **k):
            raise RuntimeError("policy store down")

        import aitbc_chain.state.agent_spend as agent_spend_mod

        orig = agent_spend_mod._get_session
        agent_spend_mod._get_session = _boom
        try:
            with pytest.raises(RuntimeError):
                _spend(session, st, nonce=0, value=10)
        finally:
            agent_spend_mod._get_session = orig
        assert _ledger(session) is None


# ---- height resolution ------------------------------------------------------


def test_version_resolution_v21(monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v21_height", 22000)
    monkeypatch.setattr(settings, "state_transition_v20_height", 1)
    assert get_block_version_for_height(22000) == 21
    assert get_block_version_for_height(21999) == 20


def test_version_resolution_v21_unarmed(monkeypatch):
    monkeypatch.setattr(settings, "state_transition_v21_height", None)
    monkeypatch.setattr(settings, "state_transition_v20_height", 100)
    assert get_block_version_for_height(500) == 20
