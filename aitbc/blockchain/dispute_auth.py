"""Signed-request proof for chain dispute mutations (#3052, AUDIT-DISPUTE-AUTH-HEADER-1).

The blockchain-node dispute write routes (``/rpc/disputes/file``,
``/evidence``, ``/verify-evidence``, ``/vote``) used to authenticate on a
bare ``X-Wallet-Address`` header trusted verbatim under
``TRUST_X_WALLET_ADDRESS=true`` — any caller could name a real arbitrator
and cast or revise votes that steer escrowed market funds. They now require
a secp256k1 signature over a canonical message binding the claimed address,
the exact route action, the full request payload, a freshness timestamp and
a single-use nonce — the same canonical-JSON + keccak scheme every signed
RPC request in this repo uses (``verify_request_signature`` /
``sign_transaction_data``).

``X-Wallet-Address`` survives only as the claimed-identity hint the signature
is verified against; the env flag no longer authorizes anything on these
routes. ``TRUST_X_WALLET_ADDRESS`` still gates the *other* routes that share
``get_authenticated_address`` (mining bookkeeping, arbitrator authorize /
revoke — the latter additionally verify an owner signature on-chain).

This module is the single place both sides build the signed dict, so the
CLI and the node cannot drift on the field set. The server adds the replay
guard (``issued_at`` skew + nonce spend) on top; the nonce itself is stored
node-side, so clients only mint a fresh random value per request.
"""

from __future__ import annotations

import time
from typing import Any

from aitbc.crypto.crypto import sign_transaction_data

#: Route actions bound into the signature. One per mutation endpoint so a
#: proof minted for ``file`` cannot be replayed against ``vote``.
ACTION_FILE = "rpc/disputes/file"
ACTION_EVIDENCE = "rpc/disputes/evidence"
ACTION_VERIFY_EVIDENCE = "rpc/disputes/verify-evidence"
ACTION_VOTE = "rpc/disputes/vote"

#: Request-body fields carrying the proof. Everything else in the body is
#: business payload and is covered by the signature.
SIGNATURE_FIELD = "signature"
ISSUED_AT_FIELD = "issued_at"
NONCE_FIELD = "nonce"
AUTH_FIELDS = frozenset({SIGNATURE_FIELD, ISSUED_AT_FIELD, NONCE_FIELD})


def dispute_sign_data(
    *,
    action: str,
    address: str,
    payload: dict[str, Any],
    issued_at: int,
    nonce: str,
    chain_id: str,
) -> dict[str, Any]:
    """Canonical dict a dispute mutation signature covers.

    ``payload`` is the request's business fields exactly as posted (the
    server reconstructs it from the fields the client actually sent, so
    defaults the client omitted are not signed). ``action`` binds the proof
    to one endpoint; ``address`` is the claimed ``X-Wallet-Address`` the
    recovered signer must equal. ``chain_id`` is the *serving* node's chain
    id (#3073): without it a captured signature is a bearer credential on
    every node and island — dispute state is node-local, so replaying one
    signed vote to N nodes applies the signer's action to N independent
    dispute copies. The server resolves its own chain id when verifying;
    the client learns it from ``GET /rpc/info``.
    """
    return {
        "action": action,
        "address": address,
        "payload": payload,
        "issued_at": issued_at,
        "nonce": nonce,
        "chain_id": chain_id,
    }


def new_dispute_proof_fields() -> dict[str, Any]:
    """Fresh ``issued_at``/``nonce`` pair for one signed dispute request."""
    import secrets

    return {"issued_at": int(time.time()), "nonce": secrets.token_hex(16)}


def sign_dispute_request(
    private_key: str,
    *,
    action: str,
    address: str,
    payload: dict[str, Any],
    issued_at: int,
    nonce: str,
    chain_id: str,
) -> str:
    """Sign ``dispute_sign_data`` with a secp256k1 private key (CLI side)."""
    return sign_transaction_data(
        dispute_sign_data(
            action=action, address=address, payload=payload, issued_at=issued_at, nonce=nonce, chain_id=chain_id
        ),
        private_key,
    )
