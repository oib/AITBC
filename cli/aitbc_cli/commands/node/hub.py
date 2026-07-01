"""
Hub management commands for federated mesh.
"""

import asyncio
import hashlib
import json
import os
import socket

import click

try:
    from ...utils.output import error, output, success
except ImportError:
    from utils import error, output, success


def register_hub_command(ctx, public_address, public_port, redis_url, hub_discovery_url):
    """Register this node as a hub"""
    try:
        # Get environment variables
        island_id = os.getenv("ISLAND_ID")
        if not island_id:
            error("ISLAND_ID environment variable not set")
            raise click.Abort()
        island_name = os.getenv("ISLAND_NAME", "default")

        # Get system hostname
        hostname = socket.gethostname()

        # Get public key from keystore
        keystore_path = "/var/lib/aitbc/keystore/validator_keys.json"
        public_key_pem = None

        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                for _key_id, key_data in keys.items():
                    public_key_pem = key_data.get("public_key_pem")
                    break
        else:
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        if not public_key_pem:
            error("No public key found in keystore")
            raise click.Abort()

        # Generate node_id
        local_address = socket.gethostbyname(hostname)
        local_port = 7070
        content = f"{hostname}:{local_address}:{local_port}:{public_key_pem}"
        node_id = hashlib.sha256(content.encode()).hexdigest()

        # Create HubManager instance
        from aitbc_chain.network.hub_discovery import HubDiscovery
        from aitbc_chain.network.hub_manager import HubManager

        hub_manager = HubManager(node_id, local_address, local_port, island_id, island_name, redis_url)

        # Register as hub (async)
        async def register_hub():
            success = await hub_manager.register_as_hub(public_address, public_port)
            if success:
                hub_discovery = HubDiscovery(hub_discovery_url, local_port)
                hub_info_dict = {
                    "node_id": node_id,
                    "address": local_address,
                    "port": local_port,
                    "island_id": island_id,
                    "island_name": island_name,
                    "public_address": public_address,
                    "public_port": public_port,
                    "public_key_pem": public_key_pem,
                }
                dns_success = await hub_discovery.register_hub(hub_info_dict)
                return success and dns_success
            return False

        result = asyncio.run(register_hub())

        if result:
            hub_info = {
                "Node ID": node_id,
                "Hostname": hostname,
                "Address": local_address,
                "Port": local_port,
                "Island ID": island_id,
                "Island Name": island_name,
                "Public Address": public_address or "auto-discovered",
                "Public Port": public_port or "auto-discovered",
                "Status": "Registered",
            }

            output(hub_info, ctx.obj.get("output", "table"), title="Hub Registration")
            success("Successfully registered as hub")
        else:
            error("Failed to register as hub")
            raise click.Abort()

    except Exception as e:
        error(f"Error registering as hub: {str(e)}")
        raise click.Abort() from e


def unregister_hub_command(ctx, redis_url, hub_discovery_url):
    """Unregister this node as a hub"""
    try:
        island_id = os.getenv("ISLAND_ID")
        if not island_id:
            error("ISLAND_ID environment variable not set")
            raise click.Abort()
        island_name = os.getenv("ISLAND_NAME", "default")

        hostname = socket.gethostname()

        keystore_path = "/var/lib/aitbc/keystore/validator_keys.json"
        public_key_pem = None

        if os.path.exists(keystore_path):
            with open(keystore_path) as f:
                keys = json.load(f)
                for _key_id, key_data in keys.items():
                    public_key_pem = key_data.get("public_key_pem")
                    break
        else:
            error(f"Keystore not found at {keystore_path}")
            raise click.Abort()

        if not public_key_pem:
            error("No public key found in keystore")
            raise click.Abort()

        local_address = socket.gethostbyname(hostname)
        local_port = 7070
        content = f"{hostname}:{local_address}:{local_port}:{public_key_pem}"
        node_id = hashlib.sha256(content.encode()).hexdigest()

        from aitbc_chain.network.hub_discovery import HubDiscovery
        from aitbc_chain.network.hub_manager import HubManager

        hub_manager = HubManager(node_id, local_address, local_port, island_id, island_name, redis_url)

        async def unregister_hub():
            success = await hub_manager.unregister_as_hub()
            if success:
                hub_discovery = HubDiscovery(hub_discovery_url, local_port)
                dns_success = await hub_discovery.unregister_hub(node_id)
                return success and dns_success
            return False

        result = asyncio.run(unregister_hub())

        if result:
            hub_info = {"Node ID": node_id, "Status": "Unregistered"}

            output(hub_info, ctx.obj.get("output", "table"), title="Hub Unregistration")
            success("Successfully unregistered as hub")
        else:
            error("Failed to unregister as hub")
            raise click.Abort()

    except Exception as e:
        error(f"Error unregistering as hub: {str(e)}")
        raise click.Abort() from e


def list_hubs_command(ctx, redis_url):
    """List registered hubs from Redis"""
    try:
        import redis.asyncio as redis

        async def get_hubs():
            client = redis.from_url(redis_url)
            hubs = await client.hgetall("hubs")
            await client.close()
            return hubs

        hubs = asyncio.run(get_hubs())

        if not hubs:
            output("No hubs registered", ctx.obj.get("output", "table"))
            return

        hubs_data = []
        for hub_id, hub_info_str in hubs.items():
            hub_info = json.loads(hub_info_str)
            hubs_data.append(
                {
                    "Hub ID": hub_id,
                    "Island ID": hub_info.get("island_id"),
                    "Island Name": hub_info.get("island_name"),
                    "Address": hub_info.get("address"),
                    "Port": hub_info.get("port"),
                }
            )

        output(hubs_data, ctx.obj.get("output", "table"), title="Registered Hubs")

    except Exception as e:
        error(f"Error listing hubs: {str(e)}")
        raise click.Abort() from e
