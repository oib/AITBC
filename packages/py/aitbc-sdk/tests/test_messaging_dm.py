"""MSG-15 Phase B: SDK DM helpers — client-side encryption boundary.

Fake RPC, in-memory keys only, no live host. The load-bearing assertion:
plaintext never appears in any submitted envelope or fetched payload — only
the sealed ``ct`` crosses the wire.
"""

from __future__ import annotations

import base64
import json

import pytest

from aitbc.dm_client import UNREACHABLE, dm_store_load, dm_store_save, generate_key_era, open_dm, seal_dm
from aitbc_sdk.errors import AITBCConnectionError, AITBCError
from aitbc_sdk.messaging import MessagingClient, MessagingNotFoundError
import aitbc_sdk.messaging as sdkmsg

ALICE = "0x" + "11" * 20
BOB = "0x" + "22" * 20
CAROL = "0x" + "33" * 20

SECRET_BODY = "meet at the usual bench — bring the ledger"


class FakeHTTP:
    def __init__(self, base_url: str = "http://rpc"):
        self.base_url = base_url


def _client() -> MessagingClient:
    return MessagingClient(FakeHTTP())


def _capture_submit():
    calls = []

    def submit(wallet, envelope, fee):
        calls.append({"wallet": wallet, "envelope": envelope, "fee": fee})
        return "ab" * 32

    return calls, submit


def _patch_key_fetch(monkeypatch, response):
    monkeypatch.setattr(sdkmsg, "fetch_dm_key", lambda *a, **k: response)


def _patch_inbox(monkeypatch, pages):
    it = iter(pages)
    monkeypatch.setattr(sdkmsg, "fetch_dm_inbox", lambda *a, **k: next(it, {"messages": []}))


# --------------------------------------------------------------- dm_send


class TestDmSend:
    def test_roundtrip_plaintext_never_leaves_process(self, monkeypatch):
        bob = generate_key_era()
        _patch_key_fetch(monkeypatch, {"enc_pubkey": bob["enc_pubkey"]})
        calls, submit = _capture_submit()
        out = _client().dm_send(BOB, SECRET_BODY, wallet="alice", agent_address=ALICE, submit=submit)

        env = calls[0]["envelope"]
        assert env["kind"] == "dm" and env["topic"] == "dm" and env["to"] == BOB
        assert env["agent_address"] == ALICE
        # The whole submitted payload carries ciphertext only.
        wire = json.dumps(calls)
        assert SECRET_BODY not in wire
        assert "body" not in env
        ct = env["ct"]
        base64.b64decode(ct, validate=True)  # strict base64
        assert SECRET_BODY.encode() not in base64.b64decode(ct)
        # …and Bob can open it with his secret key.
        assert open_dm(bob["secret_key"], ALICE, BOB, ct) == SECRET_BODY
        assert out["tx_hash"] == "ab" * 32

    def test_requires_wallet_submit_body(self, monkeypatch):
        bob = generate_key_era()
        _patch_key_fetch(monkeypatch, {"enc_pubkey": bob["enc_pubkey"]})
        c = _client()
        _, submit = _capture_submit()
        with pytest.raises(AITBCError, match="wallet"):
            c.dm_send(BOB, "hi", wallet="", agent_address=ALICE, submit=submit)
        with pytest.raises(AITBCError, match="submit"):
            c.dm_send(BOB, "hi", wallet="w", agent_address=ALICE, submit=None)  # type: ignore[arg-type]
        with pytest.raises(AITBCError, match="empty"):
            c.dm_send(BOB, "", wallet="w", agent_address=ALICE, submit=submit)
        with pytest.raises(AITBCError, match="limit"):
            c.dm_send(BOB, "x" * 4000, wallet="w", agent_address=ALICE, submit=submit)
        with pytest.raises(AITBCError, match="0x"):
            c.dm_send("not-an-address", "hi", wallet="w", agent_address=ALICE, submit=submit)

    def test_no_published_key_is_not_found(self, monkeypatch):
        _patch_key_fetch(monkeypatch, None)
        c = _client()
        with pytest.raises(MessagingNotFoundError):
            c.dm_send(BOB, "hi", wallet="w", agent_address=ALICE, submit=lambda *a: "t")
        monkeypatch.setattr(sdkmsg, "fetch_dm_key", lambda *a, **k: UNREACHABLE)
        with pytest.raises(AITBCConnectionError):
            c.dm_send(BOB, "hi", wallet="w", agent_address=ALICE, submit=lambda *a: "t")


# --------------------------------------------------------- dm_publish_key


class TestDmPublishKey:
    def test_generates_stores_and_submits(self, tmp_path, monkeypatch):
        calls, submit = _capture_submit()
        path = tmp_path / "alice.json"
        out = _client().dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=submit)
        env = calls[0]["envelope"]
        assert env["kind"] == "dm_key" and env["topic"] == "dm" and env["enc_pubkey"] == out["enc_pubkey"]
        store = dm_store_load(path)
        assert store["keys"][-1]["enc_pubkey"] == out["enc_pubkey"]
        assert store["keys"][-1]["published_tx"] == out["tx_hash"]
        assert (path.stat().st_mode & 0o777) == 0o600

    def test_existing_key_not_reposted_unless_rotate(self, tmp_path):
        calls, submit = _capture_submit()
        path = tmp_path / "alice.json"
        c = _client()
        first = c.dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=submit)
        second = c.dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=submit)
        assert second["enc_pubkey"] == first["enc_pubkey"]
        assert len(calls) == 1  # no second envelope
        third = c.dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=submit, rotate=True)
        assert third["enc_pubkey"] != first["enc_pubkey"]
        assert len(calls) == 2
        assert len(dm_store_load(path)["keys"]) == 2  # old era kept


# ----------------------------------------------------------------- dm_read


def _dm_row(tx: str, ct: str, sender: str = ALICE, height: int = 50) -> dict:
    return {"tx_hash": tx, "block_height": height, "sender": sender, "ct": ct}


class TestDmRead:
    def test_decrypts_matching_row(self, monkeypatch):
        bob = generate_key_era()
        ct = seal_dm(bob["enc_pubkey"], ALICE, BOB, SECRET_BODY)
        tx = "cd" * 32
        _patch_inbox(monkeypatch, [{"messages": [_dm_row(tx, ct)], "next_cursor": None}])
        out = _client().dm_read(tx, address=BOB, secret_key=bob["secret_key"])
        assert out["body"] == SECRET_BODY and out["from"] == ALICE and out["to"] == BOB

    def test_paginates_to_find_row(self, monkeypatch):
        bob = generate_key_era()
        tx = "cd" * 32
        ct = seal_dm(bob["enc_pubkey"], ALICE, BOB, SECRET_BODY)
        pages = [
            {"messages": [_dm_row("ee" * 32, "junk")], "next_cursor": "40:ee"},
            {"messages": [_dm_row(tx, ct)], "next_cursor": None},
        ]
        _patch_inbox(monkeypatch, pages)
        out = _client().dm_read(tx, address=BOB, secret_key=bob["secret_key"])
        assert out["body"] == SECRET_BODY

    def test_missing_row_and_tamper_raise(self, monkeypatch):
        bob = generate_key_era()
        carol = generate_key_era()
        tx = "cd" * 32
        _patch_inbox(monkeypatch, [{"messages": [], "next_cursor": None}])
        c = _client()
        with pytest.raises(MessagingNotFoundError):
            c.dm_read(tx, address=BOB, secret_key=bob["secret_key"])

        wrong_ct = seal_dm(carol["enc_pubkey"], ALICE, BOB, "other words")
        _patch_inbox(monkeypatch, [{"messages": [_dm_row(tx, wrong_ct)], "next_cursor": None}])
        with pytest.raises(AITBCError, match="cannot read DM"):
            c.dm_read(tx, address=BOB, secret_key=bob["secret_key"])

    def test_requires_key_material(self):
        c = _client()
        with pytest.raises(AITBCError, match="secret_key|wallet"):
            c.dm_read("ab" * 32, address=BOB)
        with pytest.raises(AITBCError, match="address|wallet"):
            c.dm_read("ab" * 32, secret_key="x")


# ------------------------------------------------------------------ MSG-8e
# Store hardening on the SDK path: persist-before-publish, atomic modes,
# corrupt store refused, crash keeps the secret on disk.

import os


class TestPublishKeyHardening:
    def test_secret_on_disk_before_submit_runs(self, tmp_path):
        path = tmp_path / "alice.json"
        seen = {}

        def submit(wallet, envelope, fee):
            # At submit time the era is already persisted, unpublished.
            store = dm_store_load(path, strict=True)
            seen["era"] = store["keys"][-1]
            return "ab" * 32

        _client().dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=submit)
        assert seen["era"]["secret_key"]
        assert seen["era"]["published_tx"] is None

    def test_failed_submit_keeps_era_and_retry_reuses_it(self, tmp_path):
        path = tmp_path / "alice.json"
        c = _client()

        def boom(*a):
            raise AITBCError("simulated crash in send")

        with pytest.raises(AITBCError, match="simulated crash"):
            c.dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=boom)
        on_disk = dm_store_load(path, strict=True)
        assert len(on_disk["keys"]) == 1
        assert on_disk["keys"][0]["secret_key"] and on_disk["keys"][0]["published_tx"] is None

        calls, submit = _capture_submit()
        out = c.dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=submit)
        assert out["enc_pubkey"] == on_disk["keys"][0]["enc_pubkey"]  # same era retried
        assert len(dm_store_load(path, strict=True)["keys"]) == 1
        assert len(calls) == 1

    def test_corrupt_store_refused_byte_identical(self, tmp_path):
        path = tmp_path / "alice.json"
        path.write_bytes(b"{not json")
        before = path.read_bytes()
        with pytest.raises(AITBCError, match="unreadable|malformed"):
            _client().dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=lambda *a: "t")
        assert path.read_bytes() == before

    @pytest.mark.parametrize("umask", [0o022, 0o000])
    def test_modes_under_umask(self, tmp_path, umask):
        old = os.umask(umask)
        try:
            path = tmp_path / "fresh" / "alice.json"
            _, submit = _capture_submit()
            _client().dm_publish_key(wallet="alice", agent_address=ALICE, keys_path=path, submit=submit)
            assert (path.stat().st_mode & 0o777) == 0o600
            assert (path.parent.stat().st_mode & 0o777) == 0o700
            assert [p.name for p in path.parent.iterdir()] == ["alice.json"]
        finally:
            os.umask(old)


# ------------------------------------------------------------------ MSG-8g
# Wallet-store era fallback on the read path: dm_read tries every stored era
# newest→oldest; an explicit secret_key keeps its single-key meaning.


def _wallet_store(tmp_path, eras):
    path = tmp_path / "bob.json"
    dm_store_save(path, {"keys": list(eras)})
    return path


class TestDmReadEras:
    def test_rotation_round_trip_wallet_store(self, tmp_path, monkeypatch):
        era1, era2 = generate_key_era(), generate_key_era()
        path = _wallet_store(tmp_path, [era1, era2])
        monkeypatch.setattr(sdkmsg, "_resolve_dm_key_path", lambda w: path)
        c = _client()
        tx = "cd" * 32
        for pub, body in (
            (era1["enc_pubkey"], "sealed to the old key"),
            (era2["enc_pubkey"], "sealed to the new key"),
        ):
            _patch_inbox(monkeypatch, [{"messages": [_dm_row(tx, seal_dm(pub, ALICE, BOB, body))]}])
            assert c.dm_read(tx, wallet="bob", address=BOB)["body"] == body

    def test_unknown_key_reports_count_without_material(self, tmp_path, monkeypatch):
        era1, era2, stranger = generate_key_era(), generate_key_era(), generate_key_era()
        path = _wallet_store(tmp_path, [era1, era2])
        monkeypatch.setattr(sdkmsg, "_resolve_dm_key_path", lambda w: path)
        ct = seal_dm(stranger["enc_pubkey"], ALICE, BOB, "unreadable")
        tx = "cd" * 32
        _patch_inbox(monkeypatch, [{"messages": [_dm_row(tx, ct)]}])
        with pytest.raises(AITBCError) as exc:
            _client().dm_read(tx, wallet="bob", address=BOB)
        text = str(exc.value)
        assert "no stored DM key era" in text and "2" in text
        for leak in (era1["secret_key"], era2["secret_key"], stranger["secret_key"], ct):
            assert leak not in text

    def test_header_mismatch_never_falls_through(self, tmp_path, monkeypatch):
        import aitbc.dm_client as dm

        era1, era2 = generate_key_era(), generate_key_era()
        path = _wallet_store(tmp_path, [era1, era2])
        monkeypatch.setattr(sdkmsg, "_resolve_dm_key_path", lambda w: path)
        calls = []
        real = dm.open_dm

        def spy(secret, sender, recipient, ct):
            calls.append(secret)
            return real(secret, sender, recipient, ct)

        monkeypatch.setattr(dm, "open_dm", spy)
        # Sealed to era1, but the inner header names CAROL while the row is
        # signed by ALICE — era2 decrypt-fails and advances, era1 decrypts
        # and the header check must stop the walk there.
        ct = seal_dm(era1["enc_pubkey"], CAROL, BOB, "rebound")
        tx = "cd" * 32
        _patch_inbox(monkeypatch, [{"messages": [_dm_row(tx, ct)]}])
        with pytest.raises(AITBCError, match="signer"):
            _client().dm_read(tx, wallet="bob", address=BOB)
        assert calls == [era2["secret_key"], era1["secret_key"]]

    def test_tampered_ciphertext_fails_all_eras(self, tmp_path, monkeypatch):
        era1, era2 = generate_key_era(), generate_key_era()
        path = _wallet_store(tmp_path, [era1, era2])
        monkeypatch.setattr(sdkmsg, "_resolve_dm_key_path", lambda w: path)
        raw = bytearray(base64.b64decode(seal_dm(era1["enc_pubkey"], ALICE, BOB, "hi")))
        raw[-1] ^= 1
        tx = "cd" * 32
        _patch_inbox(monkeypatch, [{"messages": [_dm_row(tx, base64.b64encode(bytes(raw)).decode())]}])
        with pytest.raises(AITBCError, match="cannot read DM"):
            _client().dm_read(tx, wallet="bob", address=BOB)

    def test_single_era_store_still_reads(self, tmp_path, monkeypatch):
        era = generate_key_era()
        path = _wallet_store(tmp_path, [era])
        monkeypatch.setattr(sdkmsg, "_resolve_dm_key_path", lambda w: path)
        tx = "cd" * 32
        _patch_inbox(monkeypatch, [{"messages": [_dm_row(tx, seal_dm(era["enc_pubkey"], ALICE, BOB, SECRET_BODY))]}])
        assert _client().dm_read(tx, wallet="bob", address=BOB)["body"] == SECRET_BODY

    def test_corrupt_store_refused_byte_identical_on_read(self, tmp_path, monkeypatch):
        path = tmp_path / "bob.json"
        path.write_bytes(b"{not json")
        before = path.read_bytes()
        monkeypatch.setattr(sdkmsg, "_resolve_dm_key_path", lambda w: path)
        with pytest.raises(AITBCError, match="unreadable|malformed"):
            _client().dm_read("cd" * 32, wallet="bob", address=BOB)
        assert path.read_bytes() == before

    def test_empty_store_keeps_no_key_error(self, tmp_path, monkeypatch):
        path = _wallet_store(tmp_path, [])
        monkeypatch.setattr(sdkmsg, "_resolve_dm_key_path", lambda w: path)
        with pytest.raises(AITBCError, match="no DM key stored"):
            _client().dm_read("cd" * 32, wallet="bob", address=BOB)

    def test_explicit_secret_key_tries_only_that_key(self, monkeypatch):
        import aitbc.dm_client as dm

        era1, era2 = generate_key_era(), generate_key_era()
        ct = seal_dm(era1["enc_pubkey"], ALICE, BOB, SECRET_BODY)
        tx = "cd" * 32
        calls = []
        real = dm.open_dm

        def spy(secret, sender, recipient, blob):
            calls.append(secret)
            return real(secret, sender, recipient, blob)

        monkeypatch.setattr(dm, "open_dm", spy)
        page = {"messages": [_dm_row(tx, ct)]}
        # era2 alone cannot open a ct sealed to era1: one attempt, the named
        # key only — the explicit-key path never grows an era list.
        _patch_inbox(monkeypatch, [page, page])
        with pytest.raises(AITBCError, match="cannot read DM"):
            _client().dm_read(tx, address=BOB, secret_key=era2["secret_key"])
        assert calls == [era2["secret_key"]]
        out = _client().dm_read(tx, address=BOB, secret_key=era1["secret_key"])
        assert out["body"] == SECRET_BODY and calls == [era2["secret_key"], era1["secret_key"]]
