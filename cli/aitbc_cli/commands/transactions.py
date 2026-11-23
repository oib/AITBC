"""
Transaction commands for AITBC CLI
"""

import hashlib
import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import click
from eth_utils import keccak

from aitbc import ValidationError
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.exceptions import AITBCError
from aitbc.config.hub import normalize_hub_base
from aitbc.utils import ait_to_units, format_ait
from aitbc.utils.units import DEFAULT_TX_FEE_AIT, DEFAULT_TX_FEE_UNITS
from aitbc.utils.validation import validate_address_strict

from ..config import get_config
from ..utils import DECIMAL, error, info, success, warning
from ..utils.error_handling import CLIError, abort
from ..utils.fee_guard import ALLOW_HIGH_FEE_OPTION, validate_tx_fee
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger, http_response_status
from ..utils.wallet import decrypt_private_key
from ..utils.wallet_paths import (
    WalletSearchResult,
    ambiguous_wallet_note,
    find_wallet_file_report,
    multisig_recipient_refusal,
    service_dir_wallet_note,
    wallet_not_found_message,
    wallet_search_dirs,
)
from ..utils.wallet_secret import resolve_wallet_password, wallet_password_options

logger = get_logger(__name__)

DEFAULT_RPC_URL = "http://127.0.0.1:8202"

# Expected failure surface for the transaction fallbacks below (#1860):
# aitbc/CLI error hierarchies plus filesystem, crypto-shape and data-shape
# builtins. Sites that re-raise CLIError keep that earlier clause.
_TRANSACTION_ERRORS = (
    AITBCError,
    CLIError,
    OSError,
    ArithmeticError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
)


def _pending_tx_hash(tx: dict[str, Any]) -> str:
    """Recompute a mempool entry's tx hash with the node's canonicalization.

    Mirrors ``aitbc_chain.mempool_common.compute_tx_hash`` (sha256 of the
    canonical JSON) — the node package is not a CLI dependency, so the three
    lines are duplicated. ``/rpc/pending`` entries do not carry their hash
    on the wire (#2197).
    """
    canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
    return f"0x{hashlib.sha256(canonical).hexdigest()}"


def _format_pending_amount(tx: dict[str, Any]) -> str:
    """Render a pending tx's amount in AIT.

    Mempool entries carry raw compute-units; printing them with an ``AIT``
    suffix overstated values by UNITS_PER_AIT (36,000,000x) (#2197).
    """
    raw = tx.get("amount", tx.get("value", 0))
    try:
        return format_ait(int(raw))
    except (TypeError, ValueError):
        return str(raw)


def _find_pending_tx(http_client: AITBCHTTPClient, tx_hash: str) -> dict[str, Any] | None:
    """Return the mempool entry for ``tx_hash`` decorated with
    ``status: "pending"``, or None when the tx is neither sealed nor pending.

    Best-effort: any lookup failure returns None so the caller still reports
    the original not-found (#2197).
    """
    try:
        data = http_client.get("/rpc/pending")
        transactions = data.get("transactions", []) if isinstance(data, dict) else []
    except _TRANSACTION_ERRORS:
        return None
    wanted = tx_hash.lower()
    for tx in transactions:
        if isinstance(tx, dict) and _pending_tx_hash(tx).lower() == wanted:
            return {**tx, "tx_hash": tx_hash, "status": "pending"}
    return None


def _find_pending_tx_anywhere(tx_hash: str, urls: list[str]) -> dict[str, Any] | None:
    """Probe each candidate node's mempool for ``tx_hash`` (#2361).

    A tx can be pending on the proposer's mempool while absent from the
    queried node's — reporting "not found" in that window is a false
    eviction signal. Best-effort like ``_find_pending_tx``: unreachable
    endpoints are skipped.
    """
    for url in urls:
        try:
            client = AITBCHTTPClient(base_url=url, timeout=10)
        except _TRANSACTION_ERRORS:
            continue
        pending_tx = _find_pending_tx(client, tx_hash)
        if pending_tx is not None:
            return pending_tx
    return None


# Transaction types whose apply path rejects any nonzero value — mirrors
# aitbc_chain.state.state_transition._ZERO_VALUE_TX_TYPES (the node package
# is not a CLI dependency, so the set is duplicated here).
# GPU_DEREGISTER is deliberately absent: the apply side moved it out of
# _ZERO_VALUE_TX_TYPES into a block_version >= 10 gate
# (state_transition.py), so it is not part of the mirrored set. A nonzero
# amount is still refused at apply; the CLI just no longer pre-empts it.
_ZERO_VALUE_TX_TYPES = frozenset(
    {"MESSAGE", "GOVERNANCE_EXECUTE", "GPU_REGISTER", "GPU_ALLOCATE", "GPU_MARKET", "VALIDATOR_DEACTIVATE"}
)
# v21 agent session lifecycle (AGENT-SPEND-B-1, #1142): mirrors
# state_transition._is_zero_value_tx_type at block_version >= 21.
_AGENT_SESSION_TX_TYPES = frozenset({"AGENT_SESSION_GRANT", "AGENT_SESSION_REVOKE"})


def _hub_rpc_url() -> str | None:
    """Hub/proposer blockchain RPC base URL from config, or None."""
    config = get_config()
    hub_rpc = getattr(config, "hub_blockchain_rpc_url", None) or normalize_hub_base(
        config.hub_discovery_url or "hub.aitbc.invalid"
    )
    if not hub_rpc:
        return None
    hub_rpc = hub_rpc.rstrip("/")
    if hub_rpc.endswith("/rpc"):
        hub_rpc = hub_rpc[:-4]
    return hub_rpc or None


def _resolve_transaction_rpc_url(rpc_url: str | None) -> str:
    """Return the RPC URL to submit a transaction from.

    Follower/customer nodes run a local blockchain RPC, but it cannot on its own
    propagate transactions to the proposer. When the default local RPC is used,
    prefer the hub's public blockchain RPC URL instead.
    """
    if rpc_url:
        return rpc_url
    config = get_config()
    rpc_url = getattr(config, "blockchain_rpc_url", DEFAULT_RPC_URL) or DEFAULT_RPC_URL
    if "localhost" in rpc_url or "127.0.0.1" in rpc_url:
        hub_rpc = _hub_rpc_url()
        if hub_rpc:
            return hub_rpc
    return rpc_url


def _pending_probe_urls(rpc_url: str) -> list[str]:
    """Mempool endpoints worth probing for a tx ``rpc_url`` cannot see.

    The mempool is node-local: a tx fanned out to the proposer can sit in the
    hub's pending set while the queried node has already evicted its copy (or
    never received it). Sealed txs are chain-wide, so only the pending probe
    needs the extra endpoints — the configured local RPC and the hub RPC,
    deduplicated against the resolved URL (#2361).
    """
    config = get_config()
    urls = [rpc_url]
    seen = {rpc_url.rstrip("/")}
    for candidate in (
        getattr(config, "blockchain_rpc_url", None),
        _hub_rpc_url(),
    ):
        if not candidate:
            continue
        candidate = candidate.rstrip("/")
        if candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


# The chain settles in integer compute-units (1 AIT = 36_000_000), so the default fee is
# expressed in those units too: 360_000 compute-units = 0.01 AIT.
DEFAULT_FEE_UNITS = DEFAULT_TX_FEE_UNITS
# Use the same wallet directory as wallet create command


@click.group(
    epilog="""Examples:

  aitbc transactions send --from wallet-1 --to 0x... --amount 10

  aitbc transactions pending"""
)
def transactions():
    """Send, batch, estimate fees, and query transactions."""
    pass


def _load_sender_private_key(sender_keystore: Path, sender_data: dict[str, Any], password: str):
    """Decrypt the wallet's private key, or read it for unencrypted wallets."""
    private_key_hex: str | None
    try:
        if sender_data.get("encrypted") and isinstance(sender_data.get("private_key"), dict):
            private_key_hex = decrypt_private_key(sender_keystore, password)
        elif sender_data.get("encrypted_private_key"):
            private_key_hex = decrypt_private_key(sender_keystore, password)
        else:
            # Unencrypted wallet (created with --no-encrypt)
            private_key_hex = sender_data.get("private_key")
            if not private_key_hex:
                abort(click.get_current_context(silent=True), "Wallet does not contain private key")
                return None  # unreachable (abort raises) — mypy narrowing

        # Strip 0x prefix if present
        if isinstance(private_key_hex, str) and private_key_hex.startswith("0x"):
            private_key_hex = private_key_hex[2:]

        from eth_keys import keys

        return keys.PrivateKey(bytes.fromhex(private_key_hex))
    except CLIError:
        raise
    except _TRANSACTION_ERRORS as e:
        logger.error("Error loading private key: %s", e)
        abort(None, f"Error loading private key: {e}")
        return None


def _resolve_nonce(rpc_url: str, sender_address: str) -> int:
    """Fetch the sender's on-chain nonce; abort the command on failure.

    A failed lookup must not mean nonce 0 — the wrong nonce produces an
    already-signed transaction the chain refuses.
    """
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
        account_data = http_client.get(f"/rpc/account/{sender_address}")
        nonce = account_data.get("nonce")
        if nonce is None:
            raise ValueError(f"/rpc/account/{sender_address} response carried no nonce")
        return int(nonce)
    except Exception as e:
        abort(
            None,
            f"Nonce lookup for {sender_address} via {rpc_url} failed: {e}. "
            "Check the node is serving this account or pass --rpc-url",
            from_exception=e,
        )
        raise AssertionError("unreachable: abort always raises") from e


def _resolve_next_nonce(rpc_url: str, sender_address: str, chain_id: str, nonce_offset: int = 0) -> int:
    """Pending-aware next nonce for ``sender_address`` (#2395 residual, #2398).

    The sealed account nonce does not move while the sender's earlier
    transactions sit in the mempool, so signing it again collides on the
    occupied (sender, nonce) slot. ``pending_nonce_floor`` advances past
    the sender's pending slots — which already counts this batch's earlier
    entries — so when the probe succeeds its answer IS the next nonce and
    ``nonce_offset`` must not be added again (#2479: a mid-batch seal leaves
    the mempool readable-but-empty while the sealed nonce has already
    advanced, and sealed+offset then skips nonces into an unsealable gap).
    The offset applies only when the probe itself failed and nothing better
    is known.
    """
    from ..utils.nonce import pending_nonce_floor

    sealed = _resolve_nonce(rpc_url, sender_address)
    client = AITBCHTTPClient(base_url=rpc_url, timeout=5)
    floor = pending_nonce_floor(client, sender_address, sealed, chain_id)
    if floor is None:
        warning(
            f"Pending-nonce probe failed for {sender_address}; falling back to "
            f"sealed nonce {sealed} + offset {nonce_offset} — the nonce is unverified "
            "and a mid-batch seal can gap it. Check `aitbc transactions pending` if a "
            "later send stalls."
        )
        return sealed + nonce_offset
    return floor


# secp256k1 group order — a private key must be a scalar in (0, n).
_SECP256K1N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# --key-env takes an env-var NAME, never key material; the name charset is
# the usual shell identifier so a pasted key can never be mistaken for one.
_ENV_VAR_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _resolve_env_key_sender(key_env: str) -> tuple[str, Any] | None:
    """Resolve ``key_env`` — an env-var NAME holding a private key — to
    ``(sender_address, private_key)``.

    There is no configured-address cross-check like TransactionService's
    GENESIS_ADDRESS comparison: the env key IS the identity, so the sender
    address is derived from the key itself and echoed to the operator before
    anything is signed. Fails closed on a bad name, an unset/empty variable,
    non-hex or wrong-length material, or an out-of-range scalar.
    """
    # Failures abort (non-zero exit) rather than returning None: an env-key
    # send that cannot identify its signer must never look like a soft skip.
    if re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", key_env):
        # A 32-byte hex string is a valid env name syntactically but is almost
        # certainly pasted key material — refuse it outright rather than rely
        # on the (unlikely) chance an env var happens to share the name.
        abort(
            None,
            "--key-env takes an environment variable NAME, not a private key — export the key and pass its variable name",
        )
        return None  # unreachable (abort raises) — mypy narrowing
    if not _ENV_VAR_NAME_RE.fullmatch(key_env):
        abort(None, f"--key-env must be an environment variable NAME (e.g. FAUCET_PRIVATE_KEY), got {key_env!r}")
        return None  # unreachable (abort raises) — mypy narrowing
    raw = os.environ.get(key_env, "").strip()
    if not raw:
        abort(
            None,
            f"Environment variable {key_env} is not set or is empty — "
            "it must hold the sender's private key (hex, optional 0x)",
        )
        return None  # unreachable (abort raises) — mypy narrowing
    try:
        from eth_keys import keys

        key_bytes = bytes.fromhex(raw.removeprefix("0x"))
        if len(key_bytes) != 32:
            raise ValueError(f"private key must be 32 bytes, got {len(key_bytes)}")
        if not 0 < int.from_bytes(key_bytes, "big") < _SECP256K1N:
            raise ValueError("private key is outside the secp256k1 scalar range")
        private_key = keys.PrivateKey(key_bytes)
    except _TRANSACTION_ERRORS as e:
        abort(None, f"Could not load private key from ${key_env}: {e}", from_exception=e)
        return None  # unreachable (abort raises) — mypy narrowing
    sender_address = canonical_address(str(private_key.public_key.to_checksum_address()))
    info(f"Env key ${key_env} derives sender address {sender_address}")
    return sender_address, private_key


def _confirm_env_key_send(
    sender_address: str,
    key_env: str,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    assume_yes: bool,
) -> None:
    """Gate env-key sends behind an explicit confirmation.

    Env-held keys bypass the wallet password/KMS flow entirely, so every
    ``--key-env`` send prompts unless ``--yes`` is passed (the MCP tool's own
    dry_run/confirm gate maps onto ``--yes``). The prompt names the derived
    sender address so the operator sees who pays before confirming; a "no"
    (or non-interactive stdin) aborts via click.Abort.
    """
    if assume_yes:
        return
    click.confirm(
        f"Send {amount} AIT (fee {fee} AIT) from {sender_address} (private key from ${key_env}) to {to_address}?",
        abort=True,
    )


def _refuse_multisig_recipient(to_address: str) -> None:
    """#2499: abort when ``to_address`` is a recorded multisig address.

    The lookup lives in ``utils.wallet_paths`` and scans every wallet
    search dir — ``wallet send`` shares the same gate.
    """
    refusal = multisig_recipient_refusal(to_address, wallet_search_dirs())
    if refusal is not None:
        abort(None, refusal)


def _send_transaction_impl(
    from_wallet: str | None,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    password: str | None,
    keystore_dir: Path | None = None,
    rpc_url: str | None = None,
    tx_type: str = "TRANSFER",
    payload: dict[str, Any] | None = None,
    nonce_offset: int = 0,
    key_env: str | None = None,
    assume_yes: bool = False,
    out: dict[str, Any] | None = None,
) -> str | None:
    """Send a secp256k1-signed transaction.

    The sender key comes from exactly one of: a wallet-service keystore
    (``from_wallet`` + ``password``) or an environment variable named by
    ``key_env``. Both paths share chain-id resolution, nonce lookup, signing
    and submission so they cannot drift apart.

    When ``out`` is given it is populated with the signed ``transaction``
    and the node's ``submit`` response so JSON-output callers can report the
    real outcome without scraping stderr (#2416).
    """
    rpc_url = _resolve_transaction_rpc_url(rpc_url)

    # Validate recipient address
    try:
        validate_address_strict(to_address)
    except ValidationError as e:
        logger.error("Invalid recipient address: %s", e)
        abort(None, f"Invalid recipient address: {e}")
        return None

    # #2499: a locally recorded multisig address has no spendable key —
    # funding it burns the funds. Every send through this impl (send,
    # batch, MCP transactions_send, bond/exchange/ipfs/messaging payouts)
    # shares the #2362 guard; it previously covered only ``wallet send``.
    _refuse_multisig_recipient(to_address)

    if not _validate_send_amount(tx_type, amount):
        return None

    _warn_if_session_grant_never_expires(tx_type, payload)

    sender_label: str
    if key_env is not None:
        # Env-held key path (#2328): the env var NAME is the only thing the
        # caller supplies — never key material. Signing supports the same
        # --type/--payload surface as the wallet path because both go through
        # _build_signed_transaction.
        resolved = _resolve_env_key_sender(key_env)
        if resolved is None:
            return None
        sender_address, private_key = resolved
        _confirm_env_key_send(sender_address, key_env, to_address, amount, fee, assume_yes)
        sender_label = f"env:{key_env} ({sender_address})"
    else:
        if not from_wallet:
            abort(None, "transactions send requires --from <wallet> or --key-env <NAME>")
            return None
        # Get sender wallet info. An explicit keystore_dir wins outright; otherwise
        # the shared search order applies (configured wallet dir, then the service
        # wallet dir — a wallet that only exists under /var/lib/aitbc/wallets is
        # still found by name).
        sender_keystore = _resolve_sender_keystore(from_wallet, keystore_dir)
        if sender_keystore is None:
            return None

        with open(sender_keystore) as f:
            sender_data = json.load(f)

        sender_address = sender_data["address"]

        # Decrypt private key if wallet is encrypted, otherwise use directly
        private_key = _load_sender_private_key(sender_keystore, sender_data, password or "")
        if private_key is None:
            return None
        sender_label = from_wallet

    chain_id = _resolve_send_chain_id(rpc_url)

    # Batch callers pass a per-sender offset: it is the fallback for when
    # the mempool probe cannot advance past pending slots — a readable
    # mempool already shows this batch's earlier pending entries, so the
    # floor resolve picks the next free nonce without double-counting.
    actual_nonce = _resolve_next_nonce(rpc_url, sender_address, chain_id, nonce_offset)

    transaction = _build_signed_transaction(
        chain_id=chain_id,
        sender_address=sender_address,
        to_address=to_address,
        amount=amount,
        fee=fee,
        nonce=actual_nonce,
        tx_type=tx_type,
        payload=payload,
        private_key=private_key,
    )

    # Submit to blockchain
    submit = _submit_signed_transaction(rpc_url, transaction, sender_label, to_address)
    if out is not None:
        out["transaction"] = transaction
        out["submit"] = submit
        out["sender_address"] = sender_address
    if submit is None:
        return None
    return submit.get("transaction_hash")


def _warn_if_session_grant_never_expires(tx_type: str, payload: dict[str, Any] | None) -> None:
    """#2277: AGENT_SESSION_GRANT without ``expires_at_height`` grants a spend
    session that never expires — the chain accepts it silently
    (agent_spend._grant_verdict treats a missing expiry as unbounded), so the
    CLI must say so out loud. Covers ``send`` and batch entries alike."""
    if tx_type.upper() != "AGENT_SESSION_GRANT":
        return
    if payload is not None and payload.get("expires_at_height") is not None:
        return
    warning(
        "AGENT_SESSION_GRANT payload has no expires_at_height — the spend "
        'session will never expire. Pass "expires_at_height": <future block '
        "height> in --payload to bound it."
    )


def _validate_send_amount(tx_type: str, amount: Decimal) -> bool:
    """Validate amount/fee. Zero-value types (mirrors
    aitbc_chain.state.state_transition._ZERO_VALUE_TX_TYPES — no shared
    constants package exists) are REJECTED by apply when value != 0, so
    they need --amount 0; for every other type a zero amount is a no-op
    that only burns the fee, kept an error."""
    upper = tx_type.upper()
    if upper in _ZERO_VALUE_TX_TYPES or upper in _AGENT_SESSION_TX_TYPES:
        if amount != 0:
            error(f"{upper} transactions must have amount=0")
            return False
    elif amount <= 0:
        logger.error("Invalid amount: %s must be positive", amount)
        error("Amount must be positive")
        return False
    return True


def _resolve_sender_keystore(from_wallet: str, keystore_dir: Path | None) -> Path | None:
    """Locate the sender keystore; reports and returns None when absent."""
    report: WalletSearchResult | None = None
    sender_keystore: Path | None
    if keystore_dir is not None:
        sender_keystore = keystore_dir / f"{from_wallet}.json"
    else:
        report = find_wallet_file_report(from_wallet)
        sender_keystore = report.path
        note = ambiguous_wallet_note(report)
        if note:
            warning(note)
        service_note = service_dir_wallet_note(report)
        if service_note:
            info(service_note)
    if sender_keystore is None or not sender_keystore.exists():
        if report is not None:
            error(wallet_not_found_message(report))
        else:
            error(f"Wallet '{from_wallet}' not found at {sender_keystore}")
        return None
    return sender_keystore


def _resolve_send_chain_id(rpc_url: str) -> str:
    """Resolve chain_id and nonce source from the blockchain node.

    An explicit CHAIN_ID wins; otherwise the node must advertise one — a
    silent default signs a transaction no node serves. (No ctx here: the
    send/batch commands carry no --chain-id.)
    """
    from ..utils.chain_id import get_chain_id

    chain_id = os.getenv("CHAIN_ID") or ""
    if not chain_id:
        try:
            chain_id = get_chain_id(rpc_url, override=None, timeout=5, strict=True)
        except Exception as e:
            abort(
                None,
                f"Chain ID lookup via {rpc_url} failed: {e}. Set CHAIN_ID or point --rpc-url at a serving node",
                from_exception=e,
            )
            raise AssertionError("unreachable: abort always raises") from e
    return chain_id


def _build_signed_transaction(
    *,
    chain_id: str,
    sender_address: str,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    nonce: int,
    tx_type: str,
    payload: dict[str, Any] | None,
    private_key,
) -> dict[str, Any]:
    """Assemble the transaction dict and attach the canonical-JSON signature."""
    # Convert AIT to compute-units (chain unit)
    amount_seconds = ait_to_units(amount)
    fee_seconds = ait_to_units(fee)

    # The TransactionRequest model adds to/amount to payload, so we include them up front
    # and sign over the exact dict the verifier will hash.
    tx_payload = dict(payload) if payload else {}
    if "to" not in tx_payload:
        tx_payload["to"] = to_address
    if "amount" not in tx_payload:
        tx_payload["amount"] = amount_seconds
    transaction = {
        "chain_id": chain_id,
        "from": sender_address,
        "to": to_address,
        "amount": amount_seconds,
        "fee": fee_seconds,
        "nonce": nonce,
        "type": tx_type,
        "payload": tx_payload,
    }

    # Sign the canonical JSON (sort_keys, compact) of all fields except the signature.
    message = json.dumps(transaction, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign_msg_hash(keccak(message))
    transaction["signature"] = signature.to_bytes().hex()
    return transaction


def _submit_signed_transaction(
    rpc_url: str, transaction: dict[str, Any], from_wallet: str, to_address: str
) -> dict[str, Any] | None:
    """POST the signed transaction to the blockchain RPC.

    Returns the node's response body (``transaction_hash`` plus any
    ``peer_relay``/``warning``/``info`` fields, #2361) so callers can report
    the real submit outcome; ``None`` on failure."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        result = http_client.post("/rpc/transaction", json=transaction)
        tx_hash = result.get("transaction_hash")
        success(f"Transaction submitted, not confirmed: {tx_hash}")
        if result.get("info"):
            info(result["info"])
        logger.info("Transaction submitted (unconfirmed): %s from %s to %s", tx_hash, from_wallet, to_address)
        return result
    except NetworkError as e:
        logger.error("Network error submitting transaction: %s", e)
        abort(None, f"Error submitting transaction: {e}")
        return None
    except _TRANSACTION_ERRORS as e:
        logger.error("Error submitting transaction: %s", e)
        abort(None, f"Error: {e}")
        return None


def _parse_payload_json(payload: str | None) -> dict[str, Any] | None:
    """Parse the --payload JSON object, reporting errors instead of raising."""
    if not payload:
        return None
    try:
        parsed_payload = json.loads(payload)
        if not isinstance(parsed_payload, dict):
            abort(click.get_current_context(silent=True), "Payload must be a JSON object")
            return None  # unreachable (abort raises) — mypy narrowing
        return parsed_payload
    except json.JSONDecodeError as e:
        abort(None, f"Invalid payload JSON: {e}")
        return None


def _wallet_file_present(wallet_name: str | None) -> bool:
    """True when ``<wallet_name>.json`` resolves in the shared wallet search.

    #2450: secret-bearing leaves gate on the wallet before the password
    source, so a bad ``--password-file`` cannot preempt the wallet refusal.
    """
    if not wallet_name:
        return False
    report = find_wallet_file_report(wallet_name)
    return report.path is not None and report.path.exists()


def _resolve_send_password(
    ctx: click.Context | None,
    from_wallet: str | None,
    key_env: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
) -> str | None:
    """Validate the sender selection and resolve the wallet password (#2328).

    Exactly one of ``--from``/``--key-env`` must be given; only the wallet
    path has a password — env-key sends sign with the raw key and gate on
    ``--yes``/confirmation instead. Extracted from ``send`` for the c901
    complexity ratchet.
    """
    if (from_wallet is None) == (key_env is None):
        abort(ctx, "Exactly one of --from <wallet> or --key-env <NAME> is required")
    if from_wallet is None:
        return None
    if not _wallet_file_present(from_wallet):
        # #2450: wallet gate before secret gate — _send_transaction_impl
        # reports the missing wallet; resolving the password here would let
        # a bad --password-file preempt that refusal.
        return None
    return resolve_wallet_password(
        from_wallet,
        password=password,
        password_file=password_file,
        password_stdin=password_stdin,
        allow_unencrypted=True,
        ctx=ctx,
    )


@transactions.command(
    epilog="""Examples:

  aitbc transactions send --from wallet-1 --to 0x... --amount 10

  aitbc transactions send --from wallet-1 --to 0x... --amount 10 --fee 0.01

  aitbc transactions send --key-env FAUCET_PRIVATE_KEY --to 0x... --amount 10 --yes"""
)
@click.option("--from", "from_wallet", required=False, help="From wallet name (mutually exclusive with --key-env)")
@click.option(
    "--key-env",
    "key_env",
    default=None,
    metavar="NAME",
    help=(
        "Environment variable NAME holding the sender's private key (hex, optional 0x) "
        "— e.g. FAUCET_PRIVATE_KEY. Only the variable NAME is passed, never key "
        "material. The sender address is derived from the key and shown before "
        "sending. Mutually exclusive with --from; requires confirmation or --yes."
    ),
)
@click.option("--yes", "assume_yes", is_flag=True, help="Skip the --key-env send confirmation prompt")
@click.option("--to", "to_address", required=True, help="To address")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to send")
@click.option(
    "--fee", type=DECIMAL, default=DEFAULT_TX_FEE_AIT, show_default=True, help="Transaction fee (standard chain fee)"
)
@ALLOW_HIGH_FEE_OPTION
@wallet_password_options
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--type", "tx_type", default="TRANSFER", help="Transaction type (default TRANSFER)")
@click.option("--payload", help="JSON payload for non-standard transaction types")
@click.option(
    "--nonce-offset",
    type=int,
    default=0,
    show_default=True,
    help="Extra nonce offset, used only when the node's mempool cannot be read "
    "(a readable mempool already yields the next free nonce, #2395/#2398)",
)
@click.option("--use-explorer", is_flag=True, help="Use Explorer API for status checks")
def send(
    from_wallet: str | None,
    key_env: str | None,
    assume_yes: bool,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    allow_high_fee: bool,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    rpc_url: str | None,
    tx_type: str,
    payload: str | None,
    nonce_offset: int,
    use_explorer: bool,
):
    """Send a transaction from one wallet to another.

    The sender key comes from either --from (a wallet-service keystore,
    unlocked with the wallet password options) or --key-env NAME (an
    environment variable holding a raw private key — for service-held keys
    like FAUCET_PRIVATE_KEY that have no wallet entry). Env-key sends support
    the same --type/--payload options and always show the derived sender
    address; they prompt for confirmation unless --yes is given.
    """
    ctx = click.get_current_context(silent=True)
    validate_tx_fee(ctx, fee, allow_high_fee=allow_high_fee)
    password = _resolve_send_password(ctx, from_wallet, key_env, password, password_file, password_stdin)

    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

    parsed_payload: dict[str, Any] | None = None
    if payload:
        parsed_payload = _parse_payload_json(payload)
        if parsed_payload is None:
            return

    send_out: dict[str, Any] = {}
    tx_hash = _send_transaction_impl(
        from_wallet,
        to_address,
        amount,
        fee,
        password,
        rpc_url=rpc_url,
        tx_type=tx_type,
        payload=parsed_payload,
        nonce_offset=nonce_offset,
        key_env=key_env,
        assume_yes=assume_yes,
        out=send_out,
    )
    if not tx_hash:
        # _send_transaction_impl already printed the specific refusal (bad amount,
        # missing wallet, unreadable key); abort here so the command cannot exit 0 —
        # the same boundary hub_orders uses ("see the error above").
        abort(
            click.get_current_context(silent=True),
            "Transaction failed — see the error above",
        )

    success(f"Transaction sent: {tx_hash}")

    json_output = ctx is not None and ctx.obj and ctx.obj.get("output_format") == "json"
    explorer_result = _check_explorer_status(tx_hash, use_explorer, quiet=json_output)
    if json_output:
        _emit_send_json_document(send_out, tx_hash, tx_type, from_wallet, key_env, to_address, amount, fee, explorer_result)

    # Check if first wallet is unencrypted


def _check_explorer_status(tx_hash: str | None, use_explorer: bool, *, quiet: bool) -> dict[str, Any] | None:
    """Fetch explorer status for a submitted tx; prints it unless ``quiet``.

    In JSON-output mode the result is folded into the single stdout document
    instead of being echoed separately (#2416)."""
    if not use_explorer:
        return None
    try:
        config = get_config()
        http_client = AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)
        result = http_client.get(f"/api/transactions/by-hash/{tx_hash}")
        if not quiet:
            success("Transaction status (via Explorer):")
            click.echo(json.dumps(result, indent=2))
        return result
    except NetworkError as e:
        if http_response_status(e) == 404:
            error(f"Transaction {tx_hash} not found")
        else:
            error(f"Explorer API unavailable: {e}")
    except _TRANSACTION_ERRORS as e:
        abort(None, f"Error checking status via Explorer: {e}")
    return None


def _emit_send_json_document(
    send_out: dict[str, Any],
    tx_hash: str | None,
    tx_type: str,
    from_wallet: str | None,
    key_env: str | None,
    to_address: str,
    amount: Decimal,
    fee: Decimal,
    explorer_result: dict[str, Any] | None,
) -> None:
    """Emit the single machine-readable document for ``send --output json`` (#2416).

    Human-readable status lines stay on stderr via success/error; this is the
    only stdout write in JSON mode so `jq` sees exactly one document.
    """
    transaction = send_out.get("transaction") or {}
    submit = send_out.get("submit") or {}
    doc: dict[str, Any] = {
        "transaction_hash": tx_hash,
        "status": "submitted",
        "type": tx_type,
        "chain_id": transaction.get("chain_id"),
        "from": send_out.get("sender_address"),
        "from_wallet": from_wallet,
        "key_env": key_env,
        "to": to_address,
        "amount_ait": str(amount),
        "fee_ait": str(fee),
        "nonce": transaction.get("nonce"),
        "fee_units": transaction.get("fee"),
    }
    for passthrough in ("peer_relay", "warning", "info"):
        if passthrough in submit:
            doc[passthrough] = submit[passthrough]
    if explorer_result is not None:
        doc["explorer"] = explorer_result
    click.echo(json.dumps(doc, indent=2))


def _process_batch_entry(
    tx: dict[str, Any],
    password: str | None,
    rpc_url: str,
    seen_entries: set,
    seen_hashes: set,
    nonce_offsets: dict[str, int],
    results: list,
) -> None:
    """Send one batch entry, deduping identical entries and duplicate hashes."""
    try:
        # amounts come out of a JSON batch file as numbers; convert at the boundary
        amount = Decimal(str(tx["amount"]))
        # default fee matches `send --fee` (standard chain fee), not the old 10 AIT
        fee = Decimal(str(tx.get("fee", DEFAULT_TX_FEE_AIT)))
        # #1997: entries may carry the same type/payload keys `send` exposes so a
        # batch can queue typed nonces, not just TRANSFERs.
        tx_type = str(tx.get("type") or "TRANSFER").upper()
        payload = tx.get("payload")
        if isinstance(payload, str):
            payload = _parse_payload_json(payload)
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("batch entry 'payload' must be a JSON object")
        entry_key = (
            tx["from_wallet"],
            str(tx["to_address"]).lower(),
            amount,
            fee,
            tx_type,
            json.dumps(payload, sort_keys=True) if payload else None,
        )
        if entry_key in seen_entries:
            results.append(
                {"transaction": tx, "hash": None, "success": False, "skipped": True, "error": "duplicate batch entry"}
            )
            error(f"Duplicate batch entry skipped: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
            return
        seen_entries.add(entry_key)

        from_wallet = tx["from_wallet"]
        tx_hash = _send_transaction_impl(
            from_wallet,
            tx["to_address"],
            amount,
            fee,
            password,
            rpc_url=rpc_url,
            tx_type=tx_type,
            payload=payload,
            nonce_offset=nonce_offsets.get(from_wallet, 0),
        )
        if tx_hash:
            nonce_offsets[from_wallet] = nonce_offsets.get(from_wallet, 0) + 1
            if tx_hash in seen_hashes:
                results.append(
                    {
                        "transaction": tx,
                        "hash": tx_hash,
                        "success": False,
                        "error": f"duplicate transaction hash {tx_hash}",
                    }
                )
                abort(None, f"Transaction produced a duplicate hash: {tx['from_wallet']} → {tx['to_address']}")
            seen_hashes.add(tx_hash)
        results.append({"transaction": tx, "hash": tx_hash, "success": tx_hash is not None})

        if tx_hash:
            success(f"Transaction sent: {tx['from_wallet']} → {tx['to_address']} ({tx['amount']} AIT)")
        else:
            error(f"Transaction failed: {tx['from_wallet']} → {tx['to_address']}")

    except CLIError:
        # Lookup failures abort the batch. A chain-id failure is systemic
        # (same rpc_url for every entry); a nonce 404 is per sender — but
        # either way there is nothing valid to sign with, so the caller
        # prints a partial summary and the command exits non-zero.
        raise
    except _TRANSACTION_ERRORS as e:
        results.append({"transaction": tx, "hash": None, "success": False, "error": str(e)})
        abort(None, f"Transaction error: {e}")


@transactions.command(
    epilog="""Examples:

  aitbc transactions batch --transactions-file /tmp/txs.json

  aitbc transactions batch --transactions-file /tmp/txs.json --password-file /tmp/pass

  aitbc transactions batch --transactions '[{"from_wallet": "shop", "to_address": "0x...", "amount": 0.1}]'

  The batch file is a JSON list of objects with keys:
    from_wallet  — sender wallet name (required)
    to_address   — recipient 0x address (required)
    amount       — AIT amount to send (required)
    fee          — AIT fee (optional, defaults to the standard chain fee like `send --fee`)
    type         — transaction type (optional, default TRANSFER; same values as `send --type`)
    payload      — JSON object payload for non-standard types (optional, same as `send --payload`)"""
)
@click.option("--transactions-file", help="JSON file with batch transactions")
@click.option(
    "--transactions",
    "transactions_json",
    help="Inline JSON batch (same shape as --transactions-file); exactly one of the two is required",
)
@wallet_password_options
@click.option("--rpc-url", help="Blockchain RPC URL")
def batch(
    transactions_file: str | None,
    transactions_json: str | None,
    password: str | None,
    password_file: str | None,
    password_stdin: bool,
    rpc_url: str | None,
):
    """Send multiple transactions from a JSON batch.

    Entries are objects ``{"from_wallet", "to_address", "amount", "fee"?}``
    with amounts in AIT. Identical entries are rejected as duplicates instead
    of being reported as two successes for the same on-chain hash.
    """
    if bool(transactions_file) == bool(transactions_json):
        abort(None, "Pass exactly one of --transactions-file or --transactions")
    if transactions_file:
        with open(transactions_file) as f:
            transactions_data = json.load(f)
    else:
        try:
            transactions_data = json.loads(transactions_json or "")
        except json.JSONDecodeError as e:
            abort(None, f"--transactions is not valid JSON: {e}")
    if not isinstance(transactions_data, list):
        abort(None, "Batch must be a JSON list of transaction objects")
    first_wallet = transactions_data[0].get("from_wallet") if transactions_data else None
    # #2450: same wallet-before-secret order as `send` — when the wallet file
    # is absent the per-entry impl reports the wallet refusal instead of a
    # password-source error preempting it.
    password = (
        resolve_wallet_password(
            first_wallet,
            password=password,
            password_file=password_file,
            password_stdin=password_stdin,
            allow_unencrypted=True,
            ctx=click.get_current_context(silent=True),
        )
        if _wallet_file_present(first_wallet)
        else None
    )

    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

    # The chain's account nonce does not move while earlier batch transactions
    # sit in the mempool, so entries from the same wallet sign with per-entry
    # nonce offsets — otherwise identical entries produce the same tx hash and
    # the mempool silently dedupes them while the CLI reported "2/2 successful".
    seen_entries: set[tuple[str, str, Decimal, Decimal]] = set()
    seen_hashes: set[str] = set()
    nonce_offsets: dict[str, int] = {}

    results: list[dict[str, Any]] = []
    for index, tx in enumerate(transactions_data, start=1):
        try:
            _process_batch_entry(tx, password, rpc_url, seen_entries, seen_hashes, nonce_offsets, results)
        except CLIError:
            # Say what already went out before aborting: earlier entries were
            # submitted to the node and their hashes are the only receipt.
            submitted = [r["hash"] for r in results if r.get("hash")]
            error(
                f"Batch aborted at entry {index}/{len(transactions_data)} "
                f"(from_wallet={tx.get('from_wallet', '?')}): {len(submitted)} "
                f"transaction(s) already submitted: {', '.join(str(h) for h in submitted) or 'none'}"
            )
            raise

    succeeded = len([r for r in results if r["success"]])
    # Skipped duplicate entries are a designed skip (a retry resubmitting an
    # already-processed file must not fail) — only real send failures abort.
    skipped = len([r for r in results if r.get("skipped")])
    failed = len(results) - succeeded - skipped
    summary = f"Batch completed: {succeeded}/{len(results)} successful"
    if skipped:
        summary += f" ({skipped} duplicate(s) skipped)"
    success(summary)
    if failed:
        # Report the partial summary above first — submitted hashes are the only
        # receipt — then exit non-zero: a batch that dropped rows is not a success.
        abort(
            click.get_current_context(silent=True),
            f"Batch incomplete: {failed}/{len(results)} transactions failed ({skipped} skipped)",
        )


@transactions.command(
    epilog="""Examples:

  aitbc transactions status --tx-hash 0x...

  aitbc transactions status --tx-hash 0x... --use-explorer"""
)
@click.option("--tx-hash", "tx_hash", required=True, help="The Tx hash.")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API instead of RPC")
def status(tx_hash: str, rpc_url: str | None, use_explorer: bool):
    """Get the status of a transaction by its hash."""
    if use_explorer:
        try:
            config = get_config()
            http_client = AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)
            result = http_client.get(f"/api/transactions/by-hash/{tx_hash}")
            success(f"Transaction status for {tx_hash} (via Explorer)")
            click.echo(json.dumps(result, indent=2))
        except NetworkError as e:
            if http_response_status(e) == 404:
                abort(None, f"Transaction {tx_hash} not found", from_exception=e)
            else:
                abort(None, f"Explorer API unavailable: {e}", from_exception=e)
        except _TRANSACTION_ERRORS as e:
            abort(None, f"Error: {e}", from_exception=e)
    else:
        if not rpc_url:
            rpc_url = _resolve_transaction_rpc_url(None)

        try:
            http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
            result = http_client.get(f"/rpc/transaction/{tx_hash}")
            success(f"Transaction status for {tx_hash}")
            click.echo(json.dumps(result, indent=2))
        except NetworkError as e:
            if http_response_status(e) == 404:
                pending_tx = _find_pending_tx_anywhere(tx_hash, _pending_probe_urls(rpc_url))
                if pending_tx is not None:
                    success(f"Transaction status for {tx_hash}")
                    click.echo(json.dumps(pending_tx, indent=2))
                    return
                abort(
                    None,
                    f"Transaction {tx_hash} not found (not sealed and not pending on any reachable node)",
                    from_exception=e,
                )
            abort(None, f"Error getting transaction status: {e}", from_exception=e)
        except _TRANSACTION_ERRORS as e:
            abort(None, f"Error: {e}", from_exception=e)


@transactions.command(
    epilog="""Examples:

  aitbc transactions pending

  aitbc transactions pending --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def pending(ctx, rpc_url: str | None):
    """Get the list of pending transactions from the node."""
    if not rpc_url:
        rpc_url = _resolve_transaction_rpc_url(None)

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=30)
        data = http_client.get("/rpc/pending")
        transactions = data.get("transactions", [])
        if ctx.obj and ctx.obj.get("output_format") == "json":
            click.echo(json.dumps(transactions, indent=2))
            return
        success(f"Pending transactions: {len(transactions)}")
        for tx in transactions:
            tx_hash = tx.get("hash") or tx.get("tx_hash") or tx.get("id")
            tx_type = tx.get("type", "TRANSFER")
            amount = _format_pending_amount(tx)
            sender = tx.get("from", "?")
            if tx_hash:
                click.echo(f"  - {tx_hash}: {amount} ({tx_type})")
            else:
                click.echo(f"  - {tx_type} {amount} from {sender[:16]}...")
    except NetworkError as e:
        abort(None, f"Error getting pending transactions: {e}")
    except _TRANSACTION_ERRORS as e:
        abort(None, f"Error: {e}")


@transactions.command(
    epilog="""Examples:

  aitbc transactions estimate-fee --from wallet-1 --to 0x... --amount 10

  aitbc transactions estimate-fee --from wallet-1 --to 0x... --amount 10 --rpc-url http://localhost:8202"""
)
@click.option("--from", "from_wallet", required=True, help="From wallet name")
@click.option("--to", "to_address", required=True, help="To address")
@click.option("--amount", type=DECIMAL, required=True, help="Amount to send")
@click.option("--rpc-url", help="Blockchain RPC URL")
def estimate_fee(from_wallet: str, to_address: str, amount: Decimal, rpc_url: str | None):
    """Estimate the transaction fee for a transfer.

    The node has no fee-estimation endpoint (the old ``/rpc/estimateFee``
    call always 404'd and fell back here), so the estimate is the flat
    default fee applied to every transfer.
    """
    success(f"Estimated fee: {format_ait(DEFAULT_FEE_UNITS)} (default)")


@transactions.command(
    epilog="""Examples:

  aitbc transactions search --address 0x...

  aitbc transactions search --sender 0x... --limit 50

  aitbc transactions search --address 0x... --limit 50 --use-explorer"""
)
@click.option("--address", "address", help="Blockchain address on either side of the transaction.")
@click.option("--sender", "sender", help="Return only transactions sent by this address.")
@click.option("--recipient", "recipient", help="Return only transactions received by this address.")
@click.option("--limit", default=100, help="Number of transactions to return")
@click.option("--use-explorer", is_flag=True, help="Use Explorer API instead of RPC")
@click.option("--rpc-url", default=None, help="Blockchain RPC base URL (overrides config)")
def search(address: str, sender: str, recipient: str, limit: int, use_explorer: bool, rpc_url: str):
    """Search transactions by address, sender, or recipient."""
    if not address and not sender and not recipient:
        abort(None, "Provide at least one of --address, --sender or --recipient.")
    filters = {k: v for k, v in {"address": address, "sender": sender, "recipient": recipient}.items() if v}
    if use_explorer:
        if sender or recipient:
            abort(None, "The Explorer API cannot filter by sender or recipient. Omit --use-explorer to use the RPC path.")
        _search_via_explorer(address, limit)
    else:
        _search_via_rpc(filters, sender, recipient, limit, rpc_url)


def _search_via_explorer(address: str, limit: int) -> None:
    try:
        config = get_config()
        http_client = AITBCHTTPClient(base_url=config.explorer_api_url, timeout=30)
        params = {"address": address, "limit": limit}
        result = http_client.get("/api/transactions/search", params=params)
        transactions = [_normalize_search_row(r) for r in result.get("transactions", [])]
        # #2439: stdout is the JSON payload — status goes to stderr.
        success(f"Found {len(transactions)} transactions for {address} (via Explorer)", err=True)
        click.echo(json.dumps(transactions, indent=2))
    except NetworkError as e:
        abort(None, f"Explorer API unavailable: {e}")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure reports cleanly
        abort(None, f"Error searching transactions: {e}")


def _row_matches(row: object, key: str, want: str) -> bool:
    if not isinstance(row, dict):
        return False
    return str(row.get(key, "")).lower() == want.lower()


def _normalize_search_row(row: object) -> object:
    """#2439: one money representation and a filled timestamp in JSON output.

    ``value``/``fee`` arrive as raw compute-units while ``wallet
    transactions`` prints AIT strings — emit the same ``format_ait`` string
    and keep the raw units under ``*_units``. ``timestamp`` falls back to
    ``created_at``/``block_timestamp`` so older rows stop reporting null.
    """
    if not isinstance(row, dict):
        return row
    out = dict(row)
    value_raw = out.get("value")
    for key in ("value", "fee"):
        raw = out.get(key)
        if raw is None or (isinstance(raw, str) and raw.endswith(" AIT")):
            continue
        try:
            out[key] = format_ait(raw)
        except Exception:  # noqa: BLE001 - non-numeric payload field stays as-is
            continue
        out[f"{key}_units"] = raw
    # "amount" is the explorer's alias for "value" — mirror the formatted
    # value so no raw base-unit duplicate survives in the payload.
    if "amount" in out and out.get("amount") == value_raw and "value" in out:
        out["amount"] = out["value"]
        if value_raw is not None:
            out["amount_units"] = value_raw
    if not out.get("timestamp"):
        out["timestamp"] = out.get("created_at") or out.get("block_timestamp")
    return out


def _search_via_rpc(filters: dict, sender: str | None, recipient: str | None, limit: int, rpc_url: str | None) -> None:
    try:
        http_client = AITBCHTTPClient(base_url=_resolve_transaction_rpc_url(rpc_url), timeout=30)
        transactions = http_client.get_json("/rpc/transactions", params={**filters, "limit": limit})
        if not isinstance(transactions, list):
            abort(
                click.get_current_context(silent=True),
                "Unexpected response shape from /rpc/transactions (expected a JSON array).",
            )
            return

        # A node that has not been restarted since sender/recipient landed
        # silently ignores those params and returns either-side rows —
        # verify locally rather than present a wrong answer confidently.
        if sender or recipient:
            kept = [
                r
                for r in transactions
                if (not sender or _row_matches(r, "sender", sender))
                and (not recipient or _row_matches(r, "recipient", recipient))
            ]
            dropped = len(transactions) - len(kept)
            if dropped:
                warning(
                    f"node returned {dropped} rows that did not match the filter "
                    "(rpc not yet restarted with the sender/recipient filter?); "
                    "results were filtered locally, and `limit` applied before "
                    "the filter, so the list may be incomplete"
                )
            transactions = kept
        transactions = [_normalize_search_row(r) for r in transactions]
        names = "+".join(filters)
        success(f"Found {len(transactions)} transactions matching {names} (via RPC)", err=True)
        click.echo(json.dumps(transactions, indent=2))
    except CLIError:
        raise
    except NetworkError as e:
        abort(None, f"RPC unavailable: {e}")
    except Exception as e:  # noqa: BLE001 - CLI boundary — unexpected failure reports cleanly
        abort(None, f"Error searching transactions: {e}")
