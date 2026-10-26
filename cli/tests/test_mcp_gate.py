"""MCP-GATE-AUDIT-1: every MCP tool whose CLI leaf mutates must carry dry_run + confirm."""

import re
from pathlib import Path


MCP_DIR = Path(__file__).resolve().parents[2] / "mcp-server"

MUTATING = re.compile(
    r"(create|delete|register|update|submit|post|send|write|start|stop|restart|add|remove|set|reset|"
    r"deploy|init|install|enable|disable|activate|deactivate|approve|reject|confirm|execute|vote|stake|"
    r"transfer|withdraw|deposit|pay|charge|refund|allocate|release|lock|unlock|slash|appeal|bridge|swap|"
    r"join|leave|migrate|import|export|backup|restore|sync|pull|push|harden|clean|wipe|kill|terminate|"
    r"connect|disconnect|bond|top_up|top-up|topup|grant|revoke|pin|unpin|hide|unhide|promote|demote|"
    r"reopen|rebroadcast|resign|abandon|claim|earn|reinvest|buy|sell|trade|order|bid|offer)"
)
# Leaf names that look mutating but are confirmed reads (director's audit).
# Tool names that name-match the mutating regex but are confirmed reads.
READ_ONLY = {
    "aitbc_blockchain_block",
    "aitbc_blockchain_consensus_status",
    "aitbc_blockchain_consensus_validators",
    "aitbc_blockchain_height",
    "aitbc_blockchain_info",
    "aitbc_blockchain_list",
    "aitbc_blockchain_status",
    "aitbc_bond_status",
    "aitbc_bridge_balance",
    "aitbc_bridge_health",
    "aitbc_bridge_pending",
    "aitbc_bridge_security_status",
    "aitbc_bridge_status",
    "aitbc_crosschain_bridge_status",
    "aitbc_dispute_votes",
    "aitbc_eth_transfers",
    "aitbc_exchange_sell_admin_status",
    "aitbc_exchange_island_orderbook",
    "aitbc_exchange_island_orders",
    "aitbc_explorer_block_by_hash",
    "aitbc_explorer_blocks_by_address",
    "aitbc_explorer_non_empty_blocks",
    "aitbc_explorer_top_addresses",
    "aitbc_grant_list",
    "aitbc_market_exchange_list_deposits",
    "aitbc_reinvest_simulate",
    "aitbc_wallet_address",
    "aitbc_wallet_bridge_float",
    "aitbc_wallet_bridge_status",
}


def _cli_leaves(node, path):
    kids = getattr(node, "commands", {})
    if not kids:
        yield " ".join(path)
        return
    for name, child in kids.items():
        yield from _cli_leaves(child, path + (name,))


def _tool_names():
    for f in sorted(MCP_DIR.glob("aitbc_mcp_cli_tools_generated_*.py")):
        if f.name == "aitbc_mcp_cli_tools_generated.py":
            continue
        for m in re.finditer(r"^(?:async )?def (\w+)\(", f.read_text(), re.M):
            yield f.name, m.group(1)


def test_mutating_tools_have_gates():
    """Every generated tool whose name implies mutation must declare
    dry_run and confirm parameters."""
    missing = []
    for f, name in _tool_names():
        if not MUTATING.search(name) or name in READ_ONLY:
            continue
        src = (MCP_DIR / f).read_text()
        m = re.search(rf"(?:async )?def {name}\s*\((.*?)\) -> ", src, re.S)
        if not m:
            missing.append((f, name))
            continue
        params = m.group(1)
        if "dry_run" not in params or "confirm" not in params:
            missing.append((f, name))
    assert missing == [], f"mutating tools without gates: {missing}"


def test_all_tools_present():
    assert len(list(_tool_names())) >= 500
