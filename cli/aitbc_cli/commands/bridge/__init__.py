"""Bridge commands for AITBC CLI.

v0.7.0 §B3: Replaced the broken ``start``/``status``/``stop`` commands (which
called non-existent ``/rpc/bridge/start`` etc. and fell back to simulated data)
with actual bridge RPC commands using ``aitbc.bridge.BridgeClient``.

v0.7.1 §B7: Added ``security-status`` and ``register-validator`` subcommands
for bridge multi-sig management.

The command surface lives in the sibling submodules (``_transfers``,
``_service``, ``_proofs``, ``_ledger``) which register on the ``bridge`` group
from ``_group``; shared helpers live in ``_helpers``. This ``__init__``
re-exports the group, every command, and the helper names tests patch or call
directly so ``aitbc_cli.commands.bridge.<name>`` keeps resolving exactly as it
did when the package was a single module.
"""

# Re-exported module attributes: tests patch ``bridge_mod.httpx.get`` and
# ``bridge_mod.subprocess.run`` — both resolve to the shared module objects.
import httpx
import subprocess

from ._group import bridge
from ._helpers import (
    _EVENT_BRIDGE_URL,
    _OPS_ERRORS,
    _SERVICE_NAME,
    _canonical_hash,
    _derive_address,
    _event_bridge_status,
    _fetch_block_header,
    _get_bridge_client,
    _load_private_key,
    _resolve_bridge_repo_root,
    _resolve_node_chain_id,
    _sign_dict,
    _sign_header,
    _sign_hash,
    _systemctl,
)
from ._ledger import deposits
from ._proofs import attest, get_proof, ingest_header, sign_proof, store_header
from ._service import health, oracle_status, register_validator, security_status, start, stop
from ._transfers import balance, confirm, lock, pending, status, unlock
