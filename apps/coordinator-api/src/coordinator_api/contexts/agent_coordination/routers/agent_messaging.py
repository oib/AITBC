"""Agent messaging router — intentionally unimplemented.

The mock endpoints that lived here were removed: behind a ``settings.debug``
gate they fabricated an agent registry and message bus under ``/v1/agent/*``
(``broadcast`` returned ``sent_count: 2`` unconditionally, ``heartbeat`` was a
no-op success, ``stats`` reported ``total_messages: 0``). The router stays
mounted at ``/v1`` so the module/import contract is stable, but it registers
no routes — every ``/v1/agent/*`` request returns 404 in every environment.

Real agent messaging already exists on-chain: the messaging contract served
via ``/rpc/contracts/messaging/*`` (topics, posts, reads — the surface the CLI
``aitbc messaging`` commands use). Agent identity and attestation live in the
agent-comm service. If an off-chain REST shim over that contract is ever
wanted, build it here against the real contract — not against in-memory
dicts — and gate mutating endpoints on ``verify_rpc_api_key`` from day one.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/agent", tags=["agent"])
