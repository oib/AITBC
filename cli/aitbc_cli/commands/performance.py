"""Performance commands for AITBC CLI"""

import click

from ..utils import output
from ..utils.error_handling import abort


@click.group(
    epilog="""Examples:

  aitbc performance benchmark

  aitbc performance optimize"""
)
def performance():
    """Run benchmarks, optimize, and tune system performance."""
    pass


@performance.command(
    epilog="""Examples:

  aitbc performance benchmark

  aitbc performance benchmark --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def benchmark(ctx, rpc_url):
    """Benchmark the blockchain RPC: measure read latency and report live chain stats.

    The node has no server-side benchmark endpoint (the old POST
    ``/rpc/performance/benchmark`` call always 404'd and the CLI masked that
    with fabricated numbers), so this samples real read endpoints instead.
    """
    try:
        import time

        from ..utils.http_client import AITBCHTTPClient, NetworkError

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        samples = []
        for _ in range(3):
            started = time.monotonic()
            head = http_client.get("/rpc/head")
            samples.append((time.monotonic() - started) * 1000)
        network_info = http_client.get("/rpc/network-info")
        mempool = http_client.get("/rpc/mempool")
        peers = network_info.get("peers") if isinstance(network_info, dict) else None
        pending = mempool.get("transactions", mempool) if isinstance(mempool, dict) else mempool
        result = {
            "rpc_url": rpc_url,
            "latency_ms_min": round(min(samples), 1),
            "latency_ms_avg": round(sum(samples) / len(samples), 1),
            "latency_ms_max": round(max(samples), 1),
            "chain_height": head.get("height") if isinstance(head, dict) else None,
            "peer_count": len(peers) if isinstance(peers, list) else peers,
            "mempool_pending": len(pending) if isinstance(pending, list) else pending,
        }
        output(result, ctx.obj.get("output_format", "table"), title="Performance Benchmark")
    except NetworkError as e:
        abort(ctx, f"RPC unreachable at {rpc_url}: {e}", from_exception=e)
    except Exception as e:
        abort(ctx, f"Error running benchmark: {e}", from_exception=e)


@performance.command(
    epilog="""Examples:

  aitbc performance optimize"""
)
@click.pass_context
def optimize(ctx):
    """Optimize system performance through the blockchain RPC."""
    abort(
        ctx,
        "Not implemented: the blockchain node has no performance-optimization "
        "endpoint (the old POST /rpc/performance/optimize call always 404'd).",
    )


@performance.command(
    epilog="""Examples:

  aitbc performance tune"""
)
@click.pass_context
def tune(ctx):
    """Tune system parameters through the blockchain RPC."""
    abort(
        ctx,
        "Not implemented: the blockchain node has no performance-tuning "
        "endpoint (the old POST /rpc/performance/tune call always 404'd).",
    )
