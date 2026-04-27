"""Parser registration modules for the unified CLI."""

from . import ai, agent, blockchain, bridge, genesis, market, messaging, network, openclaw, pool_hub, resource, system, wallet, workflow

def register_all(subparsers, ctx):
    wallet.register(subparsers, ctx)
    blockchain.register(subparsers, ctx)
    messaging.register(subparsers, ctx)
    network.register(subparsers, ctx)
    market.register(subparsers, ctx)
    ai.register(subparsers, ctx)
    system.register(subparsers, ctx)
    agent.register(subparsers, ctx)
    openclaw.register(subparsers, ctx)
    workflow.register(subparsers, ctx)
    resource.register(subparsers, ctx)
    genesis.register(subparsers, ctx)
    pool_hub.register(subparsers, ctx)
    bridge.register(subparsers, ctx)
