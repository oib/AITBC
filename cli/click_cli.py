#!/usr/bin/env python3
"""
AITBC Click-Based CLI Entry Point
Separate entry point for Click-based commands (not parser/handler architecture)
"""

import sys
from pathlib import Path

# Add /opt/aitbc to Python path for shared modules
sys.path.insert(0, str(Path("/opt/aitbc")))

import click

# Import Click-based command groups
from commands import oracle
from commands import agent
from commands import ipfs
from commands import swarm
from commands import arbitrage
from commands import validator
from commands import plugin
from commands import database
from commands import island
from commands import edge
from commands import ai

# Import commands with dependencies (may fail if dependencies not installed)
# cross_chain requires tabulate - not available in click_cli
CROSS_CHAIN_AVAILABLE = False

try:
    from commands import monitor
    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False

try:
    from commands import governance
    GOVERNANCE_AVAILABLE = True
except ImportError:
    GOVERNANCE_AVAILABLE = False

try:
    from commands import staking
    STAKING_AVAILABLE = True
except ImportError:
    STAKING_AVAILABLE = False

try:
    from commands import compliance
    COMPLIANCE_AVAILABLE = True
except ImportError:
    COMPLIANCE_AVAILABLE = False

@click.group()
@click.version_option(version="2.1.0")
def aitbc_click():
    """AITBC Click-based CLI - Separate entry point for Click commands"""
    pass

# Register command groups
aitbc_click.add_command(oracle.oracle)
aitbc_click.add_command(agent.agent)
aitbc_click.add_command(ipfs.ipfs)
aitbc_click.add_command(swarm.swarm)
aitbc_click.add_command(arbitrage.arbitrage)
aitbc_click.add_command(validator.validator)
aitbc_click.add_command(plugin.plugin)
aitbc_click.add_command(database.database)
aitbc_click.add_command(island.island)
aitbc_click.add_command(edge.edge)
aitbc_click.add_command(ai.ai_group)

# Register commands with dependencies conditionally
if CROSS_CHAIN_AVAILABLE:
    aitbc_click.add_command(cross_chain.cross_chain)
if MONITOR_AVAILABLE:
    aitbc_click.add_command(monitor.monitor)
if GOVERNANCE_AVAILABLE:
    aitbc_click.add_command(governance.governance)
if STAKING_AVAILABLE:
    aitbc_click.add_command(staking.staking)
if COMPLIANCE_AVAILABLE:
    aitbc_click.add_command(compliance.compliance)

if __name__ == "__main__":
    aitbc_click()
