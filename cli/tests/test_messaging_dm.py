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

    @pytest.mark.parametrize("umask", [0o022, 0o000, 0o077])
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

    # ------------------------------------------------------------- MSG-8f

    def test_stale_legacy_tmp_swept_and_save_succeeds(self, tmp_path):
        import time

        path = tmp_path / "w.json"
        stale = tmp_path / "w.json.tmp"
        stale.write_text("crash leftover")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        dm_store_save(path, {"keys": [{"x": 1}]})
        assert not stale.exists()
        assert dm_store_load(path, strict=True) == {"keys": [{"x": 1}]}

    def test_fresh_legacy_tmp_untouched(self, tmp_path):
        path = tmp_path / "w.json"
        fresh = tmp_path / "w.json.tmp"
        fresh.write_text("in-flight?")
        dm_store_save(path, {"keys": []})
        assert fresh.exists() and fresh.read_text() == "in-flight?"

    def test_stale_unique_tmp_swept(self, tmp_path):
        import time

        path = tmp_path / "w.json"
        stale = tmp_path / ".w.json.abc123.tmp"
        stale.write_text("crash leftover")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        dm_store_save(path, {"keys": []})
        assert not stale.exists()

    def test_symlink_and_dir_decoys_never_touched(self, tmp_path):
        import time

        path = tmp_path / "w.json"
        link = tmp_path / "w.json.tmp"
        link.symlink_to(tmp_path / "w.json")
        decoy_dir = tmp_path / ".w.json.dir.tmp"
        decoy_dir.mkdir()
        old = time.time() - 3600
        os.utime(link, (old, old), follow_symlinks=False)
        os.utime(decoy_dir, (old, old))
        dm_store_save(path, {"keys": [{"x": 1}]})
        assert link.is_symlink() and decoy_dir.is_dir()

    def test_other_names_in_dir_untouched(self, tmp_path):
        import time

        other = tmp_path / "other.json.tmp"
        other.write_text("not ours")
        old = time.time() - 3600
        os.utime(other, (old, old))
        dm_store_save(tmp_path / "w.json", {"keys": []})
        assert other.exists()

    def test_fsync_order_file_then_replace_then_dir(self, tmp_path, monkeypatch):
        calls = []

        def fake_fsync(fd):
            st = os.fstat(fd)
            target = os.readlink(f"/proc/self/fd/{fd}") if os.path.exists(f"/proc/self/fd/{fd}") else None
            calls.append(("fsync", st.st_mode & 0o777, target))
            return real_fsync(fd)

        def fake_replace(src, dst):
            calls.append(("replace", 0, None))
            return real_replace(src, dst)

        real_fsync = os.fsync
        real_replace = os.replace
        monkeypatch.setattr(os, "fsync", fake_fsync)
        monkeypatch.setattr(os, "replace", fake_replace)
        dm_store_save(tmp_path / "w.json", {"keys": []})
        kinds = [c[0] for c in calls]
        # exactly: file fsync, replace, dir fsync
        assert kinds == ["fsync", "replace", "fsync"]
        assert calls[0][1] == 0o600  # the secret-bearing tmp file
        assert calls[2][1] == 0o700 and calls[2][2] == str(tmp_path)  # the store dir

    def test_write_failure_leaves_no_tmp_and_prior_file_intact(self, tmp_path, monkeypatch):
        path = tmp_path / "w.json"
        dm_store_save(path, {"keys": [{"v": 1}]})
        before = path.read_bytes()

        class Boom(Exception):
            pass

        import json

        def boom(*a, **k):
            raise Boom()

        monkeypatch.setattr(json, "dumps", boom)
        with pytest.raises(Boom):
            dm_store_save(path, {"keys": [{"v": 2}]})
        assert path.read_bytes() == before
        assert [p.name for p in tmp_path.iterdir()] == ["w.json"]

    def test_replace_failure_leaves_no_tmp_and_prior_file_intact(self, tmp_path, monkeypatch):
        path = tmp_path / "w.json"
        dm_store_save(path, {"keys": [{"v": 1}]})
        before = path.read_bytes()

        class Boom(Exception):
            pass

        def boom(*a, **k):
            raise Boom()

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(Boom):
            dm_store_save(path, {"keys": [{"v": 2}]})
        assert path.read_bytes() == before
        assert [p.name for p in tmp_path.iterdir()] == ["w.json"]

    def test_two_saves_use_distinct_tmp_names(self, tmp_path, monkeypatch):
        import tempfile

        names = []
        real = tempfile.mkstemp

        def rec(*a, **k):
            r = real(*a, **k)
            names.append(r[1])
            return r

        monkeypatch.setattr(tempfile, "mkstemp", rec)
        dm_store_save(tmp_path / "w.json", {"keys": []})
        dm_store_save(tmp_path / "w.json", {"keys": [{"x": 1}]})
        assert len(names) == 2 and names[0] != names[1]
        assert all(os.path.basename(n).startswith(".w.json.") and n.endswith(".tmp") for n in names)

    def test_prepare_era_roundtrip_with_stale_tmp(self, tmp_path):
        import time

        path = tmp_path / "w.json"
        stale = tmp_path / "w.json.tmp"
        stale.write_text("crash leftover")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        era, store = dm_prepare_era(path)
        assert era is not None and not stale.exists()
        dm_mark_published(path, store, era, "ab" * 32)
        assert dm_store_load(path, strict=True)["keys"][-1]["published_tx"] == "ab" * 32


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


# ------------------------------------------------------------------ MSG-8g
# `dm read` tries every stored key era newest→oldest, so a DM sealed to a
# superseded key still opens after `dm keygen --rotate`. All keys here are
# freshly generated throwaways in tmp_path stores.


def _read_patches(monkeypatch, key_path, pages):
    """Route dm read's wallet/store/rpc machinery at throwaway fixtures."""
    import aitbc_cli.commands.messaging as m
    from unittest.mock import MagicMock

    http = MagicMock()
    it = iter(pages)
    http.get.side_effect = lambda *a, **k: next(it, {"messages": [], "next_cursor": None})
    monkeypatch.setattr(m, "_dm_key_file", lambda ctx, w: key_path)
    monkeypatch.setattr(m, "_wallet_address", lambda ctx, w: BOB)
    monkeypatch.setattr(m, "_resolve_transaction_rpc_url", lambda u: "http://rpc")
    monkeypatch.setattr(m, "_rpc_client", lambda url: http)


def _dm_row(tx, ct, sender=ALICE, height=50):
    return {"tx_hash": tx, "block_height": height, "sender": sender, "ct": ct}


def _read(result_output):
    import json

    start = result_output.find("{")
    assert start >= 0, result_output
    return json.loads(result_output[start:])


class TestDmReadEras:
    def test_rotation_round_trip_opens_old_and_new(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc.dm_client import generate_key_era
        from aitbc_cli.commands.messaging import messaging

        era1, era2 = generate_key_era(), generate_key_era()
        key_path = tmp_path / "bob.json"
        dm_store_save(key_path, {"keys": [era1, era2]})
        runner = CliRunner()
        for pub, body in (
            (era1["enc_pubkey"], "sealed to the old key"),
            (era2["enc_pubkey"], "sealed to the new key"),
        ):
            tx = "ab" * 32
            _read_patches(monkeypatch, key_path, [{"messages": [_dm_row(tx, _seal_dm(pub, ALICE, BOB, body))]}])
            result = runner.invoke(messaging, ["dm", "read", tx, "--wallet", "bob"], obj={"output_format": "json"})
            assert result.exit_code == 0, result.output
            payload = _read(result.output)
            assert payload["body"] == body and payload["to"] == BOB

    def test_unknown_key_reports_tried_count_without_material(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc.dm_client import generate_key_era
        from aitbc_cli.commands.messaging import messaging

        era1, era2, stranger = generate_key_era(), generate_key_era(), generate_key_era()
        key_path = tmp_path / "bob.json"
        dm_store_save(key_path, {"keys": [era1, era2]})
        tx = "cd" * 32
        ct = _seal_dm(stranger["enc_pubkey"], ALICE, BOB, "unreadable")
        _read_patches(monkeypatch, key_path, [{"messages": [_dm_row(tx, ct)]}])
        result = CliRunner().invoke(messaging, ["dm", "read", tx, "--wallet", "bob"], obj={"output_format": "json"})
        assert result.exit_code != 0
        text = result.output + (result.stderr or "")
        assert "no stored DM key era" in text and "2" in text
        for leak in (era1["secret_key"], era2["secret_key"], stranger["secret_key"], ct):
            assert leak not in text

    def test_header_mismatch_raises_not_era_error(self, tmp_path, monkeypatch):
        # Sealed to era1 but the header sender is CAROL while the row signer
        # is ALICE: era1 decrypts, the header check rejects, and the walk must
        # not end in the "no stored key era" fall-through error.
        from click.testing import CliRunner

        from aitbc.dm_client import generate_key_era
        from aitbc_cli.commands.messaging import messaging

        era1, era2 = generate_key_era(), generate_key_era()
        key_path = tmp_path / "bob.json"
        dm_store_save(key_path, {"keys": [era1, era2]})
        tx = "ef" * 32
        ct = _seal_dm(era1["enc_pubkey"], CAROL, BOB, "rebound")
        _read_patches(monkeypatch, key_path, [{"messages": [_dm_row(tx, ct)]}])
        result = CliRunner().invoke(messaging, ["dm", "read", tx, "--wallet", "bob"], obj={"output_format": "json"})
        assert result.exit_code != 0
        text = result.output + (result.stderr or "")
        assert "signer" in text and "no stored DM key era" not in text

    def test_tampered_ciphertext_fails_all_eras(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc.dm_client import generate_key_era
        from aitbc_cli.commands.messaging import messaging

        era1, era2 = generate_key_era(), generate_key_era()
        key_path = tmp_path / "bob.json"
        dm_store_save(key_path, {"keys": [era1, era2]})
        raw = bytearray(base64.b64decode(_seal_dm(era1["enc_pubkey"], ALICE, BOB, "hi")))
        raw[-1] ^= 1
        tx = "ab" * 32
        _read_patches(monkeypatch, key_path, [{"messages": [_dm_row(tx, base64.b64encode(bytes(raw)).decode())]}])
        result = CliRunner().invoke(messaging, ["dm", "read", tx, "--wallet", "bob"], obj={"output_format": "json"})
        assert result.exit_code != 0
        assert "no stored DM key era" in (result.output + (result.stderr or ""))

    def test_single_era_store_still_reads(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc.dm_client import generate_key_era
        from aitbc_cli.commands.messaging import messaging

        era = generate_key_era()
        key_path = tmp_path / "bob.json"
        dm_store_save(key_path, {"keys": [era]})
        tx = "ab" * 32
        _read_patches(
            monkeypatch,
            key_path,
            [{"messages": [_dm_row(tx, _seal_dm(era["enc_pubkey"], ALICE, BOB, "one era only"))]}],
        )
        result = CliRunner().invoke(messaging, ["dm", "read", tx, "--wallet", "bob"], obj={"output_format": "json"})
        assert result.exit_code == 0, result.output
        assert _read(result.output)["body"] == "one era only"

    def test_empty_store_keeps_no_dm_key_error(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc_cli.commands.messaging import messaging

        key_path = tmp_path / "bob.json"  # missing file → empty store
        _read_patches(monkeypatch, key_path, [{"messages": [_dm_row("ab" * 32, "whatever")]}])
        result = CliRunner().invoke(messaging, ["dm", "read", "ab" * 32, "--wallet", "bob"])
        assert result.exit_code != 0
        assert "No DM key for wallet" in (result.output + (result.stderr or ""))

    def test_corrupt_store_refused_and_left_byte_identical(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from aitbc_cli.commands.messaging import messaging

        key_path = tmp_path / "bob.json"
        key_path.write_bytes(b"{not json")
        before = key_path.read_bytes()
        _read_patches(monkeypatch, key_path, [{"messages": [_dm_row("ab" * 32, "whatever")]}])
        result = CliRunner().invoke(messaging, ["dm", "read", "ab" * 32, "--wallet", "bob"])
        assert result.exit_code != 0
        assert "unreadable" in (result.output + (result.stderr or ""))
        assert key_path.read_bytes() == before
