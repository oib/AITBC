"""IPFS commands for AITBC CLI backed by a local Kubo daemon.

When a Kubo daemon is not reachable on `127.0.0.1:5001`, the CLI falls back to
a minimal filesystem shim so the surface still works on a node without a running
daemon. Cross-node retrieval requires the real daemon and the IPFS network.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import click
import requests
from eth_keys.datatypes import PrivateKey
from eth_utils import keccak

from aitbc.crypto.crypto import sign_transaction_hash

from ..config import _resolve_api_key, get_config
from ..utils import DECIMAL, OUTPUT_FORMAT_OPTION, error, info, output, success, warning
from ..utils.chain_id import get_chain_id
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger
from ..utils.output import resolve_output_format
from ..utils.wallet import decrypt_private_key
from ..utils.wallet_paths import wallet_dir
from .transactions import _send_transaction_impl

IPFS_DIR = Path(os.environ.get("AITBC_IPFS_DIR", "/var/lib/aitbc/ipfs"))
IPFS_API = os.environ.get("IPFS_API_URL", "http://127.0.0.1:5001")
TIMEOUT = 120

logger = get_logger(__name__)


def _ensure_ipfs_dir() -> None:
    """Create the IPFS directory on demand; imports must not fail on fresh runners."""
    IPFS_DIR.mkdir(parents=True, exist_ok=True)


def _cid_for(data: bytes) -> str:
    """Deterministic fallback CID for the filesystem shim."""
    digest = hashlib.sha256(data).hexdigest()
    return f"Qm{digest[:44]}"


def _index_path() -> Path:
    return IPFS_DIR / "index.json"


def _load_index() -> list[dict[str, Any]]:
    path = _index_path()
    if not path.exists():
        return []
    try:
        return cast(list, json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(items: list[dict[str, Any]]) -> None:
    _ensure_ipfs_dir()
    _index_path().write_text(json.dumps(items, indent=2))


def _make_cid_path(cid: str) -> Path:
    return IPFS_DIR / cid


def _hub_marketplace_client(timeout: int = 15) -> AITBCHTTPClient:
    """Return an HTTP client for the hub marketplace service (shared with market commands)."""
    config = get_config()
    if config.marketplace_service_url and not config.marketplace_service_url.startswith("http://127.0.0.1"):
        return AITBCHTTPClient(base_url=config.marketplace_service_url, timeout=timeout)
    hub_host = config.hub_discovery_url or "hub.aitbc.bubuit.net"
    if hub_host.startswith(("http://", "https://")):
        hub_url = hub_host.rstrip("/")
    elif "localhost" in hub_host or "127.0.0.1" in hub_host:
        hub_url = f"http://{hub_host}"
    else:
        # Public hubs are exposed over HTTPS unless the env explicitly says http://
        hub_url = f"https://{hub_host}"
    return AITBCHTTPClient(base_url=hub_url, timeout=timeout)


def _daemon_available(ipfs_api: str = IPFS_API) -> bool:
    try:
        requests.post(f"{ipfs_api}/api/v0/id", timeout=2)
        return True
    except requests.RequestException:
        return False


def _api_post(path: str, **kwargs: Any) -> requests.Response:
    ipfs_api = kwargs.pop("ipfs_api", IPFS_API)
    timeout = kwargs.pop("timeout", TIMEOUT)
    return requests.post(f"{ipfs_api}{path}", timeout=timeout, **kwargs)


def _is_cid(value: str) -> bool:
    """Return True if value looks like an IPFS CID (v0 or v1)."""
    value = value.strip()
    if not value:
        return False
    # CIDv0 starts with Qm and is base58 (roughly 46 chars).
    if value.startswith("Qm") and len(value) >= 46:
        return True
    # CIDv1 starts with bafy, bafk, bafz, etc.
    if value.startswith("baf") and len(value) >= 59:
        return True
    return False


def _ipfs_add_file(ipfs_api: str, file_path: Path) -> str | None:
    """Add a file to an IPFS API and return the CID."""
    try:
        with open(file_path, "rb") as f:
            response = requests.post(
                f"{ipfs_api.rstrip('/')}/api/v0/add",
                files={"file": (file_path.name, f)},
                timeout=TIMEOUT,
            )
        response.raise_for_status()
        result = response.json()
        return cast(str | None, result.get("Hash") or result.get("cid"))
    except Exception as e:
        warning(f"IPFS add failed: {e}")
        return None


def _ipfs_pin_cid(ipfs_api: str, cid: str) -> bool:
    """Pin a CID on an IPFS API."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/pin/add",
            params={"arg": cid},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        warning(f"IPFS pin failed: {e}")
        return False


def _ipfs_unpin_cid(ipfs_api: str, cid: str) -> bool:
    """Unpin a CID on an IPFS API."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/pin/rm",
            params={"arg": cid},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        warning(f"IPFS unpin failed: {e}")
        return False


def _ipfs_object_size(ipfs_api: str, cid: str) -> int | None:
    """Return the dag cumulative size in bytes for a CID, or None if unreachable."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/object/stat",
            params={"arg": cid},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        cumulative = data.get("CumulativeSize")
        if cumulative is not None:
            return int(cumulative)
    except Exception:
        pass
    return None


def _ipfs_swarm_connect(ipfs_api: str, multiaddr: str) -> bool:
    """Attempt to connect the local IPFS daemon to a provider multiaddr."""
    try:
        response = requests.post(
            f"{ipfs_api.rstrip('/')}/api/v0/swarm/connect",
            params={"arg": multiaddr},
            timeout=30,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        warning(f"Could not swarm connect to {multiaddr}: {e}")
        return False


@click.group(
    epilog="""Examples:

  aitbc ipfs upload --file /tmp/data.txt

  aitbc ipfs download --cid Qm..."""
)
@click.pass_context
def ipfs(ctx):
    """Upload, download, pin, and rent IPFS content via the Kubo daemon or filesystem fallback."""
    ctx.ensure_object(dict)


@ipfs.command(
    epilog="""Examples:

  aitbc ipfs upload --file /tmp/data.txt

  aitbc ipfs upload --file /tmp/data.txt --name 'my file' --pin"""
)
@click.option("--file", required=True, type=click.Path(exists=True, readable=True), help="File to upload")
@click.option("--pin", is_flag=True, default=True, help="Pin uploaded content")
@click.option("--name", default=None, help="Human-readable name for the upload")
@click.pass_context
def upload(ctx, file: str, pin: bool, name: str | None):
    """Upload a file to IPFS and return its CID."""
    file_path = Path(file)
    data = file_path.read_bytes()
    _ensure_ipfs_dir()

    if _daemon_available():
        try:
            response = _api_post(
                "/api/v0/add",
                params={"pin": "true" if pin else "false", "wrap-with-directory": "false"},
                files={"file": (file_path.name, data)},
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            cid = result.get("Hash") or result.get("cid")
            size = int(result.get("Size", len(data)))
            click.echo(
                json.dumps(
                    {
                        "success": True,
                        "data": {
                            "cid": cid,
                            "size": size,
                            "name": name or file_path.name,
                            "pinned": pin,
                        },
                    }
                )
            )
            return
        except requests.RequestException as e:
            click.echo(
                json.dumps({"success": False, "warning": f"Kubo upload failed: {e}; falling back to filesystem"}), err=True
            )

    # Filesystem fallback
    cid = _cid_for(data)
    cid_path = _make_cid_path(cid)
    cid_path.write_bytes(data)

    items = _load_index()
    items = [i for i in items if i.get("cid") != cid]
    items.append(
        {
            "cid": cid,
            "name": name or file_path.name,
            "size": len(data),
            "pinned": pin,
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
    )
    _save_index(items)

    click.echo(json.dumps({"success": True, "data": {"cid": cid, "size": len(data), "name": name or file_path.name}}))


@ipfs.command(
    epilog="""Examples:

  aitbc ipfs download --cid Qm...

  aitbc ipfs download --cid Qm... --output /tmp/data.txt --wait"""
)
@click.option("--cid", "cid", required=False, help="The Cid.")
@click.option("--output", type=click.Path(), help="Write retrieved content to this path")
@click.option("--wait", is_flag=True, default=False, help="Wait for the CID to become available on the network")
@click.option("--access-key", help="Deprecated; use `aitbc market download` instead")
@click.option("--access-secret", help="Deprecated; use `aitbc market download` instead")
@click.option("--rental-id", help="Deprecated; use `aitbc market download` instead")
@click.pass_context
def download(
    ctx,
    cid: str | None,
    output: str | None,
    wait: bool,
    access_key: str | None,
    access_secret: str | None,
    rental_id: str | None,
):
    """Download content by CID and optionally write it to a file."""
    if rental_id or access_key or access_secret:
        warning("Paid IPFS retrieval has moved to `aitbc market download`.")

    if not cid:
        error("Provide a CID, --rental-id, or --access-key/--access-secret")
        raise click.Abort()

    # Prefer the daemon that was used for the rental.
    ipfs_api = IPFS_API
    if rental_id or access_key:
        ipfs_api = (rental or token or {}).get("ipfs_api") or os.environ.get("IPFS_API_URL") or "http://127.0.0.1:5001"

    if _daemon_available(ipfs_api):
        try:
            for _attempt in range(1, 60 if wait else 1):
                response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30, ipfs_api=ipfs_api)
                if response.status_code == 200:
                    break
                if not wait:
                    response.raise_for_status()
                    break
                import time

                time.sleep(2)
            else:
                response = _api_post("/api/v0/cat", params={"arg": cid}, timeout=30, ipfs_api=ipfs_api)
            response.raise_for_status()
            data = response.content
        except requests.RequestException:
            data = None
    else:
        data = None

    if data is None:
        cid_path = _make_cid_path(cid)
        if not cid_path.exists():
            click.echo(json.dumps({"success": False, "error": f"CID not found: {cid}"}))
            raise click.Abort()
        data = cid_path.read_bytes()

    if output:
        out_path = Path(output)
        out_path.write_bytes(data)
        file_path = str(out_path)
    else:
        with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp:
            tmp.write(data)
            file_path = tmp.name

    click.echo(json.dumps({"success": True, "data": {"cid": cid, "file_path": file_path, "size": len(data)}}))


@ipfs.command(
    epilog="""Examples:

  aitbc ipfs pin --cid Qm...

  aitbc ipfs pin --cid Qm... --output json"""
)
@click.option("--cid", "cid", required=True, help="The Cid.")
@click.pass_context
def pin(ctx, cid: str):
    """Pin content by CID on the local Kubo daemon or filesystem index."""
    if _daemon_available():
        try:
            response = _api_post("/api/v0/pin/add", params={"arg": cid})
            response.raise_for_status()
            click.echo(json.dumps({"success": True, "data": {"pinned": True, "cid": cid}}))
            return
        except requests.RequestException as e:
            click.echo(json.dumps({"success": False, "warning": f"Kubo pin failed: {e}; using filesystem index"}), err=True)

    _ensure_ipfs_dir()
    cid_path = _make_cid_path(cid)
    if not cid_path.exists():
        result = {"success": False, "error": f"CID not found: {cid}"}
        click.echo(json.dumps(result))
        raise click.Abort()

    items = _load_index()
    found = False
    for item in items:
        if item.get("cid") == cid:
            item["pinned"] = True
            found = True
    if not found:
        items.append(
            {
                "cid": cid,
                "name": cid,
                "size": cid_path.stat().st_size,
                "pinned": True,
                "uploaded_at": datetime.now(UTC).isoformat(),
            }
        )
    _save_index(items)

    click.echo(json.dumps({"success": True, "data": {"pinned": True, "cid": cid}}))


@ipfs.command(
    name="list",
    epilog="""Examples:

  aitbc ipfs list

  aitbc ipfs list --output json""",
)
@click.pass_context
def list_items(ctx):
    """List uploaded and pinned IPFS items."""
    if _daemon_available():
        try:
            response = _api_post("/api/v0/pin/ls", params={"stream": "true"}, stream=True)
            response.raise_for_status()
            items = []
            for line in response.iter_lines():
                if line:
                    try:
                        obj = json.loads(line.decode())
                        items.append(
                            {
                                "cid": obj.get("Cid") or obj.get("cid"),
                                "type": obj.get("Type") or obj.get("type"),
                            }
                        )
                    except json.JSONDecodeError:
                        continue
            click.echo(json.dumps({"success": True, "data": {"items": items}}))
            return
        except requests.RequestException as e:
            click.echo(
                json.dumps({"success": False, "warning": f"Kubo pin list failed: {e}; using filesystem index"}), err=True
            )

    items = _load_index()
    click.echo(json.dumps({"success": True, "data": {"items": items}}))


# ---------------------------------------------------------------------------
# Paid IPFS hosting commands have moved to `aitbc market host`.
# Free/local IPFS helpers remain here for upload, pin, list, and download.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    ipfs()
# ---------------------------------------------------------------------------
# Island IPFS subscription and swarm-key commands
# ---------------------------------------------------------------------------


def _resolve_wallet_password(password: str | None, password_file: str | None, wallet_name: str) -> str:
    """Resolve a wallet password from flags, env, unencrypted wallet, or TTY prompt."""
    if password is not None:
        return password
    if password_file:
        with open(password_file) as f:
            return f.read().strip()
    if "AITBC_WALLET_PASSWORD" in os.environ:
        return os.environ["AITBC_WALLET_PASSWORD"]

    keystore_dir = wallet_dir()
    keystore = keystore_dir / f"{wallet_name}.json"
    if keystore.exists():
        data = json.loads(keystore.read_text())
        if not data.get("encrypted") and not data.get("encrypted_private_key"):
            return ""

    if not sys.stdin.isatty():
        abort(None, "No TTY available for password prompt. Use --password, --password-file, or set AITBC_WALLET_PASSWORD.")
        return ""  # unreachable; abort always raises

    import getpass

    try:
        return getpass.getpass("Enter wallet password: ")
    except Exception as e:
        abort(None, f"Password prompt failed: {e}", from_exception=e)
        return ""  # unreachable; abort always raises


def _load_wallet_key(wallet_name: str, password: str) -> tuple[str, PrivateKey]:
    """Load a file wallet and return (address, private_key)."""
    keystore = wallet_dir() / f"{wallet_name}.json"
    if not keystore.exists():
        raise click.BadParameter(f"Wallet '{wallet_name}' not found at {keystore}")

    data = json.loads(keystore.read_text())
    address = data.get("address")
    if not address:
        raise click.BadParameter(f"Wallet '{wallet_name}' has no address")

    if data.get("encrypted") or data.get("encrypted_private_key"):
        if not password:
            raise click.BadParameter(f"Wallet '{wallet_name}' is encrypted; provide --password")
        private_key_hex = decrypt_private_key(keystore, password)
    else:
        private_key_hex = data.get("private_key", "")

    if not private_key_hex:
        raise click.BadParameter(f"Wallet '{wallet_name}' has no private key")
    if isinstance(private_key_hex, str) and private_key_hex.startswith("0x"):
        private_key_hex = private_key_hex[2:]

    try:
        private_key = PrivateKey(bytes.fromhex(private_key_hex))
    except ValueError as e:
        raise click.BadParameter(f"Invalid private key in wallet '{wallet_name}': {e}") from e

    return address, private_key


def _default_rpc_url(rpc_url: str | None) -> str:
    if rpc_url:
        return rpc_url
    config = get_config()
    return getattr(config, "blockchain_rpc_url", "http://127.0.0.1:8202") or "http://127.0.0.1:8202"


def _default_coordinator_url(coordinator_url: str | None) -> str:
    if coordinator_url:
        return coordinator_url
    config = get_config()
    return getattr(config, "coordinator_api_url", "http://127.0.0.1:8203") or "http://127.0.0.1:8203"


@click.group(name="island")
@click.pass_context
def island(ctx):
    """Private island IPFS subscription and swarm-key management."""
    ctx.ensure_object(dict)


@island.command()
@click.option("--wallet", "wallet_name", required=True, help="Wallet name to pay from")
@click.option("--to", "to_address", required=True, help="Island treasury / recipient address")
@click.option("--island-id", required=True, help="Island identifier (e.g. ait-hub.aitbc.bubuit.net-island)")
@click.option("--duration", type=int, default=1000, help="Subscription duration in blocks (default 1000)")
@click.option("--quota", type=int, default=1073741824, help="Quota in bytes (default 1 GiB)")
@click.option("--amount", type=DECIMAL, required=True, help="Payment amount in AIT")
@click.option("--fee", type=DECIMAL, default="0.001", help="Transaction fee in AIT")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--rpc-url", help="Blockchain RPC URL")
@click.pass_context
def subscribe(
    ctx,
    wallet_name: str,
    to_address: str,
    island_id: str,
    duration: int,
    quota: int,
    amount: Decimal,
    fee: Decimal,
    password: str | None,
    password_file: str | None,
    rpc_url: str | None,
):
    """Subscribe to a private island IPFS network.

    Submits an IPFS_SUBSCRIPTION transaction that creates or extends an
    on-chain subscription record. The member can then request the swarm key
    with `aitbc-cli ipfs island swarm-key`.
    """
    resolved_password = _resolve_wallet_password(password, password_file, wallet_name)
    resolved_rpc_url = _default_rpc_url(rpc_url)
    payload = {
        "island_id": island_id,
        "duration_blocks": duration,
        "quota_bytes": quota,
    }

    tx_hash = _send_transaction_impl(
        from_wallet=wallet_name,
        to_address=to_address,
        amount=amount,
        fee=fee,
        password=resolved_password,
        rpc_url=resolved_rpc_url,
        tx_type="IPFS_SUBSCRIPTION",
        payload=payload,
    )
    if tx_hash:
        success(f"Island IPFS subscription transaction sent: {tx_hash}")
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "tx_hash": tx_hash,
                        "island_id": island_id,
                        "duration_blocks": duration,
                        "quota_bytes": quota,
                    },
                },
                indent=2,
            )
        )
    else:
        error("Failed to send island IPFS subscription transaction")


@island.command(name="swarm-key")
@click.option("--wallet", "wallet_name", required=True, help="Wallet name whose address is subscribed")
@click.option("--island-id", required=True, help="Island identifier")
@click.option("--coordinator-url", help="Coordinator API base URL")
@click.option("--chain-id", help="Blockchain chain ID (auto-detected from RPC if omitted)")
@click.option("--rpc-url", help="Blockchain RPC URL for chain ID auto-detection")
@click.option("--api-key", help="Coordinator API key (default from config / AITBC_API_KEY / MINER_API_KEYS)")
@click.option("--password", help="Wallet password")
@click.option("--password-file", help="File containing wallet password")
@click.option("--output", type=click.Path(), help="Optional path to write the swarm.key")
@click.option("--bootstrap", is_flag=True, help="Also print a bootstrap multiaddr for the hub island daemon")
@click.pass_context
def swarm_key(
    ctx,
    wallet_name: str,
    island_id: str,
    coordinator_url: str | None,
    chain_id: str | None,
    rpc_url: str | None,
    api_key: str | None,
    password: str | None,
    password_file: str | None,
    output: str | None,
    bootstrap: bool,
):
    """Request the swarm key for a subscribed island IPFS network.

    Signs an authorization challenge with the wallet key and calls the
    coordinator swarm-key endpoint. The coordinator checks the on-chain
    subscription before returning the key.
    """
    resolved_password = _resolve_wallet_password(password, password_file, wallet_name)
    member_address, private_key = _load_wallet_key(wallet_name, resolved_password)

    resolved_rpc_url = _default_rpc_url(rpc_url)
    if not chain_id:
        chain_id = get_chain_id(resolved_rpc_url, override=None, timeout=5)
        if not chain_id:
            error("Could not auto-detect chain_id; pass --chain-id explicitly")
            return

    resolved_coordinator_url = _default_coordinator_url(coordinator_url)
    resolved_api_key = api_key
    if not resolved_api_key:
        resolved_api_key = getattr(get_config(), "api_key", None)
    if not resolved_api_key:
        resolved_api_key = _resolve_api_key({})
    if not resolved_api_key:
        error("No API key available; set AITBC_API_KEY, add api_key to config, or pass --api-key")
        return

    nonce = f"{datetime.now(UTC).isoformat()}:{secrets.token_hex(8)}"
    challenge = f"{island_id}:{member_address}:{nonce}".encode()
    msg_hash = "0x" + keccak(challenge).hex()
    private_key_hex = private_key.to_hex()
    signature = sign_transaction_hash(msg_hash, private_key_hex)

    request = {
        "chain_id": chain_id,
        "island_id": island_id,
        "member_address": member_address,
        "nonce": nonce,
        "signature": signature,
    }

    base = resolved_coordinator_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/v1/ipfs/island/swarm-key"
    try:
        response = requests.post(
            url,
            json=request,
            headers={"X-Api-Key": resolved_api_key},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        error(f"Failed to request swarm key: {e}")
        if isinstance(e, requests.HTTPError) and e.response is not None:
            click.echo(e.response.text, err=True)
        return

    data = response.json()
    key = data.get("swarm_key", "")
    if output:
        out_path = Path(output)
        out_path.write_text(key)
        out_path.chmod(0o600)
        success(f"Swarm key written to {output}")

    result_data: dict[str, Any] = {
        "island_id": data.get("island_id"),
        "chain_id": data.get("chain_id"),
        "member_address": data.get("member_address"),
        "swarm_key": key,
    }
    if bootstrap and data.get("hub_multiaddr_template"):
        template = data.get("hub_multiaddr_template", "")
        # The template contains <hub_peer_id>; keep it as a hint if peer id not known.
        if "<hub_peer_id>" in template:
            result_data["bootstrap_hint"] = template
        else:
            result_data["bootstrap"] = template

    click.echo(json.dumps({"success": True, "data": result_data}, indent=2))


ipfs.add_command(island, name="island")
