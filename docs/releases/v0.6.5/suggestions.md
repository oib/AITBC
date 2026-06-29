## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.5 Suggestions

## Status
**CLAIMS VERIFIED** — All gaps confirmed in codebase. v0.5.16 Bug 15/16 fixes confirmed in place.

## Verified Gaps

1. **Agent registration lacks chain_id/island_id**: `AgentRegistrationRequest` (`apps/agent-coordinator/src/app/models.py:6`) has no chain_id or island_id fields. `AgentInfo` (`apps/agent-coordinator/src/app/routing/agent_discovery.py:53`) also lacks these fields. Agent discovery (`agents.py:52`) filters by agent_type and capabilities only — cannot filter by chain.

2. **Task submission lacks chain_id and payment**: `TaskSubmission` (`apps/agent-coordinator/src/app/models.py:18`) has no chain_id or payment fields. No escrow mechanism for task payment.

3. **coin_requests chain_id fix already done**: v0.5.16 Bug 16 is FIXED in `agent_stream.py:364-366`. `TransactionService.generate_signed_transaction()` includes chain_id in signed transaction dict (`aitbc/crypto/transaction_service.py:143`). No further work needed on this specific bug.

4. **No blockchain escrow integration**: `coordinator-api` has a `PaymentsService` with escrow fields but it's in-memory only, no blockchain contract integration. The `agent-coordinator` app has no payment escrow at all.

5. **Config gaps**: `BLOCKCHAIN_RPC_URL` is read via `os.getenv()` in `agent_stream.py:361` but is NOT in the `Settings` class in `config.py`. `DEFAULT_CHAIN_ID` and `DEFAULT_ISLAND_ID` do not exist.

6. **Agent TTL hardcoded**: `max_heartbeat_age=120s` is hardcoded in `AgentRegistry.__init__` (`agent_discovery.py:111`). Should be configurable.

## Recommendations (incorporated into change.log)

- **Add chain_id/island_id to agent models**: Update `AgentRegistrationRequest`, `AgentInfo`, and agent discovery filters.
- **Add chain_id/payment to task models**: Update `TaskSubmission` with chain_id and payment fields. Implement escrow lock/release.
- **Add config fields**: `BLOCKCHAIN_RPC_URL`, `DEFAULT_CHAIN_ID`, `DEFAULT_ISLAND_ID`, `TASK_PAYMENT_ESCROW_ENABLED`, `AGENT_HEARTBEAT_TIMEOUT_SECONDS`.
- **Structured auth**: The agent-coordinator uses `@rate_limit` decorators but no JWT auth on most endpoints. Consider adding auth for task submission and payment endpoints.
- **Observability**: Add request/response logging and error metrics starting here so all future releases inherit it.
- **App clarification**: v0.6.5 targets `apps/agent-coordinator/` (flat router structure, ~10K lines). The separate `apps/coordinator-api/` (bounded contexts) is NOT the target.

## Prerequisites Verified

- ✅ v0.5.16 Bug 15 (port 8202 → 8006): Fixed in `agent_stream.py:361`
- ✅ v0.5.16 Bug 16 (drops chain_id): Fixed in `agent_stream.py:364-366`
- ✅ TransactionService chain_id: Included in signed tx dict (`transaction_service.py:143`)
- ✅ v0.6.3 (Multi-Island Node Support): Complete
- ✅ v0.6.4 (Multi-Chain Per Island): In progress (Agent A complete, Agent B pending)
