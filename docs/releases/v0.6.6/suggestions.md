## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.6 Suggestions

## Status
**CLAIMS CONFIRMED + UPDATED** — All claims verified against current codebase. Several v0.5.16 bugs already fixed. New issues discovered (schema mismatches, stale port, missing config).

## Confirmed Gaps (verified in /opt/aitbc — 2026-06-29 subagent investigation)

1. **GPU service chain_id defaults to empty string**: `apps/gpu/src/gpu_service/main.py:280` — `chain_id = transaction_data.get("chain_id") or os.getenv("CHAIN_ID", "")`. The field IS present (v0.5.16 fix applied), but defaults to `""` which is invalid for multi-chain. **Fix**: default to `settings.default_chain_id` ("ait-hub").

2. **Marketplace BLOCKCHAIN_RPC_URL defaults to stale port 8006**: `apps/marketplace/src/marketplace_service/main.py:19` and `services/marketplace_service.py:208` — both use `os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8006")`. The correct port is 8202 (per `apps/blockchain-node/src/aitbc/config.py:89`). **Fix**: add Settings class with `blockchain_rpc_url: str = "http://localhost:8202"`.

3. **Marketplace direct SQLite queries (v0.5.16 Bugs 17-18)**: ✅ **ALREADY FIXED** — `marketplace_service.py:206-276` now uses RPC via httpx to `BLOCKCHAIN_RPC_URL/rpc/transactions`. No direct database access found.

4. **No cross-service contract for offer state transitions**: No FSM defined for `available` → `reserved` → `in_use`. Status is a simple string field in `MarketplaceOffer.status`, `GPURegistry.status`, and `GPUListing.status`. No transition validation anywhere. **Fix**: Agent A creates `OfferFSM` in `aitbc/marketplace/offer_fsm.py`.

5. **Edge service schema mismatch (NEW — not in original suggestions)**:
   - `apps/edge/src/aitbc_edge/schemas/gpu.py:11-36` defines `GPUListing` with fields `listing_id`, `island_id`, `miner_id`, `gpu_type`.
   - `apps/edge/src/aitbc_edge/services/gpu_service.py:25-34` creates `GPUListing(gpu_id=..., model=..., ...)` — fields that don't exist in the schema.
   - This causes runtime errors. The service code also uses `# type: ignore[attr-defined]` to suppress type errors.
   - **Fix**: update schema to include `gpu_id` and `model` fields, or update service code to use the correct field names.

6. **Edge service ComputeResult schema mismatch (NEW)**:
   - `apps/edge/src/aitbc_edge/schemas/serve.py` defines `result` field.
   - `apps/edge/src/aitbc_edge/services/serve_service.py:111` references `output_data` field.
   - **Fix**: align schema and service code.

7. **Edge service has no payment verification (NEW)**:
   - `apps/edge/src/aitbc_edge/routers/serve.py:27-33` — `submit_compute_request` accepts requests without any payment check.
   - No payment, escrow, or authentication verification before serving.
   - **Fix**: add payment verification (feature-flagged) using `BlockchainRPCClient.verify_escrow()`.

8. **Edge service has no marketplace advertising (NEW)**:
   - Edge only reads GPU profiles from GPU service — does not advertise its own capabilities to the marketplace.
   - **Fix**: add `advertise_to_marketplace()` method.

9. **Edge service has no coordinator health reporting (NEW)**:
   - Edge has local health endpoints (`/health`, `/ready`) but does not report to agent-coordinator.
   - **Fix**: add periodic heartbeat to agent-coordinator.

10. **Edge service has unused JWT config (NEW)**:
    - `apps/edge/src/aitbc_edge/config.py:38-40` — `jwt_secret_key`, `jwt_algorithm`, `jwt_expiration_hours` defined but never used.
    - **Fix**: remove (defer JWT to v0.7.1 Bridge Security).

11. **Marketplace has no Settings class (NEW)**:
    - Uses `os.getenv()` directly throughout `main.py` and `services/marketplace_service.py`.
    - Does not subclass `ServiceSettings` from `aitbc_shared.core.config` (project convention).
    - **Fix**: create `config.py` with `Settings(BaseSettings)` class.

12. **GPU service has no Settings class (NEW)**:
    - Same issue as marketplace — uses `os.getenv()` directly.
    - **Fix**: create `config.py` with `Settings(BaseSettings)` class.

13. **Marketplace matching is basic (NEW)**:
    - `matching_service.py:21-98` — `find_best_match()` with simple scoring, no price-time priority, no agent-coordinator integration.
    - **Fix**: implement price-time priority + `match_and_assign()` that submits task to agent-coordinator.

## Already Fixed (verified — no work needed)

1. ✅ **Marketplace direct SQLite** (v0.5.16 Bugs 17-18) — now uses RPC via httpx
2. ✅ **GPU service includes chain_id in tx** (v0.5.16 fix) — field present, just needs default fix
3. ✅ **Blockchain GPU RPC endpoints** — `/gpus`, `/gpu/register`, `/gpu/info`, `/gpu/allocate` all chain_id-aware
4. ✅ **TransactionRequest accepts chain_id** — validates against supported chains
5. ✅ **Edge config uses ServiceSettings** — already subclasses shared config with port 8202
6. ✅ **GPU service BLOCKCHAIN_RPC_URL** — already defaults to 8202 (correct)

## Recommendations
- Ship v0.6.5 first (PaymentEscrow needed for edge payment verification). ✅ Done.
- Create OfferFSM before wiring it into services (Agent A Phase 1 → Agent B Phase 3).
- Fix edge schema mismatches first (B5) — they are already-broken code causing runtime errors.
- Feature-flag payment verification (default off) to avoid breaking existing edge service users.
- Remove unused JWT config rather than implementing it — JWT auth belongs in v0.7.1 (Bridge Security).
- Require at least one end-to-end chain (offer registered → matched → payment → delivery) to be automated in B7 tests.
