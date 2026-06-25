## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.6 Suggestions

## Status
**CLAIMS CONFIRMED** — GPU service missing chain_id confirmed. Marketplace direct SQLite already tracked in v0.5.16.

## Confirmed Gaps (verified in /opt/aitbc)
1. **GPU service submits transactions without chain_id**: `apps/gpu/src/gpu_service/main.py` lines 272-291 — `blockchain_tx` dict has no `chain_id` field. Same class of bug as v0.5.16 Bug 1 and Bug 16.
2. **Marketplace direct SQLite queries**: Already tracked in v0.5.16 (Bugs 17-18). v0.6.6 should verify the fix is in place.
3. **No cross-service contract for offer state transitions**: No FSM defined for `available` → `reserved` → `in_use`.

## Recommendations
- Ship v0.5.16 first and verify GPU service against it before starting v0.6.6.
- Replace direct SQLite queries with blockchain RPC calls before any matching/feature work.
- Define a strict offer FSM and reject state transitions that bypass it.
- Require at least one end-to-end chain (offer registered → matched → payment → delivery) to be automated before expanding scope.
