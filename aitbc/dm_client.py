"""Shared client-side crypto and store helpers for encrypted DMs (MSG-8/15).

Phase 1 direct messages are PyNaCl ``SealedBox`` (libsodium
``crypto_box_seal``) to the recipient's published ``dm_key``; the chain
carries ciphertext only and the node never sees plaintext. The X25519
private key is client state: one mode-600 JSON file per wallet in a
``dm-keys/`` dir that is a sibling of the wallet's directory — key
material stays out of the wallet file format entirely. Key eras
accumulate for rotation: old eras are kept so old ciphertext still opens.

This module is the transport-independent kernel shared by the CLI
(``cli/aitbc_cli/commands/messaging.py`` — the names are re-imported
there under their historical ``_name`` so its test-suite patch points
survive), the agent SDK (``aitbc_sdk.messaging``) and the MCP tools. It
signs nothing and touches no wallet file: the caller resolves the wallet
and hands in paths, keys and submit callables.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aitbc.messaging import DM_CONTEXT

from .messaging_client import MSG_RPC_PREFIX, UNREACHABLE, poll_read


def dm_keys_dir(wallet_path: Path) -> Path:
    """``<wallets_dir>/../dm-keys`` — alongside the wallet directory."""
    return wallet_path.parent.parent / "dm-keys"


class DmStoreCorruptError(ValueError):
    """The ``dm-keys`` store exists but is unreadable or malformed.

    Callers that would later *save* must surface this rather than treat it
    as an empty store — a corrupt file is never overwritten (no backup
    copies of key-bearing files: the operator restores from custody)."""


def dm_store_load(path: Path, *, strict: bool = False) -> dict[str, Any]:
    """The ``{"keys": [...]}`` DM key store.

    Missing file → empty store (first run). With ``strict=True`` — the mode
    every save-path uses — a parse error, read error or non-list ``keys``
    raises ``DmStoreCorruptError`` and nothing is touched; non-strict keeps
    the historical tolerant read (empty store) for display-only callers.
    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {"keys": []}
    except Exception as e:
        if strict:
            raise DmStoreCorruptError(f"DM key store {path} is unreadable ({e}); refusing to touch it") from e
        return {"keys": []}
    if isinstance(data, dict) and isinstance(data.get("keys"), list):
        return data
    if strict:
        raise DmStoreCorruptError(
            f"DM key store {path} is malformed (expected a dict with a 'keys' list); refusing to touch it"
        )
    return {"keys": []}


_DM_TMP_MAX_AGE_S = 600


def _sweep_dm_store_tmps(path: Path) -> None:
    """Remove leftover save temps of this store past the safe age.

    Matches the legacy ``<name>.tmp`` and the per-save ``.<name>.*.tmp``.
    Only regular files owned by the current user and older than
    ``_DM_TMP_MAX_AGE_S`` are removed, so a concurrent in-flight save is
    never touched. Best-effort per entry; never follows a symlink."""
    import os
    import time

    now = time.time()
    prefix = "." + path.name + "."
    legacy = path.name + ".tmp"
    try:
        entries = list(os.scandir(path.parent))
    except OSError:
        return
    for entry in entries:
        if entry.name != legacy and not (entry.name.startswith(prefix) and entry.name.endswith(".tmp")):
            continue
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            st = entry.stat(follow_symlinks=False)
            if st.st_uid != os.getuid() or now - st.st_mtime < _DM_TMP_MAX_AGE_S:
                continue
            Path(entry.path).unlink()
        except OSError:
            continue


def dm_store_save(path: Path, data: dict[str, Any]) -> None:
    """Persist the key store atomically at mode-600 (X25519 secret keys).

    The directory is created 0700 and stale save temps are swept (a crash
    can leave one behind — the legacy fixed ``<name>.tmp`` used to wedge
    the ``O_EXCL`` open for good). The payload goes to a unique same-dir
    ``.<name>.<random>.tmp`` created ``O_EXCL`` at 0600 — the secret is
    never on disk with a wider mode, under any umask — fsynced, then
    ``os.replace`` puts it in place and the directory is fsynced so the
    rename itself is durable. No backup copies are made."""
    import os
    import tempfile

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _sweep_dm_store_tmps(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        os.fchmod(fd, 0o600)  # mkstemp already creates 0600; belt and braces
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        # Some filesystems refuse a directory fsync; tolerate it.
        try:
            dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def dm_prepare_era(path: Path, *, rotate: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Pick or create the era a key publication should use — shared by the
    CLI ``dm keygen`` and the SDK ``dm_publish_key`` so the persist-before-
    publish order cannot drift.

    Returns ``(era, store)``; ``era`` is ``None`` when the newest era is
    already published and ``rotate`` was not requested (nothing to send).
    Otherwise the era carries ``published_tx: None`` and is **already on
    disk**: a retry reuses the stored unpublished era instead of minting a
    second key, so a crash between save and submit can never strand a
    published public half.
    """
    store = dm_store_load(path, strict=True)
    keys = store["keys"]
    if keys and not rotate:
        last = keys[-1]
        if last.get("published_tx"):
            return None, store
        return last, store  # unpublished era — retry publishes this one
    era = generate_key_era()
    keys.append(era)
    dm_store_save(path, store)
    return era, store


def dm_mark_published(path: Path, store: dict[str, Any], era: dict[str, Any], tx_hash: str) -> None:
    """Record the sealed ``dm_key`` tx on an already-persisted era."""
    era["published_tx"] = tx_hash
    dm_store_save(path, store)


def generate_key_era() -> dict[str, Any]:
    """A fresh X25519 era ``{"enc_pubkey", "secret_key", "published_tx": None}``
    (both halves base64). Append to the store after the ``dm_key`` envelope
    seals — never publish the secret half."""
    import base64

    from nacl.public import PrivateKey

    sk = PrivateKey.generate()
    return {
        "enc_pubkey": base64.b64encode(bytes(sk.public_key)).decode("ascii"),
        "secret_key": base64.b64encode(bytes(sk)).decode("ascii"),
        "published_tx": None,
    }


def seal_dm(recipient_pub_b64: str, sender: str, recipient: str, body: str) -> str:
    """Seal ``body`` for ``recipient`` under their published ``enc_pubkey``.

    The plaintext carries the ``aitbc-dm-v1`` inner header
    ``<context>\\n<sender>\\n<recipient>\\n<body>`` so the opener can bind
    the body to both identities before trusting it."""
    import base64

    from nacl.public import PublicKey, SealedBox

    plaintext = f"{DM_CONTEXT}\n{sender}\n{recipient}\n{body}".encode()
    box = SealedBox(PublicKey(base64.b64decode(recipient_pub_b64, validate=True)))
    return base64.b64encode(box.encrypt(plaintext)).decode("ascii")


def open_dm(secret_b64: str, sender: str, recipient: str, ct_b64: str) -> str:
    """Decrypt + verify the authenticated inner header. Raises ValueError on
    any failure — never returns unverified plaintext."""
    import base64
    import binascii

    from nacl.exceptions import CryptoError
    from nacl.public import PrivateKey, SealedBox

    try:
        ct = base64.b64decode(ct_b64.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as e:
        raise ValueError("ciphertext is not strict base64") from e
    try:
        plain = SealedBox(PrivateKey(base64.b64decode(secret_b64, validate=True))).decrypt(ct)
    except CryptoError as e:
        raise ValueError("decryption failed — wrong key or tampered ciphertext") from e
    try:
        text = plain.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("decrypted payload is not UTF-8") from e
    return dm_check_header(text, sender, recipient)


def dm_check_header(text: str, sender: str, recipient: str) -> str:
    """Verify the ``aitbc-dm-v1`` inner header and return the body, or raise.

    The header ties plaintext to both identities: header sender must equal
    the transaction signer, header recipient must equal this wallet. Any
    mismatch rejects — never a guess."""
    from aitbc.crypto.signature_recovery import canonical_address

    parts = text.split("\n", 3)
    if len(parts) != 4:
        raise ValueError("decrypted payload lacks the aitbc-dm-v1 header")
    context, h_sender, h_recipient, body = parts
    if context != DM_CONTEXT:
        raise ValueError("decrypted payload has the wrong context string")
    try:
        if canonical_address(h_sender) != canonical_address(sender):
            raise ValueError("header sender does not match the transaction signer")
        if canonical_address(h_recipient) != canonical_address(recipient):
            raise ValueError("header recipient is not this wallet")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("malformed address in the decrypted header") from e
    if not body:
        raise ValueError("decrypted payload has an empty body")
    return body


def dm_max_plaintext_bytes() -> int:
    """Room for the message after the sealed-box overhead + inner header."""
    # 4096 base64 chars = 3072 raw bytes; SealedBox adds 48 B; the header is
    # context + 2 newlines + two 42-char addresses + 1 newline ≈ 106 B.
    return 3072 - 48 - (len(DM_CONTEXT) + 3 + 84)


# -- index reads (ciphertext/metadata only — never plaintext) ----------------


def fetch_dm_key(rpc_url: str, address: str, *, timeout: float = 10.0) -> Any:
    """The recipient's published DM key ``{"enc_pubkey", ...}``, ``None`` on
    404 (no key published), ``UNREACHABLE`` on transport failure."""
    return poll_read(f"{rpc_url.rstrip('/')}{MSG_RPC_PREFIX}/dm-keys/{address}", timeout=timeout)


def fetch_dm_inbox(rpc_url: str, address: str, *, limit: int = 50, cursor: str | None = None, timeout: float = 10.0) -> Any:
    """One page of the ``dm`` inbox for ``address`` — ciphertext rows only."""
    import requests

    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    try:
        resp = requests.get(f"{rpc_url.rstrip('/')}{MSG_RPC_PREFIX}/dm/{address}", params=params, timeout=timeout)
    except requests.RequestException:
        return UNREACHABLE
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None
