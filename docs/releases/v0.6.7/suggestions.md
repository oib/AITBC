## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.7 Suggestions

## Status
**CLAIMS CONFIRMED** — Pool-hub app does not exist yet. No reward policy constants found.

## Confirmed Gaps (verified in /opt/aitbc)
1. **Pool-hub app does not exist**: No `pool-hub` directory in `apps/`. This release creates it from scratch.
2. **No reward policy constants**: `REWARD_PER_SHARE`, halving interval — none exist in any Python file. Only in documentation.
3. **No BlockchainClient in pool-hub**: Cannot verify — app doesn't exist yet.

## Recommendations
- Create `apps/pool-hub/` with `BlockchainClient` dependency, `chain_id` as first-class parameter.
- Connect to blockchain-node RPC on port 8006 (not 8202 — see v0.5.16 Bug 15).
- Define reward policy constants in `aitbc/constants.py` or dedicated `aitbc/rewards/policy.py`.
- Add eligibility checks: no duplicate reward payouts within the same reward epoch.
- Surface reward distribution as observable events (logs/metrics) from the first implementation.
