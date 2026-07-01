"""
Island management commands for federated mesh.
"""

import asyncio
import hashlib
import json
import os
import socket
import uuid

import click

try:
    from aitbc_cli.utils import error, output, success
except ImportError:
    from aitbc_cli.utils import error, output, success


def create_island_command(ctx, island_id, island_name, chain_id):
    """Create a new island"""
    try:
        if not island_id:
            island_id = str(uuid.uuid4())

        if not chain_id:
            chain_id = f"ait-{island_id[:8]}"

        island_info = {"Island ID": island_id, "Island Name": island_name, "Chain ID": chain_id, "Created": "Now"}

        output(island_info, ctx.obj.get("output", "table"), title="New Island Created")
        success(f"Island {island_name} ({island_id}) created successfully")

    except Exception as e:
        error(f"Error creating island: {str(e)}")
        raise click.Abort() from e


def join_island_command(ctx, island_id, island_name, chain_id, hub, is_hub):
    """Join an existing island"""
    try:
        from datetime import datetime

        # Get system hostname
        hostname = socket.gethostname()

        from aitbc_chain.config import settings as chain_settings

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

        # Generate node_id using hostname-based method
        local_address = socket.gethostbyname(hostname)
        local_port = chain_settings.p2p_bind_port
        content = f"{hostname}:{local_address}:{local_port}:{public_key_pem}"
        node_id = hashlib.sha256(content.encode()).hexdigest()

        # Resolve hub domain to IP
        hub_ip = socket.gethostbyname(hub)
        hub_port = chain_settings.p2p_bind_port

        click.echo(f"Connecting to hub {hub} ({hub_ip}:{hub_port})...")

        # Create P2P network service instance for sending join request
        from aitbc_chain.p2p_network import P2PNetworkService

        # Create a minimal P2P service just for sending the join request
        p2p_service = P2PNetworkService(
            local_address,
            local_port,
            node_id,
            "",
            island_id=island_id,
            island_name=island_name,
            is_hub=is_hub,
            island_chain_id=chain_id or chain_settings.island_chain_id or chain_settings.chain_id,
        )

        # Send join request
        async def send_join():
            return await p2p_service.send_join_request(hub_ip, hub_port, island_id, island_name, node_id, public_key_pem)

        response = asyncio.run(send_join())

        if response:
            # Store credentials locally
            credentials_path = "/var/lib/aitbc/island_credentials.json"
            credentials_data = {
                "island_id": response.get("island_id"),
                "island_name": response.get("island_name"),
                "island_chain_id": response.get("island_chain_id"),
                "credentials": response.get("credentials"),
                "joined_at": datetime.now().isoformat(),
            }

            with open(credentials_path, "w") as f:
                json.dump(credentials_data, f, indent=2)

            # Display join info
            join_info = {
                "Island ID": response.get("island_id"),
                "Island Name": response.get("island_name"),
                "Chain ID": response.get("island_chain_id"),
                "Member Count": len(response.get("members", [])),
                "Credentials Stored": credentials_path,
            }

            output(join_info, ctx.obj.get("output", "table"), title=f"Joined Island: {island_name}")

            # Display member list
            members = response.get("members", [])
            if members:
                output(members, ctx.obj.get("output", "table"), title="Island Members")

            # Display credentials
            credentials = response.get("credentials", {})
            if credentials:
                output(credentials, ctx.obj.get("output", "table"), title="Blockchain Credentials")

            success(f"Successfully joined island {island_name}")

            # If registering as hub
            if is_hub:
                click.echo("Registering as hub...")
                click.echo("Run 'aitbc node hub register' to complete hub registration")
        else:
            error("Failed to join island - no response from hub")
            raise click.Abort()

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
        output({"message": "No islands found"}, ctx.obj.get("output", "table"))
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

    output(islands_data, ctx.obj.get("output", "table"), title=f"Known Islands ({len(islands)} total)")


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

    output(island_data, ctx.obj.get("output", "table"), title=f"Island Information: {island_id}")


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
        output({"message": "No islands found"}, ctx.obj.get("output", "table"))
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

    output(health_rows, ctx.obj.get("output", "table"), title="Island Health")
    click.echo("")
    click.echo(f"Summary: {total} total, {active} active, {inactive} inactive, {bridging} bridging")
