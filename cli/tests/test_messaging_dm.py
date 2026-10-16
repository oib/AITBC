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
