"""MSG-8: encrypted direct messages — predicate, index carve-outs, routes.

Same fixture style as test_messaging_index_msg2.py: Transaction rows seeded
directly; the index is a pure query over them. All key material here is
freshly generated throwaway PyNaCl keypairs — no real keys in tests.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta

import pytest
from eth_keys import keys
from nacl.public import PrivateKey as XKey
from nacl.public import PublicKey, SealedBox
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, col, create_engine, select

from aitbc.messaging import DM_CONTEXT, DM_TOPIC, build_envelope, envelope_error
from aitbc_chain.messaging_index import (
    dm_inbox,
    get_message,
    latest_dm_key,
    list_messages,
    list_topics,
    state,
)
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.models import Account, Block, Transaction

CHAIN = "test-chain"

_K = [keys.PrivateKey(os.urandom(32)) for _ in range(3)]
ALICE, BOB, CAROL = [k.public_key.to_checksum_address() for k in _K]

_X = [XKey.generate() for _ in range(2)]
BOB_PUB_B64 = base64.b64encode(bytes(_X[0].public_key)).decode("ascii")
CAROL_PUB_B64 = base64.b64encode(bytes(_X[1].public_key)).decode("ascii")


def _mk_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)
    s = Session(engine)
    for a in (ALICE, BOB, CAROL):
        s.add(Account(chain_id=CHAIN, address=a, balance=10**12, nonce=0))
    s.commit()
    return s


@pytest.fixture
def session():
    with _mk_session() as s:
        yield s


def _block(session: Session, height: int) -> None:
    exists = session.exec(select(Block).where(col(Block.chain_id) == CHAIN, col(Block.height) == height)).first()
    if exists is None:
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


def _seal(pub_b64: str, sender: str, recipient: str, body: str, *, context: str = DM_CONTEXT) -> str:
    plaintext = f"{context}\n{sender}\n{recipient}\n{body}".encode()
    return base64.b64encode(SealedBox(PublicKey(base64.b64decode(pub_b64, validate=True))).encrypt(plaintext)).decode("ascii")


def _dm(sender=ALICE, to=BOB, body="hi") -> dict:
    return build_envelope(kind="dm", topic=DM_TOPIC, agent_address=sender, to=to, ct=_seal(BOB_PUB_B64, sender, to, body))


# ---------------------------------------------------------------- codec


class TestDmPredicate:
    def test_dm_valid(self):
        env = _dm()
        assert envelope_error(env, sender=ALICE) is None

    def test_dm_key_valid(self):
        env = build_envelope(kind="dm_key", topic=DM_TOPIC, agent_address=BOB, enc_pubkey=BOB_PUB_B64)
        assert envelope_error(env, sender=BOB) is None

    def test_dm_on_normal_topic_refused(self):
        env = _dm()
        env["topic"] = "dev"
        assert envelope_error(env, sender=ALICE) is not None

    @pytest.mark.parametrize("kind", ["post", "reply", "vote", "hide"])
    def test_non_dm_kind_on_dm_slug_refused(self, kind):
        env = {"v": 1, "kind": kind, "topic": "dm", "agent_address": ALICE}
        if kind in {"post", "reply"}:
            env["body"] = "x"
        if kind == "vote":
            env["target"] = "a" * 64
            env["value"] = 1
        if kind in {"hide", "unhide", "pin", "unpin"}:
            env["target"] = "a" * 64
        assert envelope_error(env, sender=ALICE) is not None

    def test_dm_key_on_normal_topic_refused(self):
        env = {"v": 1, "kind": "dm_key", "topic": "dev", "agent_address": ALICE, "enc_pubkey": BOB_PUB_B64}
        assert envelope_error(env, sender=ALICE) is not None

    def test_dm_bad_to(self):
        env = _dm()
        env["to"] = "not-an-address"
        assert envelope_error(env, sender=ALICE) is not None

    @pytest.mark.parametrize(
        "ct",
        [
            "not base64!!!",
            "a" * 4097,  # over the base64 cap
            "QUJD",  # valid b64 but only 3 raw bytes — still shape-fine
            "QQ",  # missing padding
            "QUJD RQ==",  # whitespace
            "QUJDRQ==\n",  # trailing newline
        ],
    )
    def test_ct_shape(self, ct):
        env = _dm()
        env["ct"] = ct
        # Only the over-cap and non-strict-b64 values must fail; "QUJD" and
        # friends decode fine and are left to the crypto layer.
        err = envelope_error(env, sender=ALICE)
        if ct == "QUJD":
            assert err is None
        else:
            assert err is not None

    def test_ct_cap_boundary(self):
        env = _dm()
        env["ct"] = base64.b64encode(os.urandom(3072)).decode("ascii")  # exactly 4096 chars
        assert envelope_error(env, sender=ALICE) is None
        env["ct"] = base64.b64encode(os.urandom(3073)).decode("ascii")[:4097]
        assert envelope_error(env, sender=ALICE) is not None

    def test_dm_key_bad_pubkey(self):
        for bad in ["not-b64", base64.b64encode(b"short").decode(), base64.b64encode(os.urandom(33)).decode()]:
            env = {"v": 1, "kind": "dm_key", "topic": "dm", "agent_address": ALICE, "enc_pubkey": bad}
            assert envelope_error(env, sender=ALICE) is not None

    def test_unknown_kind_still_refused(self):
        env = {"v": 1, "kind": "teleport", "topic": "dm", "agent_address": ALICE}
        assert envelope_error(env, sender=ALICE) is not None


# ---------------------------------------------------------------- index


class TestDmIndex:
    def _seed(self, session):
        _tx(session, 10, 1, BOB, build_envelope(kind="dm_key", topic=DM_TOPIC, agent_address=BOB, enc_pubkey=BOB_PUB_B64))
        h1 = _tx(session, 11, 2, ALICE, _dm(body="first"))
        h2 = _tx(session, 12, 3, ALICE, _dm(body="second"))
        # A DM to Carol must not appear in Bob's inbox.
        _tx(
            session,
            13,
            4,
            ALICE,
            build_envelope(
                kind="dm",
                topic=DM_TOPIC,
                agent_address=ALICE,
                to=CAROL,
                ct=_seal(CAROL_PUB_B64, ALICE, CAROL, "not for bob"),
            ),
        )
        return h1, h2

    def test_inbox(self, session):
        h1, h2 = self._seed(session)
        out = dm_inbox(session, CHAIN, BOB)
        assert [m["tx_hash"] for m in out["messages"]] == [h2, h1]
        assert all(m["to"] == BOB for m in out["messages"])
        assert all(m["sender"] == ALICE for m in out["messages"])
        assert all(m["kind"] == "dm" for m in out["messages"])

    def test_inbox_cursor_orders(self, session):
        h1, h2 = self._seed(session)
        page1 = dm_inbox(session, CHAIN, BOB, limit=1)
        assert page1["messages"][0]["tx_hash"] == h2 and page1["next_cursor"]
        page2 = dm_inbox(session, CHAIN, BOB, limit=1, cursor=page1["next_cursor"])
        assert page2["messages"][0]["tx_hash"] == h1

    def test_dm_excluded_from_public_reads(self, session):
        self._seed(session)
        msgs = list_messages(session, CHAIN)
        assert msgs["messages"] == []
        topics = list_topics(session, CHAIN)
        assert all(t["topic"] != DM_TOPIC for t in topics["topics"])
        st = state(session, CHAIN)
        assert st["contract_state"]["total_topics"] == 0
        found = list_messages(session, CHAIN, body_contains="first")
        assert found["messages"] == []

    def test_get_message_never_returns_dm(self, session):
        h1, _ = self._seed(session)
        assert get_message(session, CHAIN, h1) is None

    def test_legacy_post_on_dm_slug_hidden(self, session):
        # A pre-rule squat: a valid-looking post under the reserved slug. The
        # predicate refuses it; the index must also never list or count it.
        _tx(
            session,
            10,
            9,
            ALICE,
            {"v": 1, "kind": "post", "topic": "dm", "agent_address": ALICE, "body": "squatter"},
        )
        assert list_messages(session, CHAIN)["messages"] == []
        assert list_topics(session, CHAIN)["topics"] == []
        assert state(session, CHAIN)["contract_state"]["total_messages"] == 0

    def test_latest_dm_key(self, session):
        self._seed(session)
        key = latest_dm_key(session, CHAIN, BOB)
        assert key is not None and key["enc_pubkey"] == BOB_PUB_B64
        assert latest_dm_key(session, CHAIN, ALICE) is None

    def test_dm_key_rotation_latest_wins(self, session):
        self._seed(session)
        new = XKey.generate()
        pub2 = base64.b64encode(bytes(new.public_key)).decode("ascii")
        _tx(session, 20, 5, BOB, build_envelope(kind="dm_key", topic=DM_TOPIC, agent_address=BOB, enc_pubkey=pub2))
        assert latest_dm_key(session, CHAIN, BOB)["enc_pubkey"] == pub2

    def test_dm_key_same_block_tie(self, session):
        self._seed(session)
        a = XKey.generate()
        b = XKey.generate()
        pa = base64.b64encode(bytes(a.public_key)).decode("ascii")
        pb = base64.b64encode(bytes(b.public_key)).decode("ascii")
        _tx(session, 30, 6, BOB, build_envelope(kind="dm_key", topic=DM_TOPIC, agent_address=BOB, enc_pubkey=pa))
        _tx(session, 30, 7, BOB, build_envelope(kind="dm_key", topic=DM_TOPIC, agent_address=BOB, enc_pubkey=pb))
        # (block_height, tx_hash) order: tx 7 > tx 6, so pb wins.
        assert latest_dm_key(session, CHAIN, BOB)["enc_pubkey"] == pb

    def test_invalid_sealed_dm_never_lists(self, session):
        # Hostile sealed row: valid-looking dm shape but a bad `to` — the
        # predicate rejects it at read time.
        env = _dm()
        env["to"] = "garbage"
        _tx(session, 11, 2, ALICE, env)
        out = dm_inbox(session, CHAIN, BOB)
        assert out["messages"] == []


# ------------------------------------------------------------------ MSG-8g
# Era fallback in the shared read kernel (aitbc.dm_client): the read paths
# try every stored key era newest→oldest; only a sealed-box decrypt failure
# advances to the next era — an authenticity (header) failure raises on the
# spot.

import aitbc.dm_client as dm
from aitbc.dm_client import DmDecryptError, generate_key_era, open_dm, open_dm_with_eras, seal_dm


def _spy_open(monkeypatch):
    """Count open_dm calls while still running the real implementation."""
    calls = []
    real = dm.open_dm

    def spy(secret, sender, recipient, ct):
        calls.append(secret)
        return real(secret, sender, recipient, ct)

    monkeypatch.setattr(dm, "open_dm", spy)
    return calls


class TestOpenDmWithEras:
    def test_rotated_store_opens_old_and_new_ciphertexts(self):
        era1, era2 = generate_key_era(), generate_key_era()
        secrets = [era1["secret_key"], era2["secret_key"]]
        ct_old = seal_dm(era1["enc_pubkey"], ALICE, BOB, "sealed to era one")
        ct_new = seal_dm(era2["enc_pubkey"], ALICE, BOB, "sealed to era two")
        assert open_dm_with_eras(secrets, ALICE, BOB, ct_old) == "sealed to era one"
        assert open_dm_with_eras(secrets, ALICE, BOB, ct_new) == "sealed to era two"

    def test_newest_era_is_tried_first(self, monkeypatch):
        era1, era2 = generate_key_era(), generate_key_era()
        calls = _spy_open(monkeypatch)
        ct = seal_dm(era2["enc_pubkey"], ALICE, BOB, "for the current key")
        assert open_dm_with_eras([era1["secret_key"], era2["secret_key"]], ALICE, BOB, ct) == "for the current key"
        assert calls == [era2["secret_key"]]  # first try opens — older era never touched

    def test_unknown_key_fails_naming_only_the_tried_count(self):
        era1, era2 = generate_key_era(), generate_key_era()
        stranger = generate_key_era()  # a key the wallet never had
        ct = seal_dm(stranger["enc_pubkey"], ALICE, BOB, "unreachable")
        with pytest.raises(ValueError) as exc:
            open_dm_with_eras([era1["secret_key"], era2["secret_key"]], ALICE, BOB, ct)
        text = str(exc.value)
        assert "no stored DM key era" in text and "2" in text
        # No key, era or ciphertext material leaks into the error text.
        for leak in (
            era1["secret_key"],
            era2["secret_key"],
            stranger["secret_key"],
            era1["enc_pubkey"],
            era2["enc_pubkey"],
            stranger["enc_pubkey"],
            ct,
        ):
            assert leak not in text

    def test_header_failure_does_not_fall_through(self, monkeypatch):
        era1, era2 = generate_key_era(), generate_key_era()
        calls = _spy_open(monkeypatch)
        # Sealed to era1's key, but the inner header names CAROL while the tx
        # is signed by ALICE: era2 is tried first (decrypt fails → advance),
        # era1 decrypts and the header check must stop the walk right there.
        ct = seal_dm(era1["enc_pubkey"], CAROL, BOB, "rebound")
        with pytest.raises(ValueError, match="signer"):
            open_dm_with_eras([era1["secret_key"], era2["secret_key"]], ALICE, BOB, ct)
        assert calls == [era2["secret_key"], era1["secret_key"]]

    def test_tampered_ciphertext_fails_every_era(self):
        era1, era2 = generate_key_era(), generate_key_era()
        raw = bytearray(base64.b64decode(seal_dm(era1["enc_pubkey"], ALICE, BOB, "hi")))
        raw[-1] ^= 1
        ct = base64.b64encode(bytes(raw)).decode("ascii")
        with pytest.raises(ValueError, match="no stored DM key era"):
            open_dm_with_eras([era1["secret_key"], era2["secret_key"]], ALICE, BOB, ct)

    def test_malformed_ciphertext_does_not_iterate(self, monkeypatch):
        era1, era2 = generate_key_era(), generate_key_era()
        calls = _spy_open(monkeypatch)
        with pytest.raises(ValueError, match="not strict base64"):
            open_dm_with_eras([era1["secret_key"], era2["secret_key"]], ALICE, BOB, "!!!not-b64!!!")
        assert len(calls) == 1  # the same malformed ct cannot open under any era

    def test_single_era_behaves_like_open_dm(self):
        era, other = generate_key_era(), generate_key_era()
        ct = seal_dm(era["enc_pubkey"], ALICE, BOB, "just me")
        assert open_dm_with_eras([era["secret_key"]], ALICE, BOB, ct) == "just me"
        with pytest.raises(ValueError, match="1 era"):
            open_dm_with_eras([other["secret_key"]], ALICE, BOB, ct)

    def test_empty_era_list_reports_zero_tried(self):
        ct = seal_dm(generate_key_era()["enc_pubkey"], ALICE, BOB, "x")
        with pytest.raises(ValueError, match="0 era"):
            open_dm_with_eras([], ALICE, BOB, ct)

    def test_dm_decrypt_error_keeps_the_value_error_contract(self):
        era, other = generate_key_era(), generate_key_era()
        ct = seal_dm(era["enc_pubkey"], ALICE, BOB, "x")
        with pytest.raises(DmDecryptError):
            open_dm(other["secret_key"], ALICE, BOB, ct)
        with pytest.raises(ValueError, match="wrong key or tampered ciphertext"):
            open_dm(other["secret_key"], ALICE, BOB, ct)
