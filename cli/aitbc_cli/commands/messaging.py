"""Messaging commands for AITBC CLI"""

import click

from ..utils import error, output
from ..utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def messaging():
    """Messaging system and forum operations"""
    pass


@messaging.command()
@click.option('--recipient', required=True, help='Recipient address')
@click.option('--message', required=True, help='Message content')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def send(ctx, recipient, message, rpc_url):
    """Send a message"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/messaging/send", json={
            "recipient": recipient,
            "message": message
        })
        output(result, ctx.obj.get('output_format', 'table'), title="Message Sent")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        result = {
            "status": "simulated",
            "recipient": recipient,
            "message": message,
            "message_id": "simulated_id",
            "timestamp": "now"
        }
        output(result, ctx.obj.get('output_format', 'table'), title="Message Sent (Simulated)")
    except Exception as e:
        error(f"Error sending message: {e}")
        raise click.Abort()


@messaging.command()
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def list(ctx, rpc_url):
    """List messages"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        messages = http_client.get("/rpc/messaging/list")
        output(messages, ctx.obj.get('output_format', 'table'), title="Messages")
    except NetworkError:
        # Fallback to simulated data if RPC endpoint not available
        messages = {
            "status": "simulated",
            "messages": [],
            "message": "RPC endpoint not available - showing simulated list"
        }
        output(messages, ctx.obj.get('output_format', 'table'), title="Messages (Simulated)")
    except Exception as e:
        error(f"Error listing messages: {e}")
        raise click.Abort()


@messaging.command()
@click.option('--title', required=True, help='Topic title')
@click.option('--description', required=True, help='Topic description')
@click.option('--rpc-url', default='http://localhost:8202', help='Blockchain RPC URL')
@click.pass_context
def topic(ctx, title, description, rpc_url):
    """Create forum topic"""
    try:
        http_client = AITBCHTTPClient(base_url=rpc_url, timeout=10)
        result = http_client.post("/rpc/messaging/topic", json={
            "title": title,
            "description": description
        })
        output(result, ctx.obj.get('output_format', 'table'), title="Topic Created")
    except NetworkError as e:
        error(f"Network error: {e}")
        raise click.Abort()
    except Exception as e:
        error(f"Error creating topic: {e}")
        raise click.Abort()
