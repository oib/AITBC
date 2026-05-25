#!/usr/bin/env python3
"""AITBC Command Line Interface - Main Entry Point."""

import click
from .commands import (
    wallet,
    workflow,
    transactions,
    agent_comm,
    system,
    system_architect,
    simulate,
    resource,
    operations,
    monitor,
    mining,
    node,
    marketplace_cmd,
    hermes,
    genesis,
    gpu_marketplace,
    exchange,
    exchange_island,
    edge,
    deployment,
    cross_chain,
    config,
    chain,
    analytics,
    agent_sdk,
)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """AITBC Command Line Interface."""
    pass


# Add command groups
cli.add_command(wallet.wallet)
cli.add_command(workflow.workflow)
cli.add_command(transactions.transactions)
cli.add_command(agent_comm.agent_comm)
cli.add_command(system.system)
cli.add_command(system_architect.system_architect)
cli.add_command(simulate.simulate)
cli.add_command(resource.resource)
cli.add_command(operations.operations)
cli.add_command(monitor.monitor)
cli.add_command(mining.mining)
cli.add_command(node.node)
cli.add_command(marketplace_cmd.marketplace_cmd)
cli.add_command(hermes.hermes)
cli.add_command(genesis.genesis)
cli.add_command(gpu_marketplace.gpu_marketplace)
cli.add_command(exchange.exchange)
cli.add_command(exchange_island.exchange_island)
cli.add_command(edge.edge)
cli.add_command(deployment.deployment)
cli.add_command(cross_chain.cross_chain)
cli.add_command(config.config)
cli.add_command(chain.chain)
cli.add_command(analytics.analytics)
cli.add_command(agent_sdk.agent_sdk)


if __name__ == "__main__":
    cli()
