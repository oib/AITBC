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
    """Run a performance benchmark against the blockchain RPC."""
    try:
        from ..utils.http_client import AITBCHTTPClient, NetworkError

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/performance/benchmark")
        output(result, ctx.obj.get("output_format", "table"), title="Performance Benchmark")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        result = {
            "status": "simulated",
            "tps": 1000,
            "latency_ms": 50,
            "message": "RPC endpoint not available - showing simulated benchmark",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Performance Benchmark (Simulated)")
    except Exception as e:
        abort(ctx, f"Error running benchmark: {e}", from_exception=e)


@performance.command(
    epilog="""Examples:

  aitbc performance optimize

  aitbc performance optimize --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def optimize(ctx, rpc_url):
    """Optimize system performance through the blockchain RPC."""
    try:
        from ..utils.http_client import AITBCHTTPClient, NetworkError

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/performance/optimize")
        output(result, ctx.obj.get("output_format", "table"), title="Performance Optimization")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        result = {
            "status": "simulated",
            "optimization_applied": False,
            "message": "RPC endpoint not available - showing simulated optimization",
        }
        output(result, ctx.obj.get("output_format", "table"), title="Performance Optimization (Simulated)")
    except Exception as e:
        abort(ctx, f"Error optimizing performance: {e}", from_exception=e)


@performance.command(
    epilog="""Examples:

  aitbc performance tune

  aitbc performance tune --rpc-url http://localhost:8202"""
)
@click.option("--rpc-url", default="http://localhost:8202", help="Blockchain RPC URL")
@click.pass_context
def tune(ctx, rpc_url):
    """Tune system parameters through the blockchain RPC."""
    try:
        from ..utils.http_client import AITBCHTTPClient, NetworkError

        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/performance/tune")
        output(result, ctx.obj.get("output_format", "table"), title="System Tuning")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        result = {
            "status": "simulated",
            "parameters_tuned": [],
            "message": "RPC endpoint not available - showing simulated tuning",
        }
        output(result, ctx.obj.get("output_format", "table"), title="System Tuning (Simulated)")
    except Exception as e:
        abort(ctx, f"Error tuning system: {e}", from_exception=e)
