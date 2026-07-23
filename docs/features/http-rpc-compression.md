# HTTP RPC Compression

GZip middleware for RPC responses

- **Status**: ✅
- **Release**: v0.10.1
## Implementation Details
- `apps/agent-coordinator/src/agent_app/middleware.py`
- `aitbc/auth/middleware.py` — Custom authentication error.
- `aitbc/marketplace/blockchain_rpc.py` — from __future__ import annotations import logging from typing import Any, cast import httpx logger =...
- `apps/blockchain-node/src/aitbc_chain/network/compression.py` — Check whether network compression is enabled via configuration.
- `apps/coordinator-api/src/coordinator_api/core/middleware.py` — Middleware configuration for Coordinator API.
- `Blockchain Node` exposes `POST /rpc/disputes/file` (operation `file_dispute_route_rpc_disputes_file_post`) — File a new dispute
- `Blockchain Node` exposes `POST /rpc/disputes/evidence` (operation `submit_evidence_route_rpc_disputes_evidence_post`) — Submit evidence for a dispute
- `Blockchain Node` exposes `POST /rpc/disputes/verify-evidence` (operation `verify_evidence_route_rpc_disputes_verify_evidence_post`) — Verify evidence (arbitrator only)
## Examples

- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /bridge` (`request_bridge` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/disputes/file` (`file_dispute_route_rpc_disputes_file_post`) on `Blockchain Node`
- `POST /rpc/disputes/evidence` (`submit_evidence_route_rpc_disputes_evidence_post`) on `Blockchain Node`
- `POST /rpc/disputes/verify-evidence` (`verify_evidence_route_rpc_disputes_verify_evidence_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.10.1`
