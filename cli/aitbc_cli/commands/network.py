"""Network commands for AITBC CLI"""

import os
import time
from typing import Any

import click
import requests

from ..utils import output
from ..utils.error_handling import abort
from ..utils.http_client import AITBCHTTPClient, NetworkError, get_logger

logger = get_logger(__name__)


def get_default_node_id() -> str | None:
    """Get default node ID from environment file"""
    # Try to read from /etc/aitbc/node.env
    env_file = "/etc/aitbc/node.env"
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NODE_ID="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            logger.debug("Failed to read /etc/aitbc/node.env", exc_info=True)
            pass
    # Fallback to environment variable
    return os.getenv("NODE_ID")


def get_default_chain_id() -> str | None:
    """Get default chain ID from environment file"""
    # Try to read from /etc/aitbc/node.env
    env_file = "/etc/aitbc/node.env"
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SUPPORTED_CHAINS="):
                        # SUPPORTED_CHAINS can be comma-separated, take first
                        chains = line.split("=", 1)[1].strip()
                        return chains.split(",")[0].strip()
        except Exception:
            logger.debug("Failed to read /etc/aitbc/node.env", exc_info=True)
            pass
    # Fallback to environment variable
    return os.getenv("SUPPORTED_CHAINS")


@click.group(
    epilog="""Examples:

  aitbc network status

  aitbc network peers"""
)
def network():
    """Manage peer connectivity, network synchronization, subscriptions, and heartbeats."""
    pass


@network.command(
    epilog="""Examples:

  aitbc network status

  aitbc network status --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def status(ctx, rpc_url):
    """Check the current network and peer connectivity status."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        status = http_client.get("/rpc/network-info")
        output(status, ctx.obj.get("output_format", "table"), title="Network Status")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        status = {
            "network_status": "simulated",
            "connected_peers": 0,
            "block_height": 0,
            "message": "RPC endpoint not available - showing simulated status",
        }
        output(status, ctx.obj.get("output_format", "table"), title="Network Status (Simulated)")
    except Exception as e:
        abort(ctx, f"Error getting network status: {e}", from_exception=e)


@network.command(
    epilog="""Examples:

  aitbc network peers

  aitbc network peers --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def peers(ctx, rpc_url):
    """List connected peers and basic peer information."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        peers = http_client.get("/rpc/network-info")
        output(peers, ctx.obj.get("output_format", "table"), title="Connected Peers")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        peers = {"status": "simulated", "peers": [], "message": "RPC endpoint not available - showing simulated peers"}
        output(peers, ctx.obj.get("output_format", "table"), title="Connected Peers (Simulated)")
    except Exception as e:
        abort(ctx, f"Error listing peers: {e}", from_exception=e)


@network.command(
    epilog="""Examples:

  aitbc network test --peer node-1

  aitbc network test --peer node-1 --rpc-url http://localhost:8202"""
)
@click.option("--peer", required=True, help="Peer address to test")
@click.option("--rpc-url", default=None, help="Blockchain RPC URL")
@click.pass_context
def test(ctx, peer, rpc_url):
    """Test connectivity to a specific peer address.

    By default the command probes the peer's public API gateway at
    https://<peer>/health. If an explicit --rpc-url is given, it probes that
    base URL's /health endpoint instead.
    """
    try:
        base_url = rpc_url
        if not base_url:
            base_url = f"https://{peer}"
        url = f"{base_url}/health"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        try:
            body: dict[str, Any] = resp.json()
        except Exception:
            body = {"status": resp.text}
        body["peer"] = peer
        body["endpoint"] = url
        output(body, ctx.obj.get("output_format", "table"), title=f"Connectivity Test: {peer}")
    except requests.RequestException as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error testing connectivity: {e}", from_exception=e)


@network.command(
    epilog="""Examples:

  aitbc network force-sync

  aitbc network force-sync --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def force_sync(ctx, rpc_url):
    """Force the local node to synchronize with the network."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/force-sync", json={})
        output(result, ctx.obj.get("output_format", "table"), title="Force Sync")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error forcing sync: {e}", from_exception=e)


@network.command(
    epilog="""Examples:

  aitbc network subscribe

  aitbc network subscribe --node-id node-1 --chain-id ait-mainnet --duration 600"""
)
@click.option("--node-id", help="Unique identifier for this follower node (default: from NODE_ID in /etc/aitbc/node.env)")
@click.option(
    "--transport",
    default="websocket",
    type=click.Choice(["websocket", "http", "redis"]),
    help="Transport method for block delivery",
)
@click.option("--chain-id", help="Chain ID to subscribe to (default: from SUPPORTED_CHAINS in /etc/aitbc/node.env)")
@click.option("--duration", type=int, default=300, help="Lease duration in seconds (default: 300)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def subscribe(ctx, node_id, transport, chain_id, duration, rpc_url):
    """Register this node as a follower for block subscription."""
    if not node_id:
        node_id = get_default_node_id()
        if not node_id:
            abort(ctx, "node-id is required. Set NODE_ID in /etc/aitbc/node.env or use --node-id option")

    if not chain_id:
        chain_id = get_default_chain_id()
        if not chain_id:
            abort(ctx, "chain-id is required. Set SUPPORTED_CHAINS in /etc/aitbc/node.env or use --chain-id option")

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        subscription_data = {"node_id": node_id, "transport": transport, "chain_id": chain_id, "duration": duration}
        result = http_client.post("/rpc/subscribe", json=subscription_data)
        output(result, ctx.obj.get("output_format", "table"), title="Subscription Registered")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error registering subscription: {e}", from_exception=e)


@network.command(
    epilog="""Examples:

  aitbc network heartbeat

  aitbc network heartbeat --node-id node-1 --duration 300"""
)
@click.option("--node-id", help="Subscriber node ID (default: from NODE_ID in /etc/aitbc/node.env)")
@click.option("--duration", type=int, help="Additional lease duration in seconds")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def heartbeat(ctx, node_id, duration, rpc_url):
    """Send a heartbeat to extend a subscription lease."""
    if not node_id:
        node_id = get_default_node_id()
        if not node_id:
            abort(ctx, "node-id is required. Set NODE_ID in /etc/aitbc/node.env or use --node-id option")

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        heartbeat_data = {"node_id": node_id, "duration": duration}
        result = http_client.post("/rpc/subscription/heartbeat", json=heartbeat_data)
        output(result, ctx.obj.get("output_format", "table"), title="Lease Extended")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error extending lease: {e}", from_exception=e)


@network.command(
    epilog="""Examples:

  aitbc network lease-status

  aitbc network lease-status --node-id node-1"""
)
@click.option("--node-id", help="Subscriber node ID (default: from NODE_ID in /etc/aitbc/node.env)")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def lease_status(ctx, node_id, rpc_url):
    """Check the current lease status for a subscriber."""
    if not node_id:
        node_id = get_default_node_id()
        if not node_id:
            abort(ctx, "node-id is required. Set NODE_ID in /etc/aitbc/node.env or use --node-id option")

    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.get(f"/rpc/lease/{node_id}")
        output(result, ctx.obj.get("output_format", "table"), title="Lease Status")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error checking lease status: {e}", from_exception=e)


@network.command(
    epilog="""Examples:

  aitbc network subscribers

  aitbc network subscribers --chain-id ait-mainnet"""
)
@click.option("--chain-id", help="Filter by chain ID")
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def subscribers(ctx, chain_id, rpc_url):
    """List all active subscribers, optionally filtered by chain."""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        params = {"chain_id": chain_id} if chain_id else {}
        result = http_client.get("/rpc/subscribers", params=params)
        output(result, ctx.obj.get("output_format", "table"), title="Active Subscribers")
    except NetworkError as e:
        abort(ctx, f"Network error: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error listing subscribers: {e}", from_exception=e)


_PromSamples = dict[str, list[tuple[dict[str, str], float]]]


def _scrape_prom(url: str, timeout: int) -> _PromSamples:
    """Fetch a Prometheus text endpoint and index its samples by metric name.

    The shared AITBCHTTPClient always calls .json() on the response, so it
    cannot read /metrics. Scrape it directly instead.
    """
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    samples: _PromSamples = {}
    for raw in resp.text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, rest = line.partition("{")
        if rest:
            labelstr, _, valstr = rest.partition("}")
            labels = {}
            for part in labelstr.split(","):
                key, _, val = part.partition("=")
                if key:
                    labels[key.strip()] = val.strip().strip('"')
        else:
            name, _, valstr = line.partition(" ")
            labels = {}
        try:
            value = float(valstr.strip())
        except ValueError:
            continue
        samples.setdefault(name.strip(), []).append((labels, value))
    return samples


def _sample_map(samples: _PromSamples, metric: str, label: str) -> dict[str, float]:
    """Collapse one labelled metric into {label_value: sample_value}."""
    return {lbls[label]: val for lbls, val in samples.get(metric, []) if label in lbls}


def _sample_total(samples: _PromSamples, metric: str) -> float:
    return sum(val for _, val in samples.get(metric, []))


@network.command(
    epilog="""Examples:

  aitbc network gossip

  aitbc network gossip --rpc-url http://localhost:8202

  aitbc network gossip --topics""",
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.option("--topics", is_flag=True, help="Also break published message counts down by topic")
@click.pass_context
def gossip(ctx, rpc_url, topics):
    """Show gossip websocket health: which validators have authenticated, and traffic.

    Reports the *inbound* side of gossip - the public `/rpc/gossip/ws`
    endpoint this node serves to its peers - by joining the validator set
    from /rpc/network-info against the auth counters on /metrics.

    A healthy node shows one authenticated peer per *other* validator: a node
    never dials its own websocket, so exactly one validator row is expected to
    read `no`. Two or more mean a peer is not reaching this node.

    This does not cover the node process's *outbound* mesh links. Those live in
    aitbc-blockchain-node, which serves no HTTP endpoint; check them with
    scripts/monitoring/fleet-config-check.sh, which reads GOSSIP_MESH_PEER_URLS
    from the running process.
    """
    fmt = ctx.obj.get("output_format", "table")
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        info = http_client.get("/rpc/network-info")
    except NetworkError as e:
        abort(ctx, f"Could not reach the RPC at {rpc_url}: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error getting network info: {e}", from_exception=e)

    try:
        samples = _scrape_prom(f"{rpc_url.rstrip('/')}/metrics", 10)
    except Exception as e:
        abort(ctx, f"Error scraping {rpc_url}/metrics: {e}", from_exception=e)

    accepted = _sample_map(samples, "blockchain_gossip_auth_accepted_total", "address")
    rejected = _sample_map(samples, "blockchain_gossip_auth_rejected_total", "reason")
    live = _sample_map(samples, "blockchain_gossip_authenticated_connections", "address")

    # Prefer the liveness gauge. It only exists on nodes running a build that
    # has it; on older ones fall back to the auth counter, which answers the
    # weaker question "did this peer ever authenticate since the RPC started".
    have_gauge = "blockchain_gossip_authenticated_connections" in samples
    basis = "live connections" if have_gauge else "auth counters (no liveness gauge on this node)"

    def _is_connected(address: str) -> bool:
        if have_gauge:
            return live.get(address, 0) > 0
        return accepted.get(address, 0) > 0

    validators = info.get("validators") or []
    peer_rows = []
    for validator in validators:
        address = validator.get("address", "")
        peer_rows.append(
            {
                "address": address,
                "stake": validator.get("stake", ""),
                "connected": "yes" if _is_connected(address) else "no",
                "open": int(live.get(address, 0)) if have_gauge else "-",
                "auth_ok": int(accepted.get(address, 0)),
            }
        )

    # Peers that authenticated but are not in the advertised validator set.
    known = {validator.get("address") for validator in validators}
    for address in sorted(set(accepted) | set(live)):
        if address not in known:
            peer_rows.append(
                {
                    "address": address,
                    "stake": "(not a validator)",
                    "connected": "yes" if _is_connected(address) else "no",
                    "open": int(live.get(address, 0)) if have_gauge else "-",
                    "auth_ok": int(accepted.get(address, 0)),
                }
            )

    connected = sum(1 for row in peer_rows if row["connected"] == "yes")
    expected = max(len(validators) - 1, 0)

    # Counters are cumulative since the RPC started, so a fresh restart reads
    # zero for peers that are perfectly healthy and have simply not redialled
    # yet. Report the uptime alongside so a zero can be read correctly.
    started = _sample_total(samples, "process_start_time_seconds")
    rpc_uptime = int(time.time() - started) if started else None

    summary = {
        "node_id": info.get("node_id"),
        "chain_id": info.get("chain_id"),
        "gossip_websocket_url": info.get("gossip_websocket_url"),
        "auth_required": info.get("gossip_auth_required"),
        "validators": len(validators),
        "peers_connected": connected,
        "peers_expected": expected,
        "basis": basis,
        "rpc_uptime_seconds": rpc_uptime,
        "open_connections": int(_sample_total(samples, "blockchain_gossip_open_connections")) if have_gauge else "-",
        "auth_failures": int(_sample_total(samples, "blockchain_gossip_auth_rejected_total")),
        "rate_limited": int(_sample_total(samples, "blockchain_gossip_rate_limited_total")),
        "oversized_dropped": int(_sample_total(samples, "blockchain_gossip_oversized_message_total")),
        "messages_published": int(_sample_total(samples, "blockchain_gossip_messages_published_total")),
        "verdict": "ok" if connected >= expected else "degraded",
    }

    rejections = [{"reason": reason, "count": int(count)} for reason, count in sorted(rejected.items())]

    if fmt == "json":
        payload = {"summary": summary, "peers": peer_rows, "auth_rejections": rejections}
        if topics:
            payload["topics"] = _sample_map(samples, "blockchain_gossip_messages_published_total", "topic")
        output(payload, fmt, title="Gossip Status")
        return

    output(summary, fmt, title="Gossip Status")
    if peer_rows:
        output(peer_rows, fmt, title="Gossip Peers (inbound)")
    if rejections:
        output(rejections, fmt, title="Auth Rejections by Reason")
    if topics:
        by_topic = _sample_map(samples, "blockchain_gossip_messages_published_total", "topic")
        rows = [{"topic": topic, "published": int(count)} for topic, count in sorted(by_topic.items())]
        output(rows or [{"topic": "(none)", "published": 0}], fmt, title="Published by Topic")
