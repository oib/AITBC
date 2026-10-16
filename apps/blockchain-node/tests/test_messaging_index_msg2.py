"""MSG-2: votes, moderation and reputation as derived state.

Same fixture style as test_messaging_index.py — Transaction rows seeded
directly, because every apply path writes the same row shape and the index
is a pure query over them. Determinism is proven by inserting the same rows
in different orders on two DBs and diffing the derived output.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
from eth_keys import keys
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, col, create_engine, select

from aitbc.messaging import build_envelope, envelope_error
from aitbc_chain.messaging_index import (
    get_message,
    list_messages,
    list_topics,
    message_votes,
    moderation_state,
    reputation,
    state,
    topic_founder,
    topic_moderation,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, Transaction

CHAIN = "test-chain"

_K = [keys.PrivateKey(os.urandom(32)) for _ in range(4)]
ALICE, BOB, CAROL, DAVE = [k.public_key.to_checksum_address() for k in _K]


def _mk_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    s = Session(engine)
    for a in (ALICE, BOB, CAROL, DAVE):
        s.add(Account(chain_id=CHAIN, address=a, balance=10**12, nonce=0))
    s.commit()
    return s


@pytest.fixture
def session():
    with _mk_session() as s:
        yield s


def _block(session: Session, height: int) -> None:
    exists = session.exec(select(Block).where(col(Block.chain_id) == CHAIN, col(Block.height) == height)).first()
    if exists is not None:
        return
    session.add(
        Block(
            chain_id=CHAIN,
            height=height,
            hash=f"{height:064x}",
            parent_hash=f"{height - 1:064x}",
            proposer="0x0",
            state_root="",
            timestamp=datetime(2026, 1, 1) + timedelta(seconds=height),
        )
    )


def _tx(session, height, n, sender, env, commit=True):
    _block(session, height)
    session.add(
        Transaction(
            chain_id=CHAIN,
            tx_hash=f"{n:064x}",
            sender=sender,
            recipient=sender,
            payload={"aitbc_msg": env},
            type="MESSAGE",
            status="confirmed",
            block_height=height,
            nonce=n,
            timestamp=(datetime(2026, 1, 1) + timedelta(seconds=height * 100 + n)).isoformat(),
        )
    )
    if commit:
        session.commit()
    return f"{n:064x}"


def _env(kind, topic="dev", sender=ALICE, **kw):
    return build_envelope(kind=kind, topic=topic, agent_address=sender, **kw)


# ---------------------------------------------------------------- codec


class TestActionCodec:
    def test_vote_valid(self):
        env = _env("vote", sender=ALICE, target="a" * 64, value=1)
        assert envelope_error(env, sender=ALICE) is None

    @pytest.mark.parametrize("value", [2, -2, 1.0, "1", True, None])
    def test_vote_bad_value(self, value):
        env = {"v": 1, "kind": "vote", "topic": "dev", "agent_address": ALICE, "target": "a" * 64, "value": value}
        assert envelope_error(env, sender=ALICE) is not None

    @pytest.mark.parametrize("kind", ["vote", "hide", "unhide", "pin", "unpin"])
    def test_target_required(self, kind):
        env = {"v": 1, "kind": kind, "topic": "dev", "agent_address": ALICE}
        if kind == "vote":
            env["value"] = 1
        assert envelope_error(env, sender=ALICE) is not None

    def test_lock_target_optional(self):
        assert envelope_error(_env("lock", sender=ALICE), sender=ALICE) is None
        assert envelope_error(_env("lock", sender=ALICE, target="b" * 64), sender=ALICE) is None
        bad = {"v": 1, "kind": "lock", "topic": "dev", "agent_address": ALICE, "target": "zz"}
        assert envelope_error(bad, sender=ALICE) is not None

    def test_grant_needs_grantee(self):
        env = {"v": 1, "kind": "mod_grant", "topic": "dev", "agent_address": ALICE}
        assert envelope_error(env, sender=ALICE) is not None
        ok = _env("mod_grant", sender=ALICE, grantee=BOB)
        assert envelope_error(ok, sender=ALICE) is None
        bad = {"v": 1, "kind": "mod_grant", "topic": "dev", "agent_address": ALICE, "grantee": "not-an-address"}
        assert envelope_error(bad, sender=ALICE) is not None

    def test_unknown_kind_still_skipped(self):
        env = {"v": 1, "kind": "teleport", "topic": "dev", "agent_address": ALICE}
        assert envelope_error(env, sender=ALICE) is not None


# ---------------------------------------------------------------- authority


class TestAuthority:
    def test_founder_is_first_post(self, session):
        _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="first"))
        _tx(session, 11, 0x11, BOB, _env("post", sender=BOB, body="second"))
        assert topic_founder(session, CHAIN, "dev") == ALICE

    def test_same_block_race_deterministic(self, session):
        # Same block, both claim founding — lower tx_hash wins everywhere.
        _tx(session, 10, 0xAA, BOB, _env("post", sender=BOB, body="b"))
        _tx(session, 10, 0x09, ALICE, _env("post", sender=ALICE, body="a"))
        assert topic_founder(session, CHAIN, "dev") == ALICE

    def test_grant_extends_moderator_set(self, session):
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="hi"))
        _tx(session, 11, 0x20, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB))
        st = moderation_state(session, CHAIN, "dev")
        assert st.moderators == {ALICE, BOB}
        # Bob's hide is now effective; a stranger's is not.
        _tx(session, 12, 0x30, BOB, _env("hide", sender=BOB, target=post))
        _tx(session, 13, 0x31, CAROL, _env("hide", sender=CAROL, target=post))
        st = moderation_state(session, CHAIN, "dev")
        assert st.hidden[post.lower()][1] == BOB
        # CAROL is never a moderator — her envelope never enters the
        # authority/effects scan at all (the fixpoint's anti-spam rule).
        assert all(a["signer"] != CAROL for a in st.actions)

    def test_grant_before_membership_is_ineffective(self, session):
        # Bob's hide sealed BEFORE Alice's grant: ineffective.
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="hi"))
        _tx(session, 11, 0x20, BOB, _env("hide", sender=BOB, target=post))
        _tx(session, 12, 0x21, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB))
        st = moderation_state(session, CHAIN, "dev")
        assert st.hidden == {}
        # The pre-grant hide is in the audit log, marked ineffective.
        early = next(a for a in st.actions if a["tx_hash"] == f"{0x20:064x}")
        assert early["effective"] is False
        # But Bob's later action IS effective (fixpoint picked him up).
        _tx(session, 13, 0x22, BOB, _env("hide", sender=BOB, target=post))
        st = moderation_state(session, CHAIN, "dev")
        assert post.lower() in st.hidden

    def test_revoke_and_non_empty_rule(self, session):
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="hi"))
        _tx(session, 11, 0x20, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB))
        # Founder revokes self — allowed while set stays non-empty.
        _tx(session, 12, 0x21, ALICE, _env("mod_revoke", sender=ALICE, grantee=ALICE))
        st = moderation_state(session, CHAIN, "dev")
        assert st.moderators == {BOB}
        # Bob's self-revoke would empty the set -> ineffective.
        _tx(session, 13, 0x22, BOB, _env("mod_revoke", sender=BOB, grantee=BOB))
        st = moderation_state(session, CHAIN, "dev")
        assert st.moderators == {BOB}
        # Bob still moderates.
        _tx(session, 14, 0x23, BOB, _env("hide", sender=BOB, target=post))
        st = moderation_state(session, CHAIN, "dev")
        assert post.lower() in st.hidden

    def test_hiding_the_grant_keeps_authority(self, session):
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="hi"))
        grant = _tx(session, 11, 0x20, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB))
        _tx(session, 12, 0x21, ALICE, _env("hide", sender=ALICE, target=grant))
        # Hiding the grant row changes display, not authority derivation.
        _tx(session, 13, 0x22, BOB, _env("hide", sender=BOB, target=post))
        st = moderation_state(session, CHAIN, "dev")
        assert st.moderators == {ALICE, BOB}
        assert post.lower() in st.hidden


# ---------------------------------------------------------------- hiding / reads


class TestHiddenReads:
    def _hidden_setup(self, session):
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="keep me"))
        hidden_post = _tx(session, 11, 0x11, BOB, _env("post", sender=BOB, body="spam"))
        _tx(session, 12, 0x20, ALICE, _env("hide", sender=ALICE, target=hidden_post))
        return post, hidden_post

    def test_default_list_excludes_hidden(self, session):
        post, hidden_post = self._hidden_setup(session)
        out = list_messages(session, CHAIN, topic="dev")
        ids = [m["tx_hash"] for m in out["messages"]]
        assert post in ids and hidden_post not in ids

    def test_include_hidden_flags_and_withholds_body(self, session):
        _post, hidden_post = self._hidden_setup(session)
        out = list_messages(session, CHAIN, topic="dev", include_hidden=True)
        row = next(m for m in out["messages"] if m["tx_hash"] == hidden_post)
        assert row["hidden"] is True and row["body"] is None
        assert row["hidden_by"]["moderator"] == ALICE

    def test_get_hidden_message_200_with_flag(self, session):
        _post, hidden_post = self._hidden_setup(session)
        view = get_message(session, CHAIN, hidden_post)
        assert view is not None and view["hidden"] is True and view["body"] is None

    def test_unhide_restores(self, session):
        _post, hidden_post = self._hidden_setup(session)
        _tx(session, 13, 0x30, ALICE, _env("unhide", sender=ALICE, target=hidden_post))
        out = list_messages(session, CHAIN, topic="dev")
        assert hidden_post in [m["tx_hash"] for m in out["messages"]]

    def test_hidden_still_counted_in_topics(self, session):
        self._hidden_setup(session)
        topics = list_topics(session, CHAIN)["topics"]
        t = next(t for t in topics if t["topic"] == "dev")
        assert t["message_count"] == 2 and t["hidden_count"] == 1

    def test_action_rows_never_surface_as_messages(self, session):
        self._hidden_setup(session)
        out = list_messages(session, CHAIN, topic="dev", include_hidden=True)
        assert all(m["kind"] in ("post", "reply") for m in out["messages"])


class TestPinAndLock:
    def test_pinned_in_separate_list(self, session):
        p1 = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="first"))
        p2 = _tx(session, 11, 0x11, ALICE, _env("post", sender=ALICE, body="second"))
        _tx(session, 12, 0x20, ALICE, _env("pin", sender=ALICE, target=p1))
        out = list_messages(session, CHAIN, topic="dev")
        assert [m["tx_hash"] for m in out["messages"]] == [p2]  # canonical order kept
        assert [m["tx_hash"] for m in out["pinned"]] == [p1]
        assert out["pinned"][0]["pinned_by"]["moderator"] == ALICE

    def test_topic_lock_marks_later_posts(self, session):
        before = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="before"))
        _tx(session, 11, 0x20, ALICE, _env("lock", sender=ALICE))
        after = _tx(session, 12, 0x11, BOB, _env("post", sender=BOB, body="after"))
        out = list_messages(session, CHAIN, topic="dev")
        ids = [m["tx_hash"] for m in out["messages"]]
        assert before in ids and after not in ids
        out2 = list_messages(session, CHAIN, topic="dev", include_hidden=True)
        row = next(m for m in out2["messages"] if m["tx_hash"] == after)
        assert row["after_lock"] is True and row["body"] is None

    def test_lock_does_not_block_moderation(self, session):
        _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="x"))
        _tx(session, 11, 0x20, ALICE, _env("lock", sender=ALICE))
        post = _tx(session, 12, 0x11, BOB, _env("post", sender=BOB, body="post-lock"))
        # grant + hide after the lock still apply; unlock lifts it.
        _tx(session, 13, 0x21, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB))
        _tx(session, 14, 0x22, ALICE, _env("hide", sender=ALICE, target=post))
        _tx(session, 15, 0x23, ALICE, _env("unlock", sender=ALICE))
        st = moderation_state(session, CHAIN, "dev")
        assert post.lower() in st.hidden
        assert st.topic_lock[0] == "unlock"
        assert st.moderators == {ALICE, BOB}

    def test_subtree_lock(self, session):
        root = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="root"))
        reply = _tx(session, 11, 0x11, BOB, _env("reply", sender=BOB, body="child", parent=root))
        other = _tx(session, 12, 0x12, CAROL, _env("post", sender=CAROL, body="other"))
        _tx(session, 13, 0x20, ALICE, _env("lock", sender=ALICE, target=root))
        late_reply = _tx(session, 14, 0x13, BOB, _env("reply", sender=BOB, body="late", parent=root))
        out = list_messages(session, CHAIN, topic="dev", include_hidden=True)
        by_id = {m["tx_hash"]: m for m in out["messages"]}
        assert by_id[reply]["after_lock"] is False  # sealed before the lock
        assert by_id[late_reply]["after_lock"] is True
        assert by_id[other]["after_lock"] is False


# ---------------------------------------------------------------- votes & reputation


class TestVotes:
    def _setup(self, session):
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="votable"))
        return post

    def test_score_fields_and_last_wins(self, session):
        post = self._setup(session)
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=post, value=1))
        _tx(session, 12, 0x21, CAROL, _env("vote", sender=CAROL, target=post, value=-1))
        # Bob flips to down — last wins.
        _tx(session, 13, 0x22, BOB, _env("vote", sender=BOB, target=post, value=-1))
        view = get_message(session, CHAIN, post)
        assert (view["upvotes"], view["downvotes"], view["score"], view["voter_count"]) == (0, 2, -2, 2)

    def test_retract(self, session):
        post = self._setup(session)
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=post, value=1))
        _tx(session, 12, 0x21, BOB, _env("vote", sender=BOB, target=post, value=0))
        assert get_message(session, CHAIN, post)["voter_count"] == 0

    def test_vote_on_non_message_is_noop(self, session):
        post = self._setup(session)
        bogus = f"{0x99:064x}"
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=bogus, value=1))
        assert get_message(session, CHAIN, post)["voter_count"] == 0
        st = state(session, CHAIN)
        assert st["contract_state"]["total_actions"] == 1

    def test_votes_route_lists_standing(self, session):
        post = self._setup(session)
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=post, value=1))
        _tx(session, 12, 0x21, ALICE, _env("vote", sender=ALICE, target=post, value=1))
        out = message_votes(session, CHAIN, post)
        assert out["count"] == 2
        assert {v["self_vote"] for v in out["votes"]} == {False, True}

    def test_reputation_integer_and_self_vote_excluded(self, session):
        m1 = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="m1"))
        m2 = _tx(session, 11, 0x11, ALICE, _env("post", sender=ALICE, body="m2"))
        _tx(session, 12, 0x20, BOB, _env("vote", sender=BOB, target=m1, value=1))
        _tx(session, 12, 0x21, CAROL, _env("vote", sender=CAROL, target=m1, value=1))
        _tx(session, 12, 0x22, DAVE, _env("vote", sender=DAVE, target=m1, value=-1))
        _tx(session, 12, 0x23, ALICE, _env("vote", sender=ALICE, target=m1, value=1))  # self, excluded
        _tx(session, 12, 0x24, BOB, _env("vote", sender=BOB, target=m2, value=-1))
        rep = reputation(session, CHAIN, ALICE)
        assert rep["reputation"] == (2 - 1) + (0 - 1) == 0
        assert rep["messages_authored"] == 2 and rep["messages_counted"] == 2

    def test_vote_cap(self, session):
        m = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="m"))
        for i in range(25):
            k = keys.PrivateKey(os.urandom(32))
            voter = k.public_key.to_checksum_address()
            session.add(Account(chain_id=CHAIN, address=voter, balance=1, nonce=0))
            _tx(session, 11, 0x100 + i, voter, _env("vote", sender=voter, target=m, value=1))
        session.commit()
        rep = reputation(session, CHAIN, ALICE)
        assert rep["reputation"] == 20  # VOTE_CAP

    def test_wrong_topic_vote_is_noop(self, session):
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="m"))
        _tx(session, 11, 0x20, BOB, _env("vote", topic="other", sender=BOB, target=post, value=1))
        # Vote claims topic 'other' but the target lives in 'dev' -> no-op.
        assert get_message(session, CHAIN, post)["voter_count"] == 0


# ---------------------------------------------------------------- moderation route


class TestModerationRoute:
    def test_topic_moderation_view(self, session):
        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="hi"))
        _tx(session, 11, 0x20, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB))
        _tx(session, 12, 0x21, BOB, _env("hide", sender=BOB, target=post))
        out = topic_moderation(session, CHAIN, "dev")
        assert out["founder"] == ALICE
        assert out["moderators"] == sorted([ALICE, BOB])
        assert out["hidden_count"] == 1
        assert any(a["kind"] == "hide" and a["effective"] for a in out["actions"])

    def test_unknown_topic_404s(self, session):
        assert topic_moderation(session, CHAIN, "nope") is None


# ---------------------------------------------------------------- determinism


class TestDeterminism:
    """The same sealed rows must derive identically regardless of insertion
    order (proposer vs follower vs bulk paths write in different orders)."""

    def _fixture_rows(self):
        rows = []
        rows.append((10, 0x10, ALICE, _env("post", sender=ALICE, body="first")))
        rows.append((10, 0x11, BOB, _env("post", sender=BOB, body="second")))
        rows.append((11, 0x20, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB)))
        rows.append((12, 0x21, BOB, _env("hide", sender=BOB, target=f"{0x11:064x}")))
        rows.append((12, 0x22, CAROL, _env("vote", sender=CAROL, target=f"{0x10:064x}", value=1)))
        rows.append((13, 0x23, ALICE, _env("pin", sender=ALICE, target=f"{0x10:064x}")))
        return rows

    def _load(self, order):
        s = _mk_session()
        for height, n, sender, env in order:
            _tx(s, height, n, sender, env, commit=False)
        s.commit()
        return s

    def test_reordered_application_identical(self):
        rows = self._fixture_rows()
        a = self._load(rows)
        b = self._load(list(reversed(rows)))
        with a, b:
            for fn in (
                lambda s: list_messages(s, CHAIN, topic="dev"),
                lambda s: list_topics(s, CHAIN),
                lambda s: topic_moderation(s, CHAIN, "dev"),
                lambda s: reputation(s, CHAIN, ALICE),
                lambda s: message_votes(s, CHAIN, f"{0x10:064x}"),
            ):
                assert fn(a) == fn(b)

    def test_reorg_removal(self, session):
        rows = self._fixture_rows()
        for height, n, sender, env in rows:
            _tx(session, height, n, sender, env)
        hidden_post = f"{0x11:064x}"
        assert get_message(session, CHAIN, hidden_post)["hidden"] is True
        # Reorg removes the hide's block rows (fork-heal deletes them).
        for r in session.exec(select(Transaction).where(col(Transaction.block_height) == 12)).all():
            session.delete(r)
        for b in session.exec(select(Block).where(col(Block.height) == 12)).all():
            session.delete(b)
        session.commit()
        assert get_message(session, CHAIN, hidden_post)["hidden"] is False


def _brute_force_moderators(session, topic: str) -> set[str]:
    """Reference authority: ONE canonical-order replay over every valid
    grant/revoke row for the topic, no signer prefilter. Each row applies iff
    its signer is in the moderator set at that position."""
    import aitbc_chain.messaging_index as mi
    from aitbc.crypto.signature_recovery import canonical_address

    founder = topic_founder(session, CHAIN, topic)
    mods: set[str] = {founder} if founder else set()
    stmt = mi._asc_select(CHAIN, topic).where(mi._env_json("kind").in_(["mod_grant", "mod_revoke"]))
    for row in mi._iter_valid_asc(session, stmt):
        signer = mi._canonical(row.sender)
        if signer not in mods:
            continue
        env = mi._env_from_row(row)
        try:
            grantee = canonical_address(env.get("grantee") or "", strict=True)
        except Exception:
            continue
        if env.get("kind") == "mod_grant":
            mods.add(grantee)
        elif grantee in mods and len(mods) > 1:
            mods.discard(grantee)
    return mods


class TestAuthorityProperty:
    """Director's amendment: the fixpoint's moderator set must equal a plain
    canonical-order replay over all rows signed by anyone who ever held
    moderation — randomised grant/revoke/reorder sequences."""

    def test_fixpoint_matches_brute_force_replay(self):
        import random

        signers = [ALICE, BOB, CAROL, DAVE]
        for seed in range(40):
            rng = random.Random(seed)
            rows: list[tuple[int, int, str, dict]] = []
            n = 0x1000
            height = 10
            # Founding posts in random order.
            for s in rng.sample(signers, rng.randint(1, 3)):
                rows.append((height, n, s, _env("post", sender=s, body=f"p{n}")))
                n += 1
            # Random grant/revoke fuzz over later blocks.
            for _ in range(rng.randint(2, 14)):
                height += rng.randint(0, 2)
                signer = rng.choice(signers)
                grantee = rng.choice(signers)
                kind = rng.choice(["mod_grant", "mod_revoke"])
                rows.append((height, n, signer, _env(kind, sender=signer, grantee=grantee)))
                n += 1
            rng.shuffle(rows)  # randomised insertion order
            s = _mk_session()
            for h, nn, sender, env in rows:
                _tx(s, h, nn, sender, env, commit=False)
            s.commit()
            with s:
                st = moderation_state(s, CHAIN, "dev")
                assert st.authority_unresolved is False, f"seed {seed}"
                assert st.moderators == _brute_force_moderators(s, "dev"), f"seed {seed}"

    def test_unconverged_authority_reports_flag_not_500(self, session, monkeypatch):
        """If the pass cap trips, the topic flags authority_unresolved and the
        route still answers — a long grant chain must not break topic reads."""
        import aitbc_chain.messaging_index as mi

        post = _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="hi"))
        _tx(session, 11, 0x20, ALICE, _env("mod_grant", sender=ALICE, grantee=BOB))
        monkeypatch.setattr(mi, "AUTHORITY_PASSES_CAP", 1)
        st = moderation_state(session, CHAIN, "dev")
        assert st.authority_unresolved is True
        # The read surfaces still answer.
        tm = topic_moderation(session, CHAIN, "dev")
        assert tm is not None and tm["authority_unresolved"] is True
        topics = list_topics(session, CHAIN)
        assert topics["topics"][0]["authority_unresolved"] is True
        assert get_message(session, CHAIN, post)["tx_hash"] == post


# ---------------------------------------------------------------- MSG-2b


def _rep_reference(session, address):
    """Straightforward reference for reputation(): the last valid vote per
    (voter, target, claimed topic) stands; counted only when the claimed
    topic equals the target's real topic; self-votes excluded."""
    from aitbc.messaging import POST_KINDS, VOTE_CAP

    author = address.lower()
    rows = session.exec(
        select(Transaction)
        .where(col(Transaction.chain_id) == CHAIN, col(Transaction.type) == "MESSAGE")
        .order_by(col(Transaction.block_height), col(Transaction.tx_hash))
    ).all()
    targets: list[str] = []
    topic_of: dict[str, str] = {}
    standing: dict[tuple[str, str, str], int] = {}
    for r in rows:
        env = (r.payload or {}).get("aitbc_msg")
        if not isinstance(env, dict) or envelope_error(env, sender=r.sender) is not None:
            continue
        kind = env.get("kind")
        if kind in POST_KINDS and r.sender.lower() == author:
            targets.append(str(r.tx_hash))
            topic_of[str(r.tx_hash).lower()] = env.get("topic")
        if kind == "vote":
            standing[(r.sender.lower(), str(env["target"]).lower(), env.get("topic"))] = env["value"]
    per: dict[str, list[tuple[str, int]]] = {}
    for (voter, target, ctopic), v in standing.items():
        if v != 0 and ctopic == topic_of.get(target):
            per.setdefault(target, []).append((voter, v))
    total = 0
    counted = 0
    for t in targets:
        vals = [(s, v) for s, v in per.get(t.lower(), []) if s != author]
        if not vals:
            continue
        counted += 1
        up = sum(1 for _s, v in vals if v > 0)
        down = sum(1 for _s, v in vals if v < 0)
        total += max(-VOTE_CAP, min(VOTE_CAP, up - down))
    return total, len(targets), counted


class TestReputationChunking:
    """MSG-2b item 1: the target IN-list is chunked (<=500 literals) with
    exact merged results — no truncation, no cap."""

    def _seed_posts(self, session, n_posts):
        hashes = []
        for i in range(n_posts):
            hashes.append(
                _tx(session, 10 + i // 20, 0x1000 + i, ALICE, _env("post", sender=ALICE, body=f"m{i}"), commit=False)
            )
        session.commit()
        return hashes

    @pytest.mark.parametrize("n_posts", [499, 500, 501, 1200])
    def test_exact_across_chunk_boundaries(self, session, n_posts):
        posts = self._seed_posts(session, n_posts)
        vote_h = 10 + n_posts // 20 + 10
        # Voters spread across every chunk boundary: first, last, and the
        # 499/500/501 seam, plus a self-vote (excluded) and a wrong-topic
        # vote (sealed no-op).
        seen = []
        for i in (0, min(249, n_posts - 1), min(498, n_posts - 1), min(499, n_posts - 1), min(500, n_posts - 1), n_posts - 1):
            if i in seen:
                continue
            seen.append(i)
            voter = [BOB, CAROL, DAVE][i % 3]
            _tx(session, vote_h, 0x8000 + i, voter, _env("vote", sender=voter, target=posts[i], value=1), commit=False)
        _tx(session, vote_h, 0x9000, ALICE, _env("vote", sender=ALICE, target=posts[0], value=1), commit=False)
        _tx(
            session,
            vote_h,
            0x9001,
            BOB,
            _env("vote", topic="other", sender=BOB, target=posts[n_posts - 1], value=-1),
            commit=False,
        )
        session.commit()
        rep = reputation(session, CHAIN, ALICE)
        ref_total, ref_authored, ref_counted = _rep_reference(session, ALICE)
        assert rep["messages_authored"] == n_posts == ref_authored
        assert rep["reputation"] == ref_total
        assert rep["messages_counted"] == ref_counted

    def test_zero_message_author(self, session):
        _tx(session, 10, 0x10, BOB, _env("post", sender=BOB, body="other author"))
        rep = reputation(session, CHAIN, ALICE)
        assert rep["messages_authored"] == 0
        assert rep["reputation"] == 0
        assert rep["messages_counted"] == 0


class TestWrongTopicVotePartition:
    """MSG-2b item 2: the standing-vote window partitions by
    (voter, target, claimed topic) — a wrong-topic vote is a sealed no-op
    and can never retract the voter's valid vote."""

    def _post(self, session):
        return _tx(session, 10, 0x10, ALICE, _env("post", sender=ALICE, body="hi"))

    def test_wrong_topic_does_not_displace_valid(self, session):
        post = self._post(session)
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=post, value=1))
        _tx(session, 12, 0x30, BOB, _env("vote", topic="other", sender=BOB, target=post, value=-1))
        out = message_votes(session, CHAIN, post)
        assert [(v["voter"], v["value"]) for v in out["votes"]] == [(BOB.lower(), 1)]
        assert get_message(session, CHAIN, post)["score"] == 1

    def test_right_topic_retract_still_works(self, session):
        post = self._post(session)
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=post, value=1))
        _tx(session, 12, 0x30, BOB, _env("vote", topic="other", sender=BOB, target=post, value=-1))
        _tx(session, 13, 0x40, BOB, _env("vote", sender=BOB, target=post, value=0))
        out = message_votes(session, CHAIN, post)
        assert out["votes"] == []
        assert get_message(session, CHAIN, post)["voter_count"] == 0

    def test_right_topic_last_wins_after_wrong_topic(self, session):
        post = self._post(session)
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=post, value=1))
        _tx(session, 12, 0x30, BOB, _env("vote", topic="other", sender=BOB, target=post, value=-1))
        _tx(session, 13, 0x40, BOB, _env("vote", sender=BOB, target=post, value=-1))
        out = message_votes(session, CHAIN, post)
        assert [(v["voter"], v["value"]) for v in out["votes"]] == [(BOB.lower(), -1)]
        assert get_message(session, CHAIN, post)["score"] == -1

    def test_surfaces_agree(self, session):
        """message_votes, _score_fields (via list/get views) and reputation
        must all report the same standing vote."""
        post = self._post(session)
        other = _tx(session, 10, 0x11, ALICE, _env("post", sender=ALICE, body="m2"))
        _tx(session, 11, 0x20, BOB, _env("vote", sender=BOB, target=post, value=1))
        _tx(session, 12, 0x30, BOB, _env("vote", topic="other", sender=BOB, target=post, value=-1))
        _tx(session, 13, 0x40, CAROL, _env("vote", sender=CAROL, target=other, value=-1))
        mv = message_votes(session, CHAIN, post)
        assert [(v["voter"], v["value"]) for v in mv["votes"]] == [(BOB.lower(), 1)]
        listed = {m["tx_hash"]: m for m in list_messages(session, CHAIN, topic="dev")["messages"]}
        assert listed[post]["score"] == 1 and listed[other]["score"] == -1
        rep = reputation(session, CHAIN, ALICE)
        assert rep["reputation"] == 1 - 1 == 0
