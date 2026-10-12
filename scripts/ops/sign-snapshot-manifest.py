#!/usr/bin/env python3
"""Sign a snapshot manifest (V-5 attested-snapshot signing step).

Reads a manifest JSON emitted by ``snapshot-manifest.py``, re-derives the
canonical bytes — the manifest serialized exactly as the generator emits it
(``json.dumps(obj, indent=2, sort_keys=True)``) with the signing-metadata
fields ``signature`` and ``signature_note`` removed — and signs those bytes
with EIP-191 ``personal_sign`` (``eth_account.messages.encode_defunct``).

The signature and a signer note are written back into the manifest file in
place; the file's mode and owner are preserved.

Key handling:

- The key comes only from ``--key-file`` (one line of 64 hex chars, optional
  ``0x`` prefix). It is never read from the environment or argv text, never
  printed, and never copied.
- A key file whose mode is not exactly ``0o600`` is refused.

A manifest that already carries a non-empty ``signature`` is refused — sign
a freshly generated manifest, or strip the field deliberately yourself.

Output: signer address and the sha256 digest of the canonical bytes only.

Exit status: 0 = signed; 2 = refused / error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys

SIGNING_METADATA_FIELDS = ("signature", "signature_note")


def canonical_bytes(manifest: dict) -> bytes:
    """The bytes that are signed: manifest minus signing-metadata fields,
    serialized exactly as snapshot-manifest.py emits it."""
    body = {k: v for k, v in manifest.items() if k not in SIGNING_METADATA_FIELDS}
    return json.dumps(body, indent=2, sort_keys=True).encode("utf-8")


def _read_key(path: str) -> str:
    st = os.stat(path)
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise ValueError(f"key file {path} must be mode 600 (got {oct(stat.S_IMODE(st.st_mode))})")
    token = open(path, "rb").read().strip()
    if token.startswith(b"0x"):
        token = token[2:]
    if len(token) != 64 or any(c not in b"0123456789abcdefABCDEF" for c in token):
        raise ValueError("key file must hold exactly one line of 64 hex characters")
    return "0x" + token.decode()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sign a snapshot manifest in place (EIP-191 personal_sign).")
    ap.add_argument("manifest", help="manifest JSON file; updated in place, mode/owner preserved")
    ap.add_argument("--key-file", required=True, help="path to a mode-600 file holding one 64-hex private key")
    args = ap.parse_args(argv)

    try:
        key = _read_key(args.key_file)
    except (OSError, ValueError) as e:
        print(f"key-file refused: {e}", file=sys.stderr)
        return 2

    try:
        manifest = json.load(open(args.manifest))
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read manifest: {e}", file=sys.stderr)
        return 2
    if not isinstance(manifest, dict):
        print("manifest is not a JSON object", file=sys.stderr)
        return 2
    if manifest.get("signature"):
        print("manifest already carries a signature — refusing to re-sign", file=sys.stderr)
        return 2

    body = canonical_bytes(manifest)
    digest = hashlib.sha256(body).hexdigest()

    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = Account.from_key(key)
    sig = acct.sign_message(encode_defunct(body)).signature.hex()

    manifest["signature"] = "0x" + sig
    manifest["signature_note"] = (
        f"EIP-191 personal_sign by {acct.address} over the canonical manifest bytes "
        "(signature/signature_note excluded; json.dumps indent=2 sort_keys=True)."
    )

    st = os.stat(args.manifest)
    fd = os.open(args.manifest, os.O_WRONLY | os.O_TRUNC)
    try:
        os.write(fd, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(args.manifest, stat.S_IMODE(st.st_mode))

    print(f"signer {acct.address}")
    print(f"digest 0x{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
