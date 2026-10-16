"""MSG-15 Phase B: SDK DM helpers — client-side encryption boundary.

Fake RPC, in-memory keys only, no live host. The load-bearing assertion:
plaintext never appears in any submitted envelope or fetched payload — only
the sealed ``ct`` crosses the wire.
"""

from __future__ import annotations

import base64
import json

import pytest

from aitbc.dm_client import UNREACHABLE, dm_store_load, generate_key_era, open_dm, seal_dm
from aitbc_sdk.errors import AITBCConnectionError, AITBCError
from aitbc_sdk.messaging import MessagingClient, MessagingNotFoundError
import aitbc_sdk.messaging as sdkmsg

ALICE = "0x" + "11" * 20
BOB = "0x" + "22" * 20

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
