"""MSG-1: on-chain forum messages — codec, derived index, admission, tamper.

The index is a bounded, predicate-filtered query over the ``transaction``
table (docs/design/msg1-onchain-messaging.md). These tests seed Transaction
rows directly — no proposer needed — because every apply path already writes
the same row shape.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import pytest
from eth_keys import keys
from sqlmodel import Session, create_engine, select
from sqlalchemy.pool import StaticPool

from aitbc.messaging import (
    MAX_MESSAGE_BODY_BYTES,
    build_envelope,
    envelope_error,
    extract_envelope,
    normalize_topic,
)
from aitbc_chain.messaging_index import (
    MAX_READ_LIMIT,
    admission_error,
    get_message,
    list_messages,
    list_topics,
    parse_cursor,
    state,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, Transaction
from aitbc_chain.rpc.transactions import TransactionRequest, _validate_transaction_admission
from aitbc_chain.rpc.utils import sign_transaction_data, verify_transaction_signature
from aitbc_chain.state.pure_state_transition import compute_state_delta

CHAIN = "test-chain"

_KEY_A = keys.PrivateKey(os.urandom(32))
_KEY_B = keys.PrivateKey(os.urandom(32))
ALICE = _KEY_A.public_key.to_checksum_address()
BOB = _KEY_B.public_key.to_checksum_address()


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Account(chain_id=CHAIN, address=ALICE, balance=10**12, nonce=0))
        s.add(Account(chain_id=CHAIN, address=BOB, balance=10**12, nonce=0))
        s.commit()
        yield s


def _block(session: Session, height: int) -> None:
    session.add(
        Block(
            chain_id=CHAIN,
            height=height,
            hash=f"{height:064x}",
            parent_hash=f"{height - 1:064x}",
            proposer="0x0",
            state_root="",
        )
    )


def _tx_row(
    height: int | None,
    n: int,
    *,
    sender: str = ALICE,
    payload: dict[str, Any] | None = None,
    tx_type: str = "MESSAGE",
) -> Transaction:
    return Transaction(
        chain_id=CHAIN,
        tx_hash=f"{n:064x}",
        sender=sender,
        recipient=sender,
        payload=payload or {},
        type=tx_type,
        status="confirmed",
        block_height=height,
        timestamp=f"2026-10-15T00:{n % 60:02d}:00",
        nonce=n,
    )


def _env(kind="post", topic="dev", body="hello", agent_address=ALICE, **extra):
    env = {"v": 1, "kind": kind, "topic": topic, "body": body, "agent_address": agent_address}
    env.update(extra)
    return env


# ---------------------------------------------------------------- codec


class TestTopicNormalization:
    @pytest.mark.parametrize(
        "raw,want",
        [
            ("dev", "dev"),
            ("Dev", "dev"),
            ("  Dev Ops  ", "dev-ops"),
            ("broadcast", "broadcast"),
            ("a" * 64, "a" * 64),
        ],
    )
    def test_maps(self, raw, want):
        assert normalize_topic(raw) == want

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "-dev", "dev-", ".x", "a" * 65, "dev!", "dev ops!", "x" * 200],
    )
    def test_rejects(self, raw):
        assert normalize_topic(raw) is None

    def test_canonical_required_in_envelope(self):
        assert envelope_error(_env(topic="Dev"), sender=ALICE) is not None
        assert envelope_error(_env(topic="dev"), sender=ALICE) is None


class TestEnvelopeError:
    @pytest.mark.parametrize(
        "mutate",
        [
            lambda e: e.update(v=2),
            lambda e: e.update(v=True),
            lambda e: e.update(kind="announce"),
            lambda e: e.update(kind="vote"),
            lambda e: e.update(topic=""),
            lambda e: e.update(topic="Not Canonical"),
            lambda e: e.update(body=""),
            lambda e: e.update(body="x" * (MAX_MESSAGE_BODY_BYTES + 1)),
            lambda e: e.update(body=123),
            lambda e: e.update(agent_address=BOB),
            lambda e: e.update(parent="not-hex"),
        ],
    )
    def test_invalid(self, mutate):
        env = _env()
        mutate(env)
        assert envelope_error(env, sender=ALICE) is not None

    def test_valid_post(self):
        assert envelope_error(_env(), sender=ALICE) is None

    def test_body_boundary_bytes(self):
        assert envelope_error(_env(body="x" * MAX_MESSAGE_BODY_BYTES), sender=ALICE) is None
        assert envelope_error(_env(body="x" * (MAX_MESSAGE_BODY_BYTES + 1)), sender=ALICE) is not None
        # multibyte: 2049 two-byte chars = 4098 bytes > 4096 though chars < cap
        assert envelope_error(_env(body="é" * 2049), sender=ALICE) is not None
        assert envelope_error(_env(body="é" * 2048), sender=ALICE) is None

    def test_control_chars(self):
        assert envelope_error(_env(body="a\x07b"), sender=ALICE) is not None
        assert envelope_error(_env(body="a\nb\tc"), sender=ALICE) is None

    def test_reply_requires_64hex_parent(self):
        parent = "ab" * 32
        assert envelope_error(_env(kind="reply", parent=parent), sender=ALICE) is None
        assert envelope_error(_env(kind="reply"), sender=ALICE) is not None
        assert envelope_error(_env(kind="reply", parent="xyz"), sender=ALICE) is not None
        assert envelope_error(_env(parent=parent), sender=ALICE) is not None  # post + parent

    def test_extra_keys_ignored(self):
        env = _env(extra_field={"nested": True})
        assert envelope_error(env, sender=ALICE) is None
        # siblings next to aitbc_msg (to/amount injected by the submit route)
        payload = {"to": ALICE, "amount": 0, "aitbc_msg": env}
        assert envelope_error(extract_envelope(payload), sender=ALICE) is None

    def test_address_casing_canonical(self):
        assert envelope_error(_env(agent_address=ALICE.lower()), sender=ALICE) is None

    def test_build_envelope(self):
        env = build_envelope(kind="post", topic=" Dev ", body="hi", agent_address=ALICE)
        assert env["topic"] == "dev"
        with pytest.raises(ValueError):
            build_envelope(kind="post", topic="dev", body="x" * (MAX_MESSAGE_BODY_BYTES + 1), agent_address=ALICE)
        with pytest.raises(ValueError):
            build_envelope(kind="reply", topic="dev", body="hi", agent_address=ALICE)


# ------------------------------------------------------- signature round-trip


def _signed_message_tx(body: str = "hello chain", topic: str = "dev", parent: str | None = None) -> dict[str, Any]:
    """The exact dict a node verifies: to/amount inside the payload up front."""
    envelope = build_envelope(
        kind="reply" if parent else "post",
        topic=topic,
        body=body,
        agent_address=ALICE,
        parent=parent,
    )
    tx = {
        "chain_id": CHAIN,
        "from": ALICE,
        "to": ALICE,
        "amount": 0,
        "fee": 36,
        "nonce": 0,
        "type": "MESSAGE",
        "payload": {"to": ALICE, "amount": 0, "aitbc_msg": envelope},
    }
    tx["signature"] = sign_transaction_data(tx, _KEY_A.to_hex())
    return tx


class TestSignedRoundTrip:
    def test_signed_bytes_are_verified_bytes(self):
        """TransactionRequest enrichment must be a no-op for a CLI-built tx."""
        tx = _signed_message_tx()
        req = TransactionRequest.model_validate(
            {
                "from": tx["from"],
                "to": tx["to"],
                "amount": tx["amount"],
                "fee": tx["fee"],
                "nonce": tx["nonce"],
                "type": tx["type"],
                "chain_id": tx["chain_id"],
                "payload": dict(tx["payload"]),
                "signature": tx["signature"],
            }
        )
        verified = {
            "from": req.sender,
            "to": req.recipient,
            "amount": req.amount,
            "fee": req.fee,
            "nonce": req.nonce,
            "payload": req.payload,
            "type": req.type,
            "chain_id": req.chain_id,
            "signature": req.sig,
        }
        assert verify_transaction_signature(verified, req.sig, req.sender)

    def test_unsigned_to_amount_in_payload_breaks_signature(self):
        """A payload missing `to`/`amount` gets mutated before verification —
        the signature no longer covers what the verifier hashes."""
        tx = _signed_message_tx()
        tx["payload"] = {"aitbc_msg": tx["payload"]["aitbc_msg"]}
        tx["signature"] = sign_transaction_data(tx, _KEY_A.to_hex())
        req = TransactionRequest.model_validate(
            {
                "from": tx["from"],
                "to": tx["to"],
                "amount": tx["amount"],
                "fee": tx["fee"],
                "nonce": tx["nonce"],
                "type": tx["type"],
                "chain_id": tx["chain_id"],
                "payload": dict(tx["payload"]),
                "signature": tx["signature"],
            }
        )
        # wire input carries the `to` alias, not `recipient` — so only
        # `amount` is injected into the payload the client never signed
        assert req.payload["amount"] == 0 and "to" not in req.payload
        verified = {
            "from": req.sender,
            "to": req.recipient,
            "amount": req.amount,
            "fee": req.fee,
            "nonce": req.nonce,
            "payload": req.payload,
            "type": req.type,
            "chain_id": req.chain_id,
            "signature": req.sig,
        }
        assert not verify_transaction_signature(verified, req.sig, req.sender)

    @pytest.mark.parametrize("field", ["body", "topic", "agent_address"])
    def test_tampered_payload_rejected_everywhere(self, session, field):
        """Mutating after signing breaks the signature: the REST verify check
        (submit route) and the consensus delta both reject it. Admission only
        sees the signature-verified dict, so a schema-valid tamper is refused
        by those two gates — and a schema-*invalid* tamper (agent_address)
        additionally fails the envelope predicate at admission."""
        tx = _signed_message_tx()
        env = dict(tx["payload"]["aitbc_msg"])
        env[field] = {"body": "forged", "topic": "other", "agent_address": BOB}[field]
        tx["payload"] = dict(tx["payload"], aitbc_msg=env)

        assert not verify_transaction_signature(tx, tx["signature"], ALICE)

        account_map = {ALICE: session.get(Account, (CHAIN, ALICE))}
        delta = compute_state_delta(account_map, tx, CHAIN, tx["signature"][:8], block_version=9)
        assert not delta.success
        assert "signature" in delta.error.lower()

        if field == "agent_address":
            assert admission_error(tx["payload"], ALICE) is not None

    def test_stored_payload_shape(self):
        """What lands in `transaction.payload`: to/amount siblings + envelope."""
        tx = _signed_message_tx()
        assert set(tx["payload"]) >= {"to", "amount", "aitbc_msg"}
        assert tx["payload"]["to"] == ALICE and tx["payload"]["amount"] == 0


# ---------------------------------------------------------------- admission


class TestAdmission:
    @pytest.fixture
    def door(self, session, monkeypatch):
        @contextmanager
        def _scope(chain_id: str = ""):
            yield session

        monkeypatch.setattr("aitbc_chain.rpc.transactions.session_scope", _scope)
        monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])

        def submit(tx_type: str, sender: str, **overrides: Any) -> None:
            tx: dict[str, Any] = {
                "from": sender,
                "to": sender,
                "amount": 0,
                "fee": 36,
                "nonce": 0,
                "type": tx_type,
                "chain_id": CHAIN,
                "payload": {},
            }
            tx.update(overrides)
            _validate_transaction_admission(tx, None)

        return submit

    def test_valid_envelope_admitted(self, door):
        door("MESSAGE", ALICE, payload={"to": ALICE, "amount": 0, "aitbc_msg": _env()})

    def test_opaque_message_untouched(self, door):
        """Bridge-shaped/internal MESSAGE payloads carry no aitbc_msg — admitted."""
        door("MESSAGE", ALICE, payload={"type": "BRIDGE_RELEASE", "transfer_id": "x"})

    def test_broken_claim_refused(self, door):
        with pytest.raises(ValueError, match="aitbc_msg"):
            door("MESSAGE", ALICE, payload={"aitbc_msg": _env(body="x" * (MAX_MESSAGE_BODY_BYTES + 1))})
        with pytest.raises(ValueError):
            door("MESSAGE", ALICE, payload={"aitbc_msg": _env(agent_address=BOB)})
        with pytest.raises(ValueError):
            door("MESSAGE", ALICE, payload={"aitbc_msg": _env(kind="announce")})

    def test_malformed_namespace_refused(self, door):
        with pytest.raises(ValueError):
            door("MESSAGE", ALICE, payload={"aitbc_msg": "not-a-dict"})

    def test_admission_error_helper(self):
        assert admission_error({"aitbc_msg": _env()}, ALICE) is None
        assert admission_error({"aitbc_msg": _env(agent_address=BOB)}, ALICE) is not None
        assert admission_error({"type": "BRIDGE_RELEASE"}, ALICE) is None
        assert admission_error({"aitbc_msg": None}, ALICE) is not None


# ------------------------------------------------------------------- index


class TestIndex:
    """Seed sealed rows: valid posts/replies interleaved with junk. Only valid
    rows may surface — before paging, grouping and counting."""

    @pytest.fixture
    def seeded(self, session):
        _block(session, 10)
        _block(session, 11)
        rows = [
            # h10: valid post, junk kind, valid post
            _tx_row(10, 1, payload={"aitbc_msg": _env(body="first")}),
            _tx_row(10, 2, payload={"aitbc_msg": _env(kind="announce", body="fake official")}),
            _tx_row(10, 3, sender=BOB, payload={"aitbc_msg": _env(body="hi all", agent_address=BOB)}),
            # h11: bridge-internal MESSAGE row, oversized junk, reply, unsealed
            _tx_row(11, 4, payload={"type": "BRIDGE_RELEASE", "transfer_id": "t1"}),
            _tx_row(11, 5, payload={"aitbc_msg": _env(body="x" * (MAX_MESSAGE_BODY_BYTES + 1))}),
            _tx_row(11, 6, payload={"aitbc_msg": _env(kind="reply", body="re:first", parent=f"{1:064x}")}),
            _tx_row(11, 7, payload={"aitbc_msg": _env(kind="reply", body="re:ghost", parent="ff" * 32)}),
            _tx_row(None, 8, payload={"aitbc_msg": _env(body="unsealed draft")}),
            # non-canonical topic, wrong v, mismatched address — all sealed junk
            _tx_row(11, 9, payload={"aitbc_msg": _env(topic="Dev")}),
            _tx_row(11, 10, payload={"aitbc_msg": _env(v=9)}),
            _tx_row(11, 11, payload={"aitbc_msg": _env(agent_address=BOB)}),  # sender ALICE
            _tx_row(11, 12, tx_type="TRANSFER", payload={}),  # not a message at all
        ]
        session.add_all(rows)
        session.commit()
        return session

    def test_only_valid_rows_listed(self, seeded):
        out = list_messages(seeded, CHAIN, limit=50)
        bodies = [m["body"] for m in out["messages"]]
        assert bodies == ["re:ghost", "re:first", "hi all", "first"]
        assert out["count"] == 4
        assert out["index_height"] == 11
        assert out["scan_bounded"] is False

    def test_ordering_newest_first(self, seeded):
        out = list_messages(seeded, CHAIN, limit=50)
        heights = [m["block_height"] for m in out["messages"]]
        assert heights == sorted(heights, reverse=True)

    def test_topic_filter(self, seeded):
        out = list_messages(seeded, CHAIN, topic="dev")
        assert out["count"] == 4
        out = list_messages(seeded, CHAIN, topic="nothing-here")
        assert out["count"] == 0

    def test_author_filter(self, seeded):
        out = list_messages(seeded, CHAIN, author=BOB)
        assert [m["body"] for m in out["messages"]] == ["hi all"]
        # case-insensitive against the verbatim sender column
        out2 = list_messages(seeded, CHAIN, author=BOB.lower())
        assert out2["count"] == 1

    def test_cursor_paging_no_gaps_over_junk(self, seeded):
        page1 = list_messages(seeded, CHAIN, limit=2)
        assert [m["body"] for m in page1["messages"]] == ["re:ghost", "re:first"]
        assert page1["next_cursor"]
        page2 = list_messages(seeded, CHAIN, limit=2, cursor=page1["next_cursor"])
        assert [m["body"] for m in page2["messages"]] == ["hi all", "first"]
        page3 = list_messages(seeded, CHAIN, limit=2, cursor=page2["next_cursor"])
        assert page3["messages"] == [] and page3["next_cursor"] is None
        # no duplicates across pages
        seen = [m["tx_hash"] for p in (page1, page2, page3) for m in p["messages"]]
        assert len(seen) == len(set(seen)) == 4

    def test_cursor_validation(self, seeded):
        with pytest.raises(ValueError):
            list_messages(seeded, CHAIN, cursor="garbage")
        assert parse_cursor("10:3") == (10, 3)
        assert parse_cursor(None) is None

    def test_parent_resolved_flag(self, seeded):
        out = list_messages(seeded, CHAIN)
        replies = {m["body"]: m for m in out["messages"] if m["kind"] == "reply"}
        assert replies["re:first"]["parent_resolved"] is True
        assert replies["re:ghost"]["parent_resolved"] is False
        # unresolvable parent still indexed, with its own topic
        assert replies["re:ghost"]["topic"] == "dev"

    def test_get_message(self, seeded):
        assert get_message(seeded, CHAIN, f"{1:064x}")["body"] == "first"
        # bridge-internal row and sealed junk are not forum messages
        assert get_message(seeded, CHAIN, f"{4:064x}") is None
        assert get_message(seeded, CHAIN, f"{5:064x}") is None
        assert get_message(seeded, CHAIN, "0" * 64) is None

    def test_topics_aggregation_excludes_junk(self, seeded):
        out = list_topics(seeded, CHAIN)
        assert out["total_topics"] == 1
        assert out["topics"][0]["topic"] == "dev"
        assert out["topics"][0]["message_count"] == 4
        assert out["topics"][0]["last_block_height"] == 11

    def test_state_totals(self, seeded):
        out = state(seeded, CHAIN)
        cs = out["contract_state"]
        assert cs["total_messages"] == 4
        assert cs["total_topics"] == 1
        assert cs["total_agents"] == 2
        assert out["index_height"] == 11

    def test_search_escapes_like_metachars(self, session):
        _block(session, 5)
        session.add_all(
            [
                _tx_row(5, 1, payload={"aitbc_msg": _env(body="100% sure")}),
                _tx_row(5, 2, payload={"aitbc_msg": _env(body="1000x")}),
                _tx_row(5, 3, payload={"aitbc_msg": _env(body="under_score")}),
            ]
        )
        session.commit()
        out = list_messages(session, CHAIN, body_contains="100%")
        assert [m["body"] for m in out["messages"]] == ["100% sure"]
        out = list_messages(session, CHAIN, body_contains="under_score")
        assert [m["body"] for m in out["messages"]] == ["under_score"]

    def test_limit_clamped(self, seeded):
        out = list_messages(seeded, CHAIN, limit=9999)
        assert out["count"] == 4  # all, no error; route layer clamps to MAX_READ_LIMIT
        assert MAX_READ_LIMIT == 100

    def test_offset_bounded(self, seeded):
        out = list_messages(seeded, CHAIN, offset=2, limit=10)
        assert [m["body"] for m in out["messages"]] == ["hi all", "first"]

    def test_reorg_removal_is_row_deletion(self, seeded):
        """Fork-heal deletes the losing block's tx rows — the index follows."""
        h11 = seeded.exec(select(Transaction).where(Transaction.chain_id == CHAIN, Transaction.block_height == 11)).all()
        for row in h11:
            seeded.delete(row)
        seeded.commit()
        out = list_messages(seeded, CHAIN)
        assert [m["body"] for m in out["messages"]] == ["hi all", "first"]

    def test_rebuild_identical(self, seeded):
        """'Rebuild' is re-running the query — identical by construction."""
        a = list_messages(seeded, CHAIN)["messages"]
        b = list_messages(seeded, CHAIN)["messages"]
        assert a == b

    def test_state_root_unaffected(self, session):
        """A sealed MESSAGE delta touches only the sender's fee+nonce."""
        tx = _signed_message_tx()
        account = session.get(Account, (CHAIN, ALICE))
        before = (account.balance, account.nonce)
        delta = compute_state_delta({ALICE: account}, tx, CHAIN, tx["signature"][:8], block_version=9)
        assert delta.success
        assert delta.sender_balance_change == -36
        assert delta.sender_nonce_change == 1
        assert delta.recipient_balance_change == 0
        # account table is the state_root input; only the sender row changes
        after = (account.balance + delta.sender_balance_change, account.nonce + delta.sender_nonce_change)
        assert after[0] < before[0] and after[1] == before[1] + 1


class TestGossipDrop:
    def test_gossip_drops_broken_claim(self):
        from aitbc_chain.rpc.utils import gossip_transaction_drop_reason

        tx = _signed_message_tx()
        assert gossip_transaction_drop_reason(tx) is None
        env = dict(tx["payload"]["aitbc_msg"], topic="Not Canonical")
        broken = dict(tx, payload={"to": ALICE, "amount": 0, "aitbc_msg": env})
        broken["signature"] = sign_transaction_data(broken, _KEY_A.to_hex())
        assert gossip_transaction_drop_reason(broken) == "invalid_aitbc_msg"

    def test_gossip_opaque_message_passes(self):
        from aitbc_chain.rpc.utils import gossip_transaction_drop_reason

        tx = _signed_message_tx()
        tx["payload"] = {"type": "BRIDGE_RELEASE", "transfer_id": "x"}
        tx["signature"] = sign_transaction_data(tx, _KEY_A.to_hex())
        assert gossip_transaction_drop_reason(tx) is None


# ------------------------------------------------------- hostile payload totality


_SURROGATE = "a\ud800"  # lone surrogate: JSON-legal, str-legal, not UTF-8-encodable

# Values JSON can decode that must never make the predicate raise.
_HOSTILE = [
    _SURROGATE,
    "\udfff",
    "\U0010ffff",  # max code point — legal
    "",
    "   ",
    0,
    1.0,
    1.5,
    True,
    None,
    [],
    ["x"],
    {},
    {"nested": _SURROGATE},
    "x" * (MAX_MESSAGE_BODY_BYTES + 1),
]


class TestPredicateTotality:
    """envelope_error/admission_error must return a reason, never raise, on
    any JSON-decodable input (a sealed hostile row must not 500 every read)."""

    @pytest.mark.parametrize("field", ["v", "kind", "topic", "body", "parent", "agent_address"])
    @pytest.mark.parametrize("value", _HOSTILE)
    def test_field_values_never_raise(self, field, value):
        env = _env(kind="reply", parent="ab" * 32) if field == "parent" else _env()
        env[field] = value
        result = envelope_error(env, sender=ALICE)
        assert result is None or isinstance(result, str)

    @pytest.mark.parametrize("sender", _HOSTILE + [ALICE.lower()])
    def test_sender_values_never_raise(self, sender):
        assert envelope_error(_env(), sender=sender) is None or isinstance(envelope_error(_env(), sender=sender), str)

    @pytest.mark.parametrize("payload", _HOSTILE + [{"aitbc_msg": v} for v in _HOSTILE])
    def test_payload_values_never_raise(self, payload):
        result = admission_error(payload, ALICE)
        assert result is None or isinstance(result, str)

    def test_lone_surrogate_body_reason(self):
        reason = envelope_error(_env(body=_SURROGATE), sender=ALICE)
        assert reason is not None and "UTF-8" in reason

    def test_unhashable_kind_no_raise(self):
        assert envelope_error(_env(kind={}), sender=ALICE) is not None
        assert envelope_error(_env(kind=[]), sender=ALICE) is not None


class TestHostileSealedRows:
    """A sealed row with a lone-surrogate field is skipped by every read;
    the valid sibling in the same page is unaffected."""

    def _seed(self, session: Session, field: str) -> None:
        _block(session, 1)
        _block(session, 2)
        bad_env = _env(kind="reply", parent="cd" * 32) if field == "parent" else _env()
        bad_env[field] = _SURROGATE
        session.add(_tx_row(1, 1, payload={"to": ALICE, "amount": 0, "aitbc_msg": bad_env}))
        session.add(_tx_row(2, 2, payload={"to": ALICE, "amount": 0, "aitbc_msg": _env(body="ok")}))
        session.commit()

    @pytest.mark.parametrize("field", ["topic", "body", "parent", "agent_address"])
    def test_surrogate_field_row_skipped(self, session, field):
        self._seed(session, field)
        out = list_messages(session, CHAIN)
        assert [m["body"] for m in out["messages"]] == ["ok"]  # bad row skipped, no raise
        topics = list_topics(session, CHAIN)
        assert [t["topic"] for t in topics["topics"]] == ["dev"] and topics["topics"][0]["message_count"] == 1
        assert state(session, CHAIN)["contract_state"]["total_messages"] == 1
        assert get_message(session, CHAIN, f"{1:064x}") is None  # bad row 404s, no raise
        assert get_message(session, CHAIN, f"{2:064x}")["body"] == "ok"
        # search path (LIKE over body) unaffected
        assert [m["body"] for m in list_messages(session, CHAIN, body_contains="ok")["messages"]] == ["ok"]

    def test_surrogate_body_admission_reason(self):
        reason = admission_error({"aitbc_msg": _env(body=_SURROGATE)}, ALICE)
        assert reason is not None and "UTF-8" in reason
