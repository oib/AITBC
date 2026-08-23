"""Every URL this app builds for the chain node must exist on the chain node.

V23-42. `contexts/blockchain/services/blockchain.py` built fourteen URLs and not one of them
resolved: the node mounts its whole RPC surface under `/rpc` and none of the paths carried
that prefix, and twelve had no counterpart under any prefix. It went unnoticed for two
reasons worth keeping in mind, because both are shapes that recur:

1. The calls run in FastAPI background tasks that catch `NetworkError` into a log line. The
   router has already returned 201 by the time the 404 arrives, so a client that stakes or
   deploys a bounty is told it succeeded while nothing reaches the chain.
2. `tests/fixtures/mock_blockchain_node.py` implemented `/rpc/admin/mintFaucet` and
   `/rpc/getBalance/{address}` — endpoints no node has ever served. **The mock was written to
   match the client rather than the server**, so the integration suite proved only that the
   client agreed with itself.

This test compares the client's URLs against the node's real route table, built by importing
`aitbc_chain` — no running node, no mock in the middle. KNOWN_MISSING is a ratchet: entries
may be removed as endpoints appear or calls are deleted, and a new unresolvable URL fails.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


CLIENT = (
    Path(__file__).resolve().parents[1] / "src" / "coordinator_api" / "contexts" / "blockchain" / "services" / "blockchain.py"
)

# The one client path with a real counterpart on the node. It is still not usable: the node
# wants {address, amount, lock_days, signature} and answers 403 without a staker signature,
# which this app cannot produce -- it holds no agent staking key. Adding the /rpc prefix would
# turn a 404 into a 403 and nothing more, so the URL is left alone and the gap named here.
SIGNATURE_BLOCKED = {"/staking/stake"}

# Paths the client asks for that the node does not serve *at all*, under any prefix. Every one
# is a real gap, not a spelling difference -- see the BlockchainService docstring.
KNOWN_MISSING = {
    "/staking/performance",
    "/staking/stake/{}/add",
    "/staking/stake/{}/unbond",
    "/staking/stake/{}/complete",
    "/staking/agents/{}/distribute",
    "/staking/claim-rewards",
    "/bounty/deploy",
    "/bounty/{}/submit",
    "/bounty/{}/verify",
    "/bounty/{}/dispute",
    "/bounty/{}/expire",
}


def _placeholders(path: str) -> str:
    """`/balance/{address}` and `/balance/{addr}` are the same route to this comparison."""
    return re.sub(r"\{[^}]*\}", "{}", path)


def _client_paths() -> set[str]:
    """Every path this app builds onto the node's base URL, from the source itself.

    Reading the AST rather than importing means a request never leaves the process and the
    set cannot be narrowed by a stubbed-out client.
    """
    tree = ast.parse(CLIENT.read_text(encoding="utf-8"))
    bases = {"BLOCKCHAIN_RPC", "RPC", "rpc_url"}
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        rendered = ""
        leads_with_base = False
        for i, part in enumerate(node.values):
            if isinstance(part, ast.FormattedValue):
                name = ast.unparse(part.value).split(".")[-1]
                if i == 0 and name in bases:
                    leads_with_base = True
                    # RPC is BLOCKCHAIN_RPC + "/rpc"; spell that out so the comparison sees
                    # the same string the node registers.
                    rendered += "/rpc" if name == "RPC" else ""
                else:
                    rendered += "{}"
            elif isinstance(part, ast.Constant):
                rendered += str(part.value)
        # `RPC = f"{BLOCKCHAIN_RPC}/rpc"` is the base definition, not a call site.
        if leads_with_base and rendered.startswith("/") and rendered != "/rpc":
            found.add(rendered)
    return found


def _node_paths() -> set[str]:
    """The node's real route table, under the /rpc prefix app.py mounts it at."""
    from aitbc_chain.rpc.router import router

    return {_placeholders(f"/rpc{route.path}") for route in router.routes if getattr(route, "path", None)}


def test_client_paths_were_found():
    """A parser that silently finds nothing would make every assertion below vacuous."""
    paths = _client_paths()
    assert len(paths) >= 13, f"expected the client's URLs, parsed {len(paths)}: {sorted(paths)}"
    assert "/rpc/balance/{}" in paths, "the repaired get_balance URL should parse out"


def test_client_paths_resolve_on_node():
    """Every coordinator URL built for the chain must exist on the chain."""
    client = _client_paths()
    node = _node_paths()
    missing = client - node
    assert not missing, f"coordinator paths not on node: {sorted(missing)}"


def test_known_missing_is_empty_or_documented():
    """V23-42: these should all have node counterparts now."""
    client = _client_paths()
    found = client & _node_paths()
    assert KNOWN_MISSING & found == set(), f"formerly missing paths now resolve: {sorted(KNOWN_MISSING & found)}"
