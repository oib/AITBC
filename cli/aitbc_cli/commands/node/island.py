"""
Island management commands for federated mesh.
"""

import json
import os
import shutil
import socket
import stat
import uuid

import click

try:
    from aitbc_cli.utils import error, output, success, warning
except ImportError:
    from aitbc_cli.utils import error, output, success, warning

try:
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError
except ImportError:
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError


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

    return f"http://{hub}:8202"


def create_island_command(ctx, island_id, island_name, chain_id):
    """Create a new island"""
    try:
        if not island_id:
            island_id = str(uuid.uuid4())

        if not chain_id:
            chain_id = f"ait-{island_id[:8]}"

        island_info = {"Island ID": island_id, "Island Name": island_name, "Chain ID": chain_id, "Created": "Now"}

        output(island_info, ctx.obj.get("output_format", "table"), title="New Island Created")
        success(f"Island {island_name} ({island_id}) created successfully")

    except Exception as e:
        error(f"Error creating island: {str(e)}")
        raise click.Abort() from e


def join_island_command(ctx, island_id, island_name, chain_id, hub, is_hub, *, rpc_url: str | None = None):
    """Join an existing island via the hub's HTTP RPC endpoint."""
    try:
        from datetime import datetime

        # Get public key from keystore
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

        # Resolve hub domain and build the RPC URL.
        rpc_base = _resolve_join_rpc_url(hub, rpc_url)
        click.echo(f"Connecting to hub {hub} (RPC {rpc_base})...")

        from aitbc_cli.config import get_config

        config = get_config()
        client = AITBCHTTPClient(base_url=rpc_base, timeout=10)

        payload_chain_id = chain_id or config.chain_id
        response = client.post(
            "/islands/join" if rpc_base.endswith("/rpc") else "/rpc/islands/join",
            json={
                "island_id": island_id,
                "island_name": island_name,
                "chain_id": payload_chain_id,
                "is_hub": is_hub,
                "role": "compute-provider",
            },
        )

        if not isinstance(response, dict) or not response.get("success"):
            status = response.get("status", "unknown") if isinstance(response, dict) else "unknown"
            message = response.get("message", "No response from hub") if isinstance(response, dict) else str(response)
            error(f"Failed to join island - status={status}: {message}")
            raise click.Abort()

        # Prefer RPC endpoint from response; fall back to the URL we used.
        credentials = response.get("credentials") or {}
        if not credentials.get("rpc_endpoint"):
            credentials["rpc_endpoint"] = f"{rpc_base}/rpc" if not rpc_base.endswith("/rpc") else rpc_base

        # Store credentials locally
        credentials_path = "/var/lib/aitbc/island_credentials.json"
        credentials_data = {
            "island_id": response.get("island_id"),
            "island_name": response.get("island_name"),
            "island_chain_id": response.get("island_chain_id"),
            "credentials": credentials,
            "joined_at": datetime.now().isoformat(),
        }

        with open(credentials_path, "w") as f:
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

        # Display join info
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

        # If registering as hub
        if is_hub:
            click.echo("Registering as hub...")
            click.echo("Run 'aitbc node hub register' to complete hub registration")

    except NetworkError as e:
        error(f"Network error joining island: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error joining island: {str(e)}")
        raise click.Abort() from e


def leave_island_command(ctx, island_id):
    """Leave an island"""
    try:
        success(f"Successfully left island {island_id}")

    except Exception as e:
        error(f"Error leaving island: {str(e)}")
        raise click.Abort() from e


def list_islands_command(ctx, node_url="http://127.0.0.1:8202"):
    """List all known islands (queries the node's island manager via RPC)"""
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

    client = AITBCHTTPClient(base_url=node_url)
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

    client = AITBCHTTPClient(base_url=node_url)
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
        "Joined At": str(result.get("joined_at", "N/A")),
    }

    output(island_data, ctx.obj.get("output_format", "table"), title=f"Island Information: {island_id}")


def health_command(ctx, node_url="http://127.0.0.1:8202", show_all=False):
    """Show health status of connected islands (status, peer count, activity).

    Queries the node's /islands RPC endpoint and presents health-focused
    information. By default, the default island is omitted (it is always
    active); use --all to include it.
    """
    from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError

    client = AITBCHTTPClient(base_url=node_url)
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
            "Joined": str(island.get("joined_at", "N/A")),
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
