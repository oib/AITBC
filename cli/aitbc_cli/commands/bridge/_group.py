"""The ``aitbc bridge`` click group plus the package-attribute seams.

Kept in a leaf module so command submodules can register against it without
importing this package's ``__init__`` — ``__init__`` imports the submodules to
attach their commands, and a submodule importing the group back from the
package would close an import cycle (same layout as ``commands/market``).

The two ``_*`` forwarders preserve the pre-split monkeypatch seams: tests do
``mock.patch.object(aitbc_cli.commands.bridge, "_get_bridge_client", ...)``
and the command callbacks resolve the name through this package at call
time, so the patch lands. The real implementations live in ``_helpers`` and
are re-exported by ``__init__``.
"""

import click

from aitbc.bridge import BridgeClient


def _get_bridge_client(rpc_url: str) -> BridgeClient:
    """Forward to the package-level ``_get_bridge_client`` (test patch seam)."""
    from aitbc_cli.commands.bridge import _get_bridge_client as _impl

    return _impl(rpc_url)


def _resolve_node_chain_id(rpc_url: str) -> str:
    """Forward to the package-level ``_resolve_node_chain_id`` (test patch seam)."""
    from aitbc_cli.commands.bridge import _resolve_node_chain_id as _impl

    return _impl(rpc_url)


@click.group(
    epilog="""Examples:

  aitbc bridge status

  aitbc bridge lock --target-chain ait-side --sender 0x... --recipient 0x... --amount 100"""
)
def bridge():
    """Manage cross-chain bridge transfers, validators, proofs, and block headers."""
    pass
