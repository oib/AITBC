"""
Hub management commands for federated mesh.
"""

import asyncio
import hashlib
import json
import os
import socket
from urllib.parse import urlparse, urlunparse

import click

try:
    from aitbc_cli.utils import error, output, success
except ImportError:
    from aitbc_cli.utils import error, output, success


def _sanitize_redis_url(url: str) -> str:
    """Remove credentials from a Redis URL before printing it."""
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except (TypeError, ValueError):
        pass
    return url


def _resolve_redis_url(redis_url: str | None, redis_password: str | None = None) -> str:
    """Resolve the Redis URL for hub commands.

    Precedence: ``--redis-url`` > ``redis_url`` config / ``REDIS_URL`` env
    (the fleet ships a credentialed URL in ``/etc/aitbc/blockchain-secrets.env``,
    which ``get_config`` already reads) > ``redis://localhost:6379``.
    ``--redis-password`` / ``REDIS_PASSWORD`` inject credentials into a URL
    that does not already carry a password.
    """
    from aitbc_cli.config import get_config

    url = redis_url or getattr(get_config(), "redis_url", None) or os.environ.get("REDIS_URL") or "redis://localhost:6379"
    password = redis_password or os.environ.get("REDIS_PASSWORD")
    if password:
        parsed = urlparse(url)
        if parsed.password is None:
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            user = parsed.username or ""
            url = urlunparse(parsed._replace(netloc=f"{user}:{password}@{host}"))
    return url


async def _ping_redis(redis_url: str) -> None:
    """Fail fast with a clean error when Redis is unreachable or rejects AUTH."""
    import redis.asyncio as aioredis
    from redis.exceptions import AuthenticationError, RedisError

    client = aioredis.from_url(redis_url)
    try:
        await client.ping()
    except AuthenticationError as e:
        raise RuntimeError(
            f"Redis authentication failed for {_sanitize_redis_url(redis_url)} — "
            "check --redis-url / REDIS_URL / --redis-password credentials"
        ) from e
    except RedisError as e:
        raise RuntimeError(f"Cannot connect to Redis at {_sanitize_redis_url(redis_url)}: {e}") from e
    finally:
        await client.close()


def register_hub_command(ctx, public_address, public_port, redis_url, hub_discovery_url, redis_password=None):
    """Register this node as a hub"""
    try:
        redis_url = _resolve_redis_url(redis_url, redis_password)
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
            await _ping_redis(redis_url)
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


def unregister_hub_command(ctx, redis_url, hub_discovery_url, redis_password=None):
    """Unregister this node as a hub"""
    try:
        redis_url = _resolve_redis_url(redis_url, redis_password)
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
            await _ping_redis(redis_url)
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


def list_hubs_command(ctx, redis_url, redis_password=None):
    """List registered hubs from Redis.

    ``HubManager`` persists registrations as JSON strings under ``hub:<node_id>``
    keys (TTL'd); the legacy ``hubs`` hash is read as a fallback source.
    """
    try:
        import redis.asyncio as redis
        from redis.exceptions import AuthenticationError, RedisError
    except ImportError as e:
        error(f"redis package required for hub commands: {e}")
        raise click.Abort() from e

    redis_url = _resolve_redis_url(redis_url, redis_password)

    async def get_hubs():
        client = redis.from_url(redis_url)
        try:
            hubs_data = []
            # Primary source: hub:<node_id> keys written by HubManager._persist_hub_registration
            async for key in client.scan_iter("hub:*"):
                raw = await client.get(key)
                if raw is None:
                    continue
                try:
                    hub_info = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(hub_info, dict):
                    continue
                key_str = key.decode() if isinstance(key, bytes) else str(key)
                hubs_data.append(
                    {
                        "Hub ID": hub_info.get("node_id") or key_str.removeprefix("hub:"),
                        "Island ID": hub_info.get("island_id"),
                        "Island Name": hub_info.get("island_name"),
                        "Address": hub_info.get("public_address") or hub_info.get("address"),
                        "Port": hub_info.get("public_port") or hub_info.get("port"),
                    }
                )
            # Fallback: legacy "hubs" hash
            hubs = await client.hgetall("hubs")
            for hub_id, hub_info_str in hubs.items():
                try:
                    hub_info = json.loads(hub_info_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(hub_info, dict):
                    continue
                hubs_data.append(
                    {
                        "Hub ID": hub_id.decode() if isinstance(hub_id, bytes) else str(hub_id),
                        "Island ID": hub_info.get("island_id"),
                        "Island Name": hub_info.get("island_name"),
                        "Address": hub_info.get("public_address") or hub_info.get("address"),
                        "Port": hub_info.get("public_port") or hub_info.get("port"),
                    }
                )
            return hubs_data
        finally:
            await client.close()

    try:
        hubs_data = asyncio.run(get_hubs())
    except AuthenticationError as e:
        error(
            f"Redis authentication failed for {_sanitize_redis_url(redis_url)} — "
            "check --redis-url / REDIS_URL / --redis-password credentials"
        )
        raise click.Abort() from e
    except RedisError as e:
        error(f"Cannot connect to Redis at {_sanitize_redis_url(redis_url)}: {e}")
        raise click.Abort() from e
    except Exception as e:
        error(f"Error listing hubs: {str(e)}")
        raise click.Abort() from e

    if not hubs_data:
        output("No hubs registered", ctx.obj.get("output", "table") if ctx and ctx.obj else "table")
        return

    output(hubs_data, ctx.obj.get("output", "table") if ctx and ctx.obj else "table", title="Registered Hubs")
