"""
Island management commands for federated mesh.
"""

import json
import os
import shutil
import socket
import stat
import uuid
from datetime import datetime, UTC

import click

try:
    from aitbc_cli.utils import error, info, output, success, warning
except ImportError:
    from aitbc_cli.utils import error, info, output, success, warning

try:
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError
except ImportError:
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

from aitbc_cli.utils.error_handling import CLIError
from aitbc.config.hub import normalize_hub_base


def _resolve_join_rpc_url(hub: str, rpc_url: str | None) -> str:
    """Return the RPC base URL to use for the island join request."""
    if rpc_url:
        return rpc_url.rstrip("/")

    from aitbc_cli.config import get_config

    config = get_config()
    if config.blockchain_rpc_url:
        return config.blockchain_rpc_url.rstrip("/")

    try:
        hub_ip = socket.gethostbyname(hub)
    except socket.gaierror:
        hub_ip = ""

    if hub_ip in ("127.0.0.1", "::1", "localhost"):
        return "http://127.0.0.1:8202"

    # The hub's node RPC sits behind its public /rpc mount; the raw :8202 port
    # is not forwarded at the edge.
    return normalize_hub_base(hub) or hub


def _format_joined_at(value) -> str:
    """Render an island ``joined_at`` value as an ISO timestamp.

    The node RPC returns a float epoch (``IslandMembership.joined_at``);
    ISO strings pass through unchanged and anything unparseable is shown
    verbatim rather than crashing the table.
    """
    if value is None or value == "":
        return "N/A"
    try:
        epoch = float(value)
    except (TypeError, ValueError):
        return str(value)
    try:
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return str(value)


def create_island_command(ctx, island_id, island_name, chain_id, node_url="http://127.0.0.1:8202"):
    """Create a new island on the local node.

    The node's island manager has no separate "create" endpoint — island
    registration goes through ``POST /rpc/islands/join`` with ``is_hub``
    set, which records the node as the island's hub member. Without this
    RPC call the command only printed identifiers and ``list-islands``
    never showed the island (#2203).
    """
    try:
        if not island_id:
            island_id = str(uuid.uuid4())

        if not chain_id:
            chain_id = f"ait-{island_id[:8]}"

        rpc_base = node_url.rstrip("/")
        click.echo(f"Registering island on node {node_url}...")

        response = _join_island_rpc(ctx, rpc_base, island_id, island_name, chain_id, True, role="hub")

        # Prefer RPC endpoint from response; fall back to the URL we used.
        credentials = dict(response["credentials"])
        if not credentials.get("rpc_endpoint"):
            credentials["rpc_endpoint"] = f"{rpc_base}/rpc" if not rpc_base.endswith("/rpc") else rpc_base

        credentials_path = _store_island_credentials(response, credentials)

        fmt = ctx.obj.get("output_format", "table") if ctx and ctx.obj else "table"
        island_info = {
            "Island ID": response.get("island_id", island_id),
            "Island Name": response.get("island_name", island_name),
            "Chain ID": response.get("island_chain_id", chain_id),
            "Status": response.get("status", "created"),
            "Is Hub": "Yes",
            "Credentials Stored": credentials_path,
        }
        output(island_info, fmt, title=f"Created Island: {island_name}")

        members = response.get("members", [])
        if members:
            output(members, fmt, title="Island Members")

        success(f"Island {island_name} ({island_id}) created and registered on {node_url}")

    except (CLIError, click.Abort):
        raise
    except NetworkError as e:
        error(f"Cannot reach node at {node_url}: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error creating island: {str(e)}")
        raise click.Abort() from e


def _load_validator_public_key() -> str:
    """Read the first validator public key from the keystore."""
    keystore_path = "/var/lib/aitbc/keystore/validator_keys.json"
    public_key_pem = None

    if os.path.exists(keystore_path):
        with open(keystore_path) as f:
            keys = json.load(f)
            # Get first key's public key
            for _key_id, key_data in keys.items():
                public_key_pem = key_data.get("public_key_pem")
                break
    else:
        error(f"Keystore not found at {keystore_path}")
        raise click.Abort()

    if not public_key_pem:
        error("No public key found in keystore")
        raise click.Abort()
    return str(public_key_pem)


def _join_island_rpc(ctx, rpc_base: str, island_id, island_name, chain_id, is_hub, *, role: str = "compute-provider") -> dict:
    """POST /islands/join and return a validated success response."""
    from aitbc_cli.config import get_config
    from aitbc_cli.utils.chain_id import resolve_chain_id

    config = get_config()
    client = AITBCHTTPClient(base_url=rpc_base, timeout=10, api_key=config.blockchain_rpc_api_key)

    payload_chain_id = chain_id or resolve_chain_id(ctx, rpc_base)
    response = client.post(
        "/islands/join" if rpc_base.endswith("/rpc") else "/rpc/islands/join",
        json={
            "island_id": island_id,
            "island_name": island_name,
            "chain_id": payload_chain_id,
            "is_hub": is_hub,
            "role": role,
        },
    )

    if not isinstance(response, dict) or not response.get("success"):
        status = response.get("status", "unknown") if isinstance(response, dict) else "unknown"
        message = response.get("message", "No response from hub") if isinstance(response, dict) else str(response)
        error(f"Failed to join island - status={status}: {message}")
        raise click.Abort()

    # Reject malformed join responses before persisting credentials —
    # a response with null island_id/credentials would otherwise clobber
    # the stored credential file (#2096).
    returned_island_id = response.get("island_id")
    returned_credentials = response.get("credentials")
    if not returned_island_id or not isinstance(returned_credentials, dict) or not returned_credentials:
        error(f"Join response missing island_id/credentials — refusing to store: {response}")
        raise click.Abort()
    return response


def _store_island_credentials(response: dict, credentials: dict) -> str:
    """Persist island credentials 0o600; returns the credentials path."""
    credentials_path = "/var/lib/aitbc/island_credentials.json"
    credentials_data = {
        "island_id": response.get("island_id"),
        "island_name": response.get("island_name"),
        "island_chain_id": response.get("island_chain_id"),
        "credentials": credentials,
        "joined_at": datetime.now().isoformat(),
    }

    # Island credentials carry API secrets — create 0o600, no umask window.
    fd = os.open(credentials_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(credentials_data, f, indent=2)

    # Ensure the runtime user can read its own island credentials.
    try:
        shutil.chown(credentials_path, user="aitbc", group="aitbc")
    except (LookupError, OSError) as e:
        warning(f"Could not chown {credentials_path} to aitbc:aitbc: {e}")
    try:
        os.chmod(credentials_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        warning(f"Could not chmod {credentials_path}: {e}")
    return credentials_path


def _print_join_results(ctx, response: dict, island_name, credentials: dict, credentials_path: str) -> None:
    """Display join info, member list, and stored credentials."""
    join_info = {
        "Island ID": response.get("island_id"),
        "Island Name": response.get("island_name"),
        "Chain ID": response.get("island_chain_id"),
        "Member Count": len(response.get("members", [])),
        "Credentials Stored": credentials_path,
    }

    output(join_info, ctx.obj.get("output_format", "table"), title=f"Joined Island: {island_name}")

    # Display member list
    members = response.get("members", [])
    if members:
        output(members, ctx.obj.get("output_format", "table"), title="Island Members")

    # Display credentials
    if credentials:
        output(credentials, ctx.obj.get("output_format", "table"), title="Blockchain Credentials")

    success(f"Successfully joined island {island_name}")


def join_island_command(ctx, island_id, island_name, chain_id, hub, is_hub, *, rpc_url: str | None = None):
    """Join an existing island via the hub's HTTP RPC endpoint."""
    try:
        _load_validator_public_key()

        # Resolve hub domain and build the RPC URL.
        rpc_base = _resolve_join_rpc_url(hub, rpc_url)
        click.echo(f"Connecting to hub {hub} (RPC {rpc_base})...")

        response = _join_island_rpc(ctx, rpc_base, island_id, island_name, chain_id, is_hub)

        # Prefer RPC endpoint from response; fall back to the URL we used.
        credentials = dict(response["credentials"])
        if not credentials.get("rpc_endpoint"):
            credentials["rpc_endpoint"] = f"{rpc_base}/rpc" if not rpc_base.endswith("/rpc") else rpc_base

        credentials_path = _store_island_credentials(response, credentials)
        _print_join_results(ctx, response, island_name, credentials, credentials_path)

        # If registering as hub
        if is_hub:
            click.echo("Registering as hub...")
            click.echo("Run 'aitbc node hub register' to complete hub registration")

    except (CLIError, click.Abort):
        raise
    except NetworkError as e:
        error(f"Network error joining island: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error joining island: {str(e)}")
        raise click.Abort() from e


def leave_island_command(ctx, island_id, node_url="http://127.0.0.1:8202"):
    """Leave an island — calls the node's /rpc/islands/leave."""
    from aitbc_cli.config import get_config
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

    config = get_config()
    client = AITBCHTTPClient(base_url=node_url, timeout=10, api_key=config.blockchain_rpc_api_key)
    try:
        response = client.post(
            "/islands/leave" if node_url.endswith("/rpc") else "/rpc/islands/leave",
            json={"island_id": island_id},
        )
    except NetworkError as e:
        error(f"Cannot reach node at {node_url}: {e}")
        raise click.Abort() from e

    if isinstance(response, dict) and response.get("success"):
        success(f"Successfully left island {island_id}")
    elif isinstance(response, dict) and (response.get("code") or response.get("status")) == "not_member":
        info(response.get("message", f"Not a member of island {island_id}"))
        output(response, ctx.obj.get("output_format", "table") if ctx and ctx.obj else "table")
    else:
        message = response.get("message", "unknown") if isinstance(response, dict) else str(response)
        error(f"Failed to leave island {island_id}: {message}")
        raise click.Abort()


def list_islands_command(ctx, node_url="http://127.0.0.1:8202"):
    """List all known islands (queries the node's island manager via RPC)"""
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

    from aitbc_cli.config import get_config as _isl_cfg

    _cfg = _isl_cfg()
    client = AITBCHTTPClient(
        base_url=node_url,
        api_key=(ctx.obj or {}).get("api_key") or getattr(_cfg, "blockchain_rpc_api_key", None),
    )
    try:
        result = client.get("/rpc/islands")
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
        raise click.Abort() from e
    finally:
        client.close()

    if isinstance(result, dict) and result.get("detail"):
        error(f"Error from /rpc/islands: {result['detail']}")
        raise click.Abort()

    islands = result.get("islands", []) if isinstance(result, dict) else []
    if not islands:
        output({"message": "No islands found"}, ctx.obj.get("output_format", "table"))
        return

    islands_data = [
        {
            "Island ID": island.get("island_id", "N/A"),
            "Island Name": island.get("island_name", "N/A"),
            "Chain ID": island.get("chain_id", "N/A"),
            "Status": island.get("status", "N/A"),
            "Peer Count": str(island.get("peer_count", 0)),
            "Is Hub": str(island.get("is_hub", False)),
        }
        for island in islands
    ]

    output(islands_data, ctx.obj.get("output_format", "table"), title=f"Known Islands ({len(islands)} total)")


def island_info_command(ctx, island_id, node_url="http://127.0.0.1:8202"):
    """Get island information (queries the node's island manager via RPC)"""
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

    from aitbc_cli.config import get_config as _isl_cfg

    _cfg = _isl_cfg()
    client = AITBCHTTPClient(
        base_url=node_url,
        api_key=(ctx.obj or {}).get("api_key") or getattr(_cfg, "blockchain_rpc_api_key", None),
    )
    try:
        result = client.get(f"/rpc/islands/{island_id}")
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
        raise click.Abort() from e
    finally:
        client.close()

    if isinstance(result, dict) and result.get("detail"):
        error(f"Error from /rpc/islands/{island_id}: {result['detail']}")
        raise click.Abort()

    island_data = {
        "Island ID": result.get("island_id", "N/A"),
        "Island Name": result.get("island_name", "N/A"),
        "Chain ID": result.get("chain_id", "N/A"),
        "Status": result.get("status", "N/A"),
        "Role": result.get("role", "N/A"),
        "Peer Count": str(result.get("peer_count", 0)),
        "Is Hub": str(result.get("is_hub", False)),
        "Joined At": _format_joined_at(result.get("joined_at")),
    }

    output(island_data, ctx.obj.get("output_format", "table"), title=f"Island Information: {island_id}")


def health_command(ctx, node_url="http://127.0.0.1:8202", show_all=False):
    """Show health status of connected islands (status, peer count, activity).

    Queries the node's /islands RPC endpoint and presents health-focused
    information. By default, the default island is omitted (it is always
    active); use --all to include it.
    """
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

    from aitbc_cli.config import get_config as _isl_cfg

    _cfg = _isl_cfg()
    client = AITBCHTTPClient(
        base_url=node_url,
        api_key=(ctx.obj or {}).get("api_key") or getattr(_cfg, "blockchain_rpc_api_key", None),
    )
    try:
        result = client.get("/rpc/islands")
    except NetworkError as e:
        error(f"Cannot connect to node at {node_url}: {e}")
        raise click.Abort() from e
    finally:
        client.close()

    if isinstance(result, dict) and result.get("detail"):
        error(f"Error from /rpc/islands: {result['detail']}")
        raise click.Abort()

    islands = result.get("islands", []) if isinstance(result, dict) else []
    if not islands:
        output({"message": "No islands found"}, ctx.obj.get("output_format", "table"))
        return

    health_rows = [
        {
            "Island ID": island.get("island_id", "N/A"),
            "Chain ID": island.get("chain_id", "N/A"),
            "Status": str(island.get("status", "N/A")).upper(),
            "Peers": str(island.get("peer_count", 0)),
            "Hub": "Yes" if island.get("is_hub") else "No",
            "Joined": _format_joined_at(island.get("joined_at")),
        }
        for island in islands
    ]

    # Summary
    total = len(islands)
    active = sum(1 for i in islands if i.get("status") == "active")
    inactive = sum(1 for i in islands if i.get("status") == "inactive")
    bridging = sum(1 for i in islands if i.get("status") == "bridging")

    output(health_rows, ctx.obj.get("output_format", "table"), title="Island Health")
    click.echo("")
    click.echo(f"Summary: {total} total, {active} active, {inactive} inactive, {bridging} bridging")
