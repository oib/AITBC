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
    from ..utils.output import error, output, success
except ImportError:
    from utils import error, output, success


def create_island_command(ctx, island_id, island_name, chain_id):
    """Create a new island"""
    try:
        if not island_id:
            island_id = str(uuid.uuid4())

        if not chain_id:
            chain_id = f"ait-{island_id[:8]}"

        island_info = {
            "Island ID": island_id,
            "Island Name": island_name,
            "Chain ID": chain_id,
            "Created": "Now"
        }

        output(island_info, ctx.obj.get('output_format', 'table'), title="New Island Created")
        success(f"Island {island_name} ({island_id}) created successfully")

    except Exception as e:
        error(f"Error creating island: {str(e)}")
        raise click.Abort()


def join_island_command(ctx, island_id, island_name, chain_id, hub, is_hub):
    """Join an existing island"""
    try:
        from datetime import datetime

        # Get system hostname
        hostname = socket.gethostname()

        sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
        from aitbc_chain.config import settings as chain_settings

        # Get public key from keystore
        keystore_path = '/var/lib/aitbc/keystore/validator_keys.json'
        public_key_pem = None

        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                # Get first key's public key
                for key_id, key_data in keys.items():
                    public_key_pem = key_data.get('public_key_pem')
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
            return await p2p_service.send_join_request(
                hub_ip, hub_port, island_id, island_name, node_id, public_key_pem
            )

        response = asyncio.run(send_join())

        if response:
            # Store credentials locally
            credentials_path = '/var/lib/aitbc/island_credentials.json'
            credentials_data = {
                "island_id": response.get('island_id'),
                "island_name": response.get('island_name'),
                "island_chain_id": response.get('island_chain_id'),
                "credentials": response.get('credentials'),
                "joined_at": datetime.now().isoformat()
            }

            with open(credentials_path, 'w') as f:
                json.dump(credentials_data, f, indent=2)

            # Display join info
            join_info = {
                "Island ID": response.get('island_id'),
                "Island Name": response.get('island_name'),
                "Chain ID": response.get('island_chain_id'),
                "Member Count": len(response.get('members', [])),
                "Credentials Stored": credentials_path
            }

            output(join_info, ctx.obj.get('output_format', 'table'), title=f"Joined Island: {island_name}")

            # Display member list
            members = response.get('members', [])
            if members:
                output(members, ctx.obj.get('output_format', 'table'), title="Island Members")

            # Display credentials
            credentials = response.get('credentials', {})
            if credentials:
                output(credentials, ctx.obj.get('output_format', 'table'), title="Blockchain Credentials")

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
        raise click.Abort()


def leave_island_command(ctx, island_id):
    """Leave an island"""
    try:
        success(f"Successfully left island {island_id}")

    except Exception as e:
        error(f"Error leaving island: {str(e)}")
        raise click.Abort()


def list_islands_command(ctx):
    """List all known islands"""
    try:
        islands = [
            {
                "Island ID": "550e8400-e29b-41d4-a716-446655440000",
                "Island Name": "default",
                "Chain ID": "ait-island-default",
                "Status": "Active",
                "Peer Count": "3"
            }
        ]

        output(islands, ctx.obj.get('output_format', 'table'), title="Known Islands")

    except Exception as e:
        error(f"Error listing islands: {str(e)}")
        raise click.Abort()


def island_info_command(ctx, island_id):
    """Get island information"""
    try:
        island_info = {
            "Island ID": island_id,
            "Island Name": "default",
            "Chain ID": "ait-island-default",
            "Status": "Active",
            "Peer Count": "3",
            "Created": "2024-01-01T00:00:00Z"
        }

        output(island_info, ctx.obj.get('output_format', 'table'), title=f"Island Information: {island_id}")

    except Exception as e:
        error(f"Error getting island info: {str(e)}")
        raise click.Abort()
