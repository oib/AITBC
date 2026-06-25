## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.4 Suggestions

## Status
**CLAIMS VERIFIED** — Dead code confirmed, join_island caller inventory complete (8 call sites).

## Confirmed Gaps (verified in /opt/aitbc)
1. **MultiChainManager**: `apps/blockchain-node/src/aitbc_chain/network/multi_chain_manager.py` line 56 — defined but never imported in `main.py`. Confirmed dead code.
2. **MultiValidatorPoA**: `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` line 33 — used only in tests/scripts, NOT in production code.
3. **PBFT**: `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` line 48 — used only in test scripts, NOT in production code.
4. **join_island() callers**: 8 call sites identified (see change.log for full list). All use old single-`chain_id` signature.

## Recommendations
- Grep for `join_island` and `IslandMembership` usages across repo first; update all 8 signatures in one atomic refactor.
- Add startup sequencing: one chain at a time with configurable retry/backoff.
- Activate only `MultiChainManager`, not `PBFT`/`MultiValidatorPoA`. Leave them in clearly commented THRESHOLD state so they don't accidentally run. They require separate security review.
- No fallback behavior if dynamic chain start fails during node boot — add retry logic with exponential backoff.
