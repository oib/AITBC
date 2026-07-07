"""Agent Identity context database schema."""

from __future__ import annotations

# Table name prefixes for agent identity context
AGENT_IDENTITY_TABLE_PREFIX = "agent_identity_"

# Agent Identity context table names
AGENT_IDENTITY_TABLE = f"{AGENT_IDENTITY_TABLE_PREFIX}identity"
IDENTITY_VERIFICATION_TABLE = f"{AGENT_IDENTITY_TABLE_PREFIX}verification"
CROSS_CHAIN_MAPPING_TABLE = f"{AGENT_IDENTITY_TABLE_PREFIX}cross_chain_mapping"
