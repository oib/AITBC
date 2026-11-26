"""Shared helpers for the ``aitbc bridge`` command package.

Extracted verbatim from the former ``commands/bridge.py`` module; the
package ``__init__`` re-exports the names tests and callers patch or call
directly (``_get_bridge_client``, ``_resolve_node_chain_id``,
``_canonical_hash``, ``_resolve_bridge_repo_root``).
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
import httpx

from aitbc.bridge import BridgeClient, BridgeConfig
from aitbc.exceptions import AITBCError
from eth_keys.exceptions import BadSignature
from eth_utils.exceptions import ValidationError as EthValidationError

from ...utils import info, warning
from ...utils.error_handling import CLIError, abort

# Expected failure surface for the bridge command handlers: filesystem/JSON,
# subprocess, data-shape, runtime, httpx transport/HTTP errors and both error
# hierarchies, eth-keys/eth-utils signing errors, and RuntimeError for
# generic runtime failures; abort() raises CLIError (already listed),
# preserving the previous re-abort behaviour. BaseExceptions still
# propagate (#1864).
_OPS_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    subprocess.SubprocessError,
    CLIError,
    AITBCError,
    httpx.HTTPError,
    BadSignature,
    EthValidationError,
)


def _canonical_hash(data: dict[str, Any]) -> bytes:
    """keccak256 of canonical JSON encoding (matches verify_request_signature)."""
    from eth_utils import keccak

    message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return keccak(message)


def _sign_hash(private_key_hex: str, msg_hash: bytes) -> str:
    """Sign a keccak message hash with a private key, returning a hex signature."""
    from eth_keys import keys

    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    sig = pk.sign_msg_hash(msg_hash)
    return sig.to_hex()


def _sign_dict(private_key_hex: str, data: dict[str, Any]) -> str:
    """Sign a canonical dict and return the hex signature."""
    return _sign_hash(private_key_hex, _canonical_hash(data))


def _derive_address(private_key_hex: str) -> str:
    """Derive the Ethereum address from a private key hex."""
    from eth_keys import keys

    pk = keys.PrivateKey(bytes.fromhex(private_key_hex.removeprefix("0x")))
    return str(pk.public_key.to_checksum_address())


def _sign_header(private_key_hex: str, header_fields: dict[str, Any]) -> str:
    """Sign a block header with the canonical verification message."""
    sign_fields = {
        "chain_id": header_fields["chain_id"],
        "height": header_fields["height"],
        "hash": header_fields["hash"],
        "parent_hash": header_fields.get("parent_hash") or "0x" + "00" * 32,
        "proposer": header_fields["proposer"],
        "state_root": header_fields["state_root"],
        "bridge_state_root": header_fields.get("bridge_state_root") or "",
    }
    return _sign_dict(private_key_hex, sign_fields)


async def _fetch_block_header(rpc_url: str, height: int | None, chain_id: str | None) -> dict[str, Any]:
    """Fetch a block header from the source RPC.

    If height is None, the current head height is resolved first.
    If chain_id is None, the source node's default chain is used.
    Returns only the header fields (no transactions).
    """
    async with httpx.AsyncClient(base_url=rpc_url, timeout=30.0) as client:
        if height is None:
            params = {}
            if chain_id:
                params["chain_id"] = chain_id
            resp = await client.get("/height", params=params)
            resp.raise_for_status()
            height = resp.json().get("height", 0)

        params = {}
        if chain_id:
            params["chain_id"] = chain_id
        resp = await client.get(f"/blocks/{height}", params=params)
        resp.raise_for_status()
        block = resp.json()

    return {
        "chain_id": block["chain_id"],
        "height": block["height"],
        "hash": block["hash"],
        "parent_hash": block.get("parent_hash") or "0x" + "00" * 32,
        "proposer": block["proposer"],
        "state_root": block["state_root"],
        "bridge_state_root": block.get("bridge_state_root", ""),
        "signature": block.get("signature", ""),
    }


_EVENT_BRIDGE_URL = os.getenv("EVENT_BRIDGE_URL", "http://127.0.0.1:8205")
_SERVICE_NAME = "aitbc-blockchain-event-bridge"


def _event_bridge_status() -> dict[str, str]:
    """Read the event bridge service status over HTTP."""
    try:
        resp = httpx.get(f"{_EVENT_BRIDGE_URL}/", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        return {"status": data.get("status", "unknown"), "bridge_status": "active"}
    except _OPS_ERRORS as e:
        return {"status": f"unreachable ({e})", "bridge_status": "inactive"}


def _systemctl(action: str) -> tuple[bool, str]:
    """Run systemctl action on the event bridge service."""
    try:
        result = subprocess.run(
            ["systemctl", action, _SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except _OPS_ERRORS as e:
        return False, str(e)


def _format_422_item(item: object) -> str:
    """Render one FastAPI 422 detail item, naming the offending field.

    Items carry ``loc=["body","signature",…]`` — prefix the leaf field so
    "String should have at least 1 character" isn't an opaque generic
    error (#2445).
    """
    if not isinstance(item, dict):
        return str(item)
    msg = str(item.get("msg") or item)
    loc = item.get("loc")
    if isinstance(loc, list) and loc:
        field = str(loc[-1])
        if field and field != "body":
            return f"{field}: {msg}"
    return msg


def _response_error_detail(exc: BaseException) -> str | None:
    """Best-effort server error detail from an httpx response on ``exc``.

    ``BridgeClient`` lets ``httpx.HTTPStatusError`` propagate; its ``str()``
    is only the status line, while the node's JSON body (``detail`` —
    string or FastAPI 422 list — or ``message``/``error``) carries the
    actual validation failure (#2214).
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    try:
        body = response.json()
    except (AttributeError, TypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if detail is None:
        detail = body.get("message") or body.get("error")
    if isinstance(detail, list):
        return "; ".join(part for part in (_format_422_item(item) for item in detail) if part) or None
    if isinstance(detail, str) and detail:
        return detail
    return None


def _abort_ops(ctx: click.Context, prefix: str, exc: Exception) -> None:
    """Abort with ``prefix: <error>`` plus the server's detail when one exists."""
    detail = _response_error_detail(exc)
    suffix = f" — server: {detail}" if detail else ""
    # httpx transport errors (ReadTimeout, ConnectError, …) stringify to "" —
    # name the class so the abort isn't a bare "prefix: " tail (#2994).
    exc_text = str(exc) or type(exc).__name__
    abort(ctx, f"{prefix}: {exc_text}{suffix}", from_exception=exc)


def _get_bridge_client(rpc_url: str) -> BridgeClient:
    """Create a BridgeClient pointing at the given blockchain RPC URL."""
    return BridgeClient(BridgeConfig(rpc_url=rpc_url))


def _load_private_key(wallet_name: str, password: str = "") -> str:
    """Load a wallet's private key (plaintext or encrypted)."""
    from ...utils.wallet_paths import find_wallet_file, is_service_wallet_path

    wallet_path = find_wallet_file(wallet_name)
    if wallet_path is None:
        raise click.ClickException(f"Wallet not found: {wallet_name}")
    if is_service_wallet_path(wallet_path):
        info(f"Using wallet file: {wallet_path}")
    with open(wallet_path) as f:
        wallet = json.load(f)
    private_key = wallet.get("private_key")
    if isinstance(private_key, dict):
        from ...utils.wallet import decrypt_private_key

        if not password:
            raise click.ClickException("Wallet is encrypted; --wallet-password is required")
        return decrypt_private_key(wallet_path, password)
    if not isinstance(private_key, str) or not private_key:
        raise click.ClickException("Wallet does not contain a usable private_key")
    return private_key


# Private keys must never ride argv — `ps` exposes them to every local
# user (#2544). Every bridge key option resolves in this order:
#   --<name>-key-file > env var > hidden prompt (required keys only) >
#   the deprecated --<name> argv option (still accepted, warns).
BRIDGE_PRIVATE_KEY_ENV = "AITBC_BRIDGE_PRIVATE_KEY"
BRIDGE_PRIVATE_KEYS_ENV = "AITBC_BRIDGE_PRIVATE_KEYS"
BRIDGE_ADMIN_KEY_ENV = "AITBC_BRIDGE_ADMIN_PRIVATE_KEY"
BRIDGE_CONFIRMER_KEY_ENV = "AITBC_BRIDGE_CONFIRMER_PRIVATE_KEY"


def _read_bridge_key_file(path: str) -> str:
    """Raw key material from a file; warns when the mode is wider than 0600."""
    key_path = Path(path)
    raw = key_path.read_text().strip()
    if not raw:
        raise click.ClickException(f"private key file {path} is empty")
    mode = key_path.stat().st_mode & 0o777
    if mode & 0o077:
        warning(f"private key file {path} is group/other-accessible (mode {mode:o}); chmod 600 it")
    return raw


def _warn_argv_key(option: str, env_name: str) -> None:
    warning(
        f"--{option} exposes the private key in the process list; "
        f"prefer --{option}-file, ${env_name}, or the interactive prompt"
    )


def _resolve_bridge_key(
    *, argv_value: str | None, key_file: str | None, env_name: str, required: bool, option: str
) -> str | None:
    """Resolve one bridge private key without argv when possible.

    ``option`` is the argv flag's long name so the deprecation warning can
    name both forms. Returns None only for an optional key with no source;
    a required key with no source is read from a hidden prompt.
    """
    if argv_value:
        _warn_argv_key(option, env_name)
    if key_file:
        return _read_bridge_key_file(key_file)
    env_value = (os.environ.get(env_name) or "").strip()
    if env_value:
        return env_value
    if argv_value:
        return argv_value
    if required:
        return str(click.prompt(f"{option} private key", hide_input=True))
    return None


def _resolve_bridge_keys(
    *, argv_values: tuple[str, ...], key_files: tuple[str, ...], env_name: str, required: bool, option: str
) -> list[str]:
    """Multi-key sibling of :func:`_resolve_bridge_key` (sign-proof multi-sig).

    A key file holds one key; the env var and the prompt take a
    comma-separated list whose first entry becomes the proposer signature.
    """
    if argv_values:
        _warn_argv_key(option, env_name)
    if key_files:
        return [_read_bridge_key_file(f) for f in key_files]
    env_value = (os.environ.get(env_name) or "").strip()
    if env_value:
        return [k.strip() for k in env_value.split(",") if k.strip()]
    if argv_values:
        return list(argv_values)
    if required:
        raw = str(click.prompt(f"{option} private keys (comma-separated)", hide_input=True))
        return [k.strip() for k in raw.split(",") if k.strip()]
    return []


def _resolve_node_chain_id(rpc_url: str) -> str:
    """Resolve the node's own chain ID via the public ``GET /rpc/proposer``.

    The /bridge/lock route verifies signatures against ``get_chain_id(None)``
    = the node's configured ``settings.chain_id`` when the body omits
    ``source_chain``, so the wallet path must sign — and send — that same
    resolved value rather than an empty string.
    """
    try:
        resp = httpx.get(f"{rpc_url.rstrip('/')}/proposer", timeout=5.0)
        resp.raise_for_status()
        chain_id = resp.json().get("chain_id")
    except _OPS_ERRORS as e:
        raise click.ClickException(
            f"Could not resolve the node's chain ID from {rpc_url} ({e}); pass --source-chain explicitly"
        ) from e
    if not isinstance(chain_id, str) or not chain_id:
        raise click.ClickException(f"Node at {rpc_url} reported an empty chain ID; pass --source-chain explicitly")
    return chain_id


def _resolve_bridge_repo_root(repo_root: str | None) -> Path:
    """Locate the AITBC checkout that owns apps/bridge-monitor.

    Order: explicit --repo-root, AITBC_REPO_ROOT, ancestors of the cwd
    (running from inside a checkout), the interpreter-derived path, then
    the conventional /opt/aitbc deploy location.
    """
    candidates: list[Path] = []
    if repo_root:
        candidates.append(Path(repo_root))
    if os.getenv("AITBC_REPO_ROOT"):
        candidates.append(Path(os.environ["AITBC_REPO_ROOT"]))
    for parent in Path.cwd().resolve().parents:
        candidates.append(parent)
    candidates.append(Path(sys.executable).resolve().parents[2])
    candidates.append(Path("/opt/aitbc"))
    for cand in candidates:
        if (cand / "apps" / "bridge-monitor" / "src" / "bridge_monitor" / "admin.py").exists():
            return cand
    return candidates[0] if repo_root else Path(sys.executable).resolve().parents[2]
