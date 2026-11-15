"""Wallet-ownership proof for provider-bond creation (#1967).

``Miner.capabilities["wallet_address"]`` is self-declared at registration —
nothing ties it to a key the provider controls, so before #1967 any caller
who could name a provider could bind *that provider's declared wallet* to an
on-chain ``bond_id`` the chain attributes to the wallet. Two miners sharing
one declared wallet could also share one bond.

The fix is a signed challenge at bond creation: the caller asks for a
single-use nonce bound to ``(provider_id, wallet)``, signs the canonical
message with the wallet key (EIP-191 ``personal_sign``, same shape as the
``/v1/auth/nonce`` login flow), and posts ``challenge_nonce`` +
``wallet_signature`` with the bond create. The nonce store is a small sqlite
file under ``AITBC_DATA_DIR`` — coordinator-api runs ``uvicorn --workers 2``,
so an in-process dict would lose nonces across workers (#1771); this mirrors
``island_ipfs_access.issue_swarm_key_nonce`` exactly, including the
``DELETE ... RETURNING`` burn-on-present consume.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address

logger = get_logger(__name__)

_NONCE_TTL_SECONDS = 300
_NONCE_MAX_PENDING = 10_000

_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    ImportError,
    sqlite3.Error,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_bond_challenge (
    nonce TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    wallet_address TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL
)
"""


def _nonce_db_path() -> Path:
    """Shared nonce store for provider-bond wallet proofs."""
    data_dir = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc/data"))
    return data_dir / "market" / "bond-challenges.db"


def _connect() -> sqlite3.Connection:
    """Open the shared nonce DB, creating schema on first use.

    ``isolation_level=None`` gives explicit transaction control so issue can
    hold a write lock (``BEGIN IMMEDIATE``) across the expiry sweep, the
    pending cap and the insert — two workers cannot both pass the cap check.
    """
    path = _nonce_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(_SCHEMA)
    return conn


def build_challenge_message(provider_id: str, wallet_address: str, nonce: str) -> str:
    """Canonical message the wallet must sign to prove bond ownership.

    Domain-separated from the login challenge ("log in to AITBC") so a
    signature captured for one purpose cannot be replayed for the other.
    """
    return (
        "Sign this message to bind a provider performance bond on AITBC.\n"
        f"Provider: {provider_id}\n"
        f"Wallet: {wallet_address.lower()}\n"
        f"Nonce: {nonce}"
    )


def issue_bond_challenge(provider_id: str, wallet_address: str) -> dict[str, Any]:
    """Issue a single-use bond-wallet challenge nonce bound to the provider."""
    now = time.time()
    expires_at = now + _NONCE_TTL_SECONDS
    nonce = secrets.token_urlsafe(24)
    wallet = canonical_address(wallet_address).lower()
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM provider_bond_challenge WHERE expires_at <= ?", (now,))
            pending = conn.execute("SELECT COUNT(*) FROM provider_bond_challenge").fetchone()
            if pending is not None and int(pending[0]) >= _NONCE_MAX_PENDING:
                conn.execute("ROLLBACK")
                raise PermissionError("Too many pending provider-bond challenges")
            conn.execute(
                "INSERT INTO provider_bond_challenge"
                " (nonce, provider_id, wallet_address, expires_at, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (nonce, provider_id, wallet, expires_at, now),
            )
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    return {
        "nonce": nonce,
        "message": build_challenge_message(provider_id, wallet, nonce),
        "wallet_address": wallet,
        "expires_in": _NONCE_TTL_SECONDS,
    }


def _consume_challenge(nonce: str) -> dict[str, Any] | None:
    """Atomically burn a challenge nonce and return its binding record.

    The DELETE...RETURNING runs under BEGIN IMMEDIATE, so exactly one
    worker/process can burn a given nonce — burn-on-present semantics: a
    nonce presented with the wrong binding is still spent.
    """
    if not nonce:
        return None
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "DELETE FROM provider_bond_challenge WHERE nonce = ? RETURNING provider_id, wallet_address, expires_at",
                (nonce,),
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    if row is None:
        return None
    provider_id, wallet, expires_at = row
    return {"provider_id": provider_id, "wallet_address": wallet, "expires_at": float(expires_at)}


def verify_bond_wallet_proof(provider_id: str, wallet_address: str, nonce: str, signature: str) -> bool:
    """Verify a bond-wallet challenge response end to end.

    Returns False on any failure: unknown/expired/replayed nonce, binding
    mismatch (nonce issued for another provider or wallet), missing
    signature, or a signature that does not recover to ``wallet_address``.
    The nonce is consumed even when the signature is bad — a failed attempt
    cannot be retried with the same nonce.
    """
    if not nonce or not signature:
        return False
    try:
        record = _consume_challenge(nonce)
    except _OPS_ERRORS:
        logger.warning("Provider-bond challenge consume failed", exc_info=True)
        return False
    if record is None:
        return False
    if record["expires_at"] <= time.time():
        return False
    expected_wallet = canonical_address(wallet_address).lower()
    if record["provider_id"] != provider_id or record["wallet_address"] != expected_wallet:
        return False

    message = build_challenge_message(provider_id, expected_wallet, nonce)
    # Function-local: eth_account pulls in the coincurve/eth-keys chain and
    # this module is imported on coordinator start; verification only runs
    # on bond creation.
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from eth_keys.exceptions import BadSignature
    from eth_utils.exceptions import ValidationError

    try:
        signable = encode_defunct(text=message)
        sig_bytes = bytes.fromhex(signature.removeprefix("0x"))
        recovered = Account.recover_message(signable, signature=sig_bytes)
    except (OSError, ValueError, TypeError, AttributeError, RuntimeError, ImportError, BadSignature, ValidationError):
        return False
    return bool(recovered.lower() == expected_wallet)
