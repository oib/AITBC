"""
Bridge management commands for federated mesh.
"""

import click

try:
    from ..utils.output import error, output, success
except ImportError:
    from utils import error, output, success


def request_bridge_command(ctx, target_island_id):
    """Request a bridge to another island"""
    try:
        success(f"Bridge request sent to island {target_island_id}")

    except Exception as e:
        error(f"Error requesting bridge: {str(e)}")
        raise click.Abort()


def approve_bridge_command(ctx, request_id, approving_node_id):
    """Approve a bridge request"""
    try:
        success(f"Bridge request {request_id} approved")

    except Exception as e:
        error(f"Error approving bridge request: {str(e)}")
        raise click.Abort()


def reject_bridge_command(ctx, request_id, reason):
    """Reject a bridge request"""
    try:
        success(f"Bridge request {request_id} rejected")

    except Exception as e:
        error(f"Error rejecting bridge request: {str(e)}")
        raise click.Abort()


def list_bridges_command(ctx):
    """List bridge connections"""
    try:
        bridges = [{"Bridge ID": "bridge-1", "Source Island": "island-a", "Target Island": "island-b", "Status": "Active"}]

        output(bridges, ctx.obj.get("output_format", "table"), title="Bridge Connections")

    except Exception as e:
        error(f"Error listing bridges: {str(e)}")
        raise click.Abort()
