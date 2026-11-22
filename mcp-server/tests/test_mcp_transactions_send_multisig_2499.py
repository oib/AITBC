"""#2499: the MCP send tool must route through the guarded CLI path.

``aitbc_transactions_send`` shells out to ``aitbc transactions send``,
which funnels into ``_send_transaction_impl`` — where the shared
multisig-recipient refusal (#2362, extended by #2499) runs. This pin fails
if the tool is ever rewired to bypass the CLI impl.
"""

import importlib
import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server

# Deterministic role map — same stub as test_aitbc_mcp_cli_tools.py.
mcp_server._HOSTS_CONFIG = {
    "roles": {"hub": "hub", "customer": "node0", "shop": "node2"},
    "default_host": "hub",
    "ssh_user": "",
}


def test_transactions_send_dry_run_targets_guarded_cli_command():
    func = importlib.import_module("aitbc_mcp_cli_tools_generated_transactions").aitbc_transactions_send
    out = json.loads(
        func(
            to_address="0x" + "ab" * 20,
            amount="1",
            from_wallet="w1",
            dry_run=True,
            confirm=False,
        )
    )
    command = out.get("command") or []
    assert "transactions" in command
    assert "send" in command
