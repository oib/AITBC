## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.3 Suggestions

## Gaps
- Changelog lacks reference files for governance and pool hub interactions.
- Cross-chain governance relies on bridge maturity not yet verified (v0.7.0-v0.7.2).
- No validation that `PoolHub` can actually expose parameters that governance is meant to change. Note: PoolHub app does not exist yet (confirmed in v0.6.7 investigation) — it will be created in v0.6.7.

## Recommendations
- Verify current PoolHub parameter surface after v0.6.7 ships, before designing governance proposals.
- Start with same-chain governance; add bridge-based cross-chain voting only after v0.7.2 is operational.
- Require an internal review pass (architecture + security) before coding starts.
- v0.7.2 is now rescoped to in-process verification (no external oracle). Cross-chain governance proposals must use the in-process verification path.
