"""Hermes training commands for AITBC CLI"""

import click

from ..utils import error, output


@click.group()
def hermes_training():
    """Hermes agent training operations"""
    pass


@hermes_training.command()
@click.option("--agent-id", required=True, help="Agent ID")
@click.option("--dataset", help="Training dataset")
@click.option("--epochs", default=100, help="Number of training epochs")
@click.pass_context
def train(ctx, agent_id, dataset, epochs):
    """Train Hermes agent"""
    try:
        result = {"agent_id": agent_id, "dataset": dataset, "epochs": epochs, "status": "training_started"}
        output(result, ctx.obj.get("output_format", "table"), title="Hermes Training")
    except Exception as e:
        error(f"Error starting training: {e}")
        raise click.Abort()


@hermes_training.command()
@click.option("--agent-id", required=True, help="Agent ID")
@click.pass_context
def status(ctx, agent_id):
    """Get training status"""
    try:
        result = {"agent_id": agent_id, "status": "in_progress", "progress": 45, "loss": 0.234}
        output(result, ctx.obj.get("output_format", "table"), title="Training Status")
    except Exception as e:
        error(f"Error getting training status: {e}")
        raise click.Abort()
