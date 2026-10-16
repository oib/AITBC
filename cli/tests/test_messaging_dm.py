"""MSG-8 CLI-side DM crypto: sealed-box roundtrip and the authenticated
inner-header checks. All keys are freshly generated throwaways."""

from __future__ import annotations

import base64
import os

import pytest
from eth_keys import keys
from nacl.public import PrivateKey as XKey
from nacl.public import PublicKey, SealedBox

pytest.importorskip("nacl")

from aitbc.messaging import DM_CONTEXT  # noqa: E402
from aitbc_cli.commands.messaging import _dm_store_load, _dm_store_save, _open_dm, _seal_dm  # noqa: E402

_K = [keys.PrivateKey(os.urandom(32)) for _ in range(3)]
ALICE, BOB, CAROL = [k.public_key.to_checksum_address() for k in _K]

_X = [XKey.generate() for _ in range(2)]
BOB_PUB = base64.b64encode(bytes(_X[0].public_key)).decode("ascii")
BOB_SEC = base64.b64encode(bytes(_X[0])).decode("ascii")
CAROL_PUB = base64.b64encode(bytes(_X[1].public_key)).decode("ascii")
CAROL_SEC = base64.b64encode(bytes(_X[1])).decode("ascii")


def test_roundtrip():
    ct = _seal_dm(BOB_PUB, ALICE, BOB, "hello bob")
    assert _open_dm(BOB_SEC, ALICE, BOB, ct) == "hello bob"


def test_multiline_body_including_leading_newline():
    body = "\nfirst line\n\nlast"
    ct = _seal_dm(BOB_PUB, ALICE, BOB, body)
    assert _open_dm(BOB_SEC, ALICE, BOB, ct) == body


def test_wrong_recipient_key_fails():
    ct = _seal_dm(BOB_PUB, ALICE, BOB, "hi")
    with pytest.raises(ValueError):
        _open_dm(CAROL_SEC, ALICE, BOB, ct)


def test_tampered_ciphertext_fails():
    ct = base64.b64decode(_seal_dm(BOB_PUB, ALICE, BOB, "hi"))
    ct = ct[:-1] + bytes([ct[-1] ^ 1])
    with pytest.raises(ValueError):
        _open_dm(BOB_SEC, ALICE, BOB, base64.b64encode(ct).decode())


def _seal_raw(pub_b64: str, plaintext: bytes) -> str:
    return base64.b64encode(SealedBox(PublicKey(base64.b64decode(pub_b64, validate=True))).encrypt(plaintext)).decode("ascii")


def test_rebinding_header_sender_mismatch():
    # Carol copies a ciphertext header naming herself — decrypts fine, header
    # check must reject: header sender says Carol but the tx signer is Alice.
    ct = _seal_dm(BOB_PUB, CAROL, BOB, "stolen words")
    with pytest.raises(ValueError, match="signer"):
        _open_dm(BOB_SEC, ALICE, BOB, ct)


def test_header_recipient_mismatch():
    ct = _seal_dm(BOB_PUB, ALICE, CAROL, "for carol really")
    with pytest.raises(ValueError, match="wallet"):
        _open_dm(BOB_SEC, ALICE, BOB, ct)


def test_wrong_context_rejected():
    ct = _seal_raw(BOB_PUB, f"other-context\n{ALICE}\n{BOB}\nhi".encode())
    with pytest.raises(ValueError, match="context"):
        _open_dm(BOB_SEC, ALICE, BOB, ct)


def test_non_utf8_rejected():
    ct = _seal_raw(BOB_PUB, b"\xff\xfe\x00binary")
    with pytest.raises(ValueError):
        _open_dm(BOB_SEC, ALICE, BOB, ct)


def test_too_few_separators_rejected():
    ct = _seal_raw(BOB_PUB, f"{DM_CONTEXT}\n{ALICE}\n{BOB}".encode())
    with pytest.raises(ValueError):
        _open_dm(BOB_SEC, ALICE, BOB, ct)


def test_empty_body_rejected():
    ct = _seal_raw(BOB_PUB, f"{DM_CONTEXT}\n{ALICE}\n{BOB}\n".encode())
    with pytest.raises(ValueError, match="empty"):
        _open_dm(BOB_SEC, ALICE, BOB, ct)


def test_not_base64_rejected():
    with pytest.raises(ValueError):
        _open_dm(BOB_SEC, ALICE, BOB, "!!!not-b64!!!")


class TestDmKeyFile:
    def test_missing_file_empty(self, tmp_path):
        assert _dm_store_load(tmp_path / "nope.json") == {"keys": []}

    def test_roundtrip_and_mode(self, tmp_path):
        path = tmp_path / "sub" / "w.json"
        store = {"keys": [{"era": 0, "enc_pubkey": BOB_PUB, "enc_seckey": BOB_SEC}]}
        _dm_store_save(path, store)
        assert _dm_store_load(path) == store
        assert (path.stat().st_mode & 0o777) == 0o600

    def test_corrupt_file_returns_empty(self, tmp_path):
        path = tmp_path / "w.json"
        path.write_text("{not json")
        assert _dm_store_load(path) == {"keys": []}

    def test_wrong_shape_returns_empty(self, tmp_path):
        path = tmp_path / "w.json"
        path.write_text('{"keys": "not-a-list"}')
        assert _dm_store_load(path) == {"keys": []}


# ------------------------------------------------------------------ MSG-8e
# Store hardening: persist-before-publish, atomic mode-600 writes, corrupt
# file refused, keygen without --rotate sends nothing.


from aitbc.dm_client import (
    DmStoreCorruptError,
    dm_mark_published,
    dm_prepare_era,
    dm_store_load,
    dm_store_save,
)


class TestStoreHardening:
    def test_corrupt_file_strict_raises_and_stays_byte_identical(self, tmp_path):
        path = tmp_path / "w.json"
        path.write_bytes(b"{not json")
        before = path.read_bytes()
        with pytest.raises(DmStoreCorruptError):
            dm_store_load(path, strict=True)
        with pytest.raises(DmStoreCorruptError):
            dm_prepare_era(path)
        assert path.read_bytes() == before

    def test_wrong_shape_strict_raises(self, tmp_path):
        path = tmp_path / "w.json"
        path.write_text('{"keys": "not-a-list"}')
        before = path.read_bytes()
        with pytest.raises(DmStoreCorruptError):
            dm_store_load(path, strict=True)
        assert path.read_bytes() == before

    @pytest.mark.parametrize("umask", [0o022, 0o000])
    def test_modes_under_umask(self, tmp_path, umask):
        old = os.umask(umask)
        try:
            path = tmp_path / "fresh" / "w.json"
            dm_store_save(path, {"keys": []})
            assert (path.stat().st_mode & 0o777) == 0o600
            assert (path.parent.stat().st_mode & 0o777) == 0o700
        finally:
            os.umask(old)

    def test_no_tmp_or_backup_files_left(self, tmp_path):
        path = tmp_path / "w.json"
        dm_store_save(path, {"keys": []})
        dm_store_save(path, {"keys": [{"x": 1}]})
        assert [p.name for p in tmp_path.iterdir()] == ["w.json"]


class TestPrepareEra:
    def test_era_persisted_before_any_publish(self, tmp_path):
        path = tmp_path / "w.json"
        era, store = dm_prepare_era(path)
        assert era is not None
        # Secret is already on disk with published_tx None — before any send.
        on_disk = dm_store_load(path, strict=True)
        assert on_disk["keys"][-1]["secret_key"] == era["secret_key"]
        assert on_disk["keys"][-1]["published_tx"] is None

    def test_crash_before_publish_retries_same_era(self, tmp_path):
        path = tmp_path / "w.json"
        era1, _ = dm_prepare_era(path)
        # Simulated crash: no dm_mark_published, process dies.
        era2, _ = dm_prepare_era(path)
        assert era1 is not None and era2 is not None
        assert era2["enc_pubkey"] == era1["enc_pubkey"]
        assert era2["secret_key"] == era1["secret_key"]
        assert len(dm_store_load(path, strict=True)["keys"]) == 1

    def test_published_era_returns_none_and_rotate_adds(self, tmp_path):
        path = tmp_path / "w.json"
        era, store = dm_prepare_era(path)
        assert era is not None
        dm_mark_published(path, store, era, "ab" * 32)
        assert dm_prepare_era(path)[0] is None
        era2, store2 = dm_prepare_era(path, rotate=True)
        assert era2 is not None
        assert era2["enc_pubkey"] != era["enc_pubkey"]
        assert len(store2["keys"]) == 2


def _keygen_patches(monkeypatch, tmp_path, key_path, send_result="ab" * 32):
    """Route dm keygen's wallet/send machinery at throwaway fixtures."""
    import aitbc_cli.commands.messaging as m

    sent = []
    monkeypatch.setattr(m, "_dm_key_file", lambda ctx, w: key_path)
    monkeypatch.setattr(m, "_wallet_address", lambda ctx, w: ALICE)
    monkeypatch.setattr(m, "_resolve_transaction_rpc_url", lambda u: "http://rpc")
    monkeypatch.setattr(m, "resolve_wallet_password", lambda **k: "pw")

    def fake_send(*a, **k):
        sent.append((a, k))
        return send_result

    monkeypatch.setattr(m, "_send_transaction_impl", fake_send)
    return sent


class TestKeygenFlow:
    def test_existing_published_key_sends_nothing(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc_cli.commands.messaging import messaging

        key_path = tmp_path / "w.json"
        dm_store_save(key_path, {"keys": [{"enc_pubkey": BOB_PUB, "secret_key": BOB_SEC, "published_tx": "ab" * 32}]})
        sent = _keygen_patches(monkeypatch, tmp_path, key_path)
        result = CliRunner().invoke(messaging, ["dm", "keygen", "--wallet", "w", "--confirm"])
        assert result.exit_code == 0, result.output
        assert "use --rotate" in result.output
        assert sent == []  # finding 4: no resubmit of the existing key

    def test_submit_failure_keeps_secret_on_disk(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc_cli.commands.messaging import messaging

        key_path = tmp_path / "w.json"
        sent = _keygen_patches(monkeypatch, tmp_path, key_path, send_result=None)
        result = CliRunner().invoke(messaging, ["dm", "keygen", "--wallet", "w", "--confirm"])
        assert result.exit_code != 0
        assert sent != []  # a send was attempted
        on_disk = dm_store_load(key_path, strict=True)
        assert len(on_disk["keys"]) == 1
        assert on_disk["keys"][0]["secret_key"]  # the private half survived
        assert on_disk["keys"][0]["published_tx"] is None
        assert "unpublished" in result.output or "kept" in result.output

    def test_retry_publishes_the_same_era(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc_cli.commands.messaging import messaging

        key_path = tmp_path / "w.json"
        _keygen_patches(monkeypatch, tmp_path, key_path, send_result=None)
        runner = CliRunner()
        assert runner.invoke(messaging, ["dm", "keygen", "--wallet", "w", "--confirm"]).exit_code != 0
        era_unpub = dm_store_load(key_path, strict=True)["keys"][0]["enc_pubkey"]
        # Second run, send now works — must reuse the unpublished era.
        sent = _keygen_patches(monkeypatch, tmp_path, key_path, send_result="cd" * 32)
        result = runner.invoke(messaging, ["dm", "keygen", "--wallet", "w", "--confirm"])
        assert result.exit_code == 0, result.output
        env = sent[0][1]["payload"]["aitbc_msg"]
        assert env["enc_pubkey"] == era_unpub
        assert len(dm_store_load(key_path, strict=True)["keys"]) == 1
