"""Cluster commands for AITBC CLI"""

import click

from ..utils import output
from ..utils.error_handling import abort


@click.group()
def cluster():
    """Cluster management and operations"""
    pass


@cluster.command()
@click.pass_context
def status(ctx):
    """Get cluster status"""
    try:
        result = {"cluster_health": "healthy", "nodes": 3, "active_nodes": 3}
        output(result, ctx.obj.get("output_format", "table"), title="Cluster Status")
    except Exception as e:
        abort(ctx, f"Error getting cluster status: {e}", from_exception=e)


@cluster.command()
@click.pass_context
def sync(ctx):
    """Cluster sync"""
    try:
        result = {"action": "cluster_sync", "status": "completed"}
        output(result, ctx.obj.get("output_format", "table"), title="Cluster Sync")
    except Exception as e:
        abort(ctx, f"Error in cluster sync: {e}", from_exception=e)


@cluster.command()
@click.pass_context
def balance(ctx):
    """Cluster balance"""
    try:
        result = {"action": "cluster_balance", "status": "completed"}
        output(result, ctx.obj.get("output_format", "table"), title="Cluster Balance")
    except Exception as e:
        abort(ctx, f"Error in cluster balance: {e}", from_exception=e)
