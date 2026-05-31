#!/usr/bin/env python3
"""
AITBC Click-Based CLI Entry Point
Separate entry point for Click-based commands (not parser/handler architecture)
"""

import sys
from pathlib import Path

# Add /opt/aitbc and /opt/aitbc/cli to Python path for shared modules
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/cli")))

import click

# Import Click-based command groups
from commands import agent, ai, arbitrage, cross_chain, database, edge, ipfs, island, oracle, plugin, swarm, validator

# Import commands with dependencies (may fail if dependencies not installed)
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
aitbc_click.add_command(oracle)
aitbc_click.add_command(agent)
aitbc_click.add_command(ipfs)
aitbc_click.add_command(swarm)
aitbc_click.add_command(arbitrage)
aitbc_click.add_command(validator)
aitbc_click.add_command(plugin)
aitbc_click.add_command(database)
aitbc_click.add_command(island)
aitbc_click.add_command(edge)
aitbc_click.add_command(ai)
aitbc_click.add_command(cross_chain)

# Register commands with dependencies conditionally
if MONITOR_AVAILABLE:
    aitbc_click.add_command(monitor)
if GOVERNANCE_AVAILABLE:
    aitbc_click.add_command(governance)
if STAKING_AVAILABLE:
    aitbc_click.add_command(staking)
if COMPLIANCE_AVAILABLE:
    aitbc_click.add_command(compliance)

if __name__ == "__main__":
    aitbc_click()
