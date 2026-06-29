## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.5 Suggestions

## Status
**CLAIMS VERIFIED** — All gaps confirmed in codebase. v0.5.16 Bug 15/16 fixes confirmed in place. Port direction corrected: **8202 is the correct blockchain RPC port** (per `apps/blockchain-node/src/aitbc_chain/config.py:89: rpc_bind_port: int = 8202`), **8006 is stale legacy**.

## Verified Gaps

1. **Agent registration lacks chain_id/island_id**: `AgentRegistrationRequest` (`apps/agent-coordinator/src/app/models.py:6`) has no chain_id or island_id fields. `AgentInfo` (`apps/agent-coordinator/src/app/routing/agent_discovery.py:53`) also lacks these fields. Agent discovery (`agents.py:52`) filters by agent_type and capabilities only — cannot filter by chain.

2. **Task submission lacks chain_id and payment**: `TaskSubmission` (`apps/agent-coordinator/src/app/models.py:18`) has no chain_id or payment fields. No escrow mechanism for task payment.

3. **coin_requests chain_id already included**: v0.5.16 Bug 16 is FIXED in `agent_stream.py:364-366`. `TransactionService.generate_signed_transaction()` includes chain_id in signed transaction dict (`aitbc/crypto/transaction_service.py:143`). The POST at `coin_requests.py:65` sends `json=signed_tx` which includes chain_id. **NOT A BUG — no fix needed.**

4. **No blockchain escrow integration**: `coordinator-api` has a `PaymentsService` with escrow fields but it's in-memory only, no blockchain contract integration. The `agent-coordinator` app has no payment escrow at all.

5. **Config gaps**: `BLOCKCHAIN_RPC_URL` is read via `os.getenv()` in `agent_stream.py:361` but is NOT in the `Settings` class in `config.py`. `DEFAULT_CHAIN_ID` and `DEFAULT_ISLAND_ID` do not exist.

6. **Agent TTL hardcoded**: `max_heartbeat_age=120s` is hardcoded in `AgentRegistry.__init__` (`agent_discovery.py:111`). Should be configurable.

7. **Stale port 8006 in agent_stream.py**: `agent_stream.py:361` defaulted to `http://localhost:8006` — **WRONG**. Blockchain node listens on **8202** (`config.py:89`). Fixed to 8202 in v0.6.5.

8. **No WebSocket auth**: `routers/websocket.py` WebSocket endpoints accepted any `agent_id` via Query param with zero authentication. Anyone could impersonate any agent. Fixed in v0.6.5 with API key/JWT token auth via query parameter.

## Recommendations (incorporated into change.log)

- **Add chain_id/island_id to agent models**: Update `AgentRegistrationRequest`, `AgentInfo`, and agent discovery filters.
- **Add chain_id/payment to task models**: Update `TaskSubmission` with chain_id and payment fields. Implement escrow lock/release.
- **Add config fields**: `BLOCKCHAIN_RPC_URL`, `DEFAULT_CHAIN_ID`, `DEFAULT_ISLAND_ID`, `TASK_PAYMENT_ESCROW_ENABLED`, `AGENT_HEARTBEAT_TIMEOUT_SECONDS`.
- **WebSocket auth**: Add API key/JWT token authentication to WebSocket endpoints via query parameter.
- **Observability**: Add request/response logging and error metrics in middleware so all future releases inherit it.
- **App clarification**: v0.6.5 targets `apps/agent-coordinator/` (flat router structure, ~10K lines). The separate `apps/coordinator-api/` (bounded contexts) is NOT the target.

## Port Direction Correction

**IMPORTANT**: The original suggestions had the port direction backwards. The correct port mapping is:

| Port | Status | Evidence |
|------|--------|----------|
| **8202** | ✅ CORRECT — blockchain node RPC port | `apps/blockchain-node/src/aitbc_chain/config.py:89: rpc_bind_port: int = 8202` |
| **8006** | ❌ STALE — legacy port, should not be used | Leftover from old port scheme, never cleaned up |

Files fixed from 8006→8202 in v0.6.5:
- `apps/agent-coordinator/src/app/websocket/agent_stream.py:361` — default RPC URL

Files already correct (8202):
- `apps/gpu/src/gpu_service/main.py:298` — uses 8202 (NOT a bug, despite original suggestion claiming otherwise)
- `apps/agent-coordinator/src/app/config.py` — `blockchain_rpc_url` default 8202 (added in B1)

## Prerequisites Verified

- ✅ v0.5.16 Bug 15 (port): Blockchain node listens on **8202** (`config.py:89`). `agent_stream.py:361` was using stale 8006 — **fixed to 8202 in v0.6.5**.
- ✅ v0.5.16 Bug 16 (drops chain_id): Fixed in `agent_stream.py:364-366`
- ✅ TransactionService chain_id: Included in signed tx dict (`transaction_service.py:143`)
- ✅ coin_requests.py: chain_id included in POST body via signed_tx (NOT a bug)
- ✅ v0.6.3 (Multi-Island Node Support): Complete
- ✅ v0.6.4 (Multi-Chain Per Island): Complete
