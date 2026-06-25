## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.1 Suggestions

## Status
**No code verification needed** — Suggestions are architectural/process recommendations. v0.6.0 prerequisite is now properly scoped (DB/network/caching only).

## Gaps
- Changelog requires `v0.6.0` prerequisite — v0.6.0 is now scoped to DB/network/caching only, providing a stable base.
- No prototype of deterministic scheduling or conflict resolution exists in the codebase.
- Tests for consensus correctness (all validators produce identical state roots) are not described in implementation terms.

## Recommendations
- Create a small executor prototype before modifying `state_transition.py` or `poa.py`.
- Keep a feature flag path so parallel validation can be toggled off if consensus diverges.
- Pair Agent A and Agent B explicitly on this release because both touch consensus-critical code.
- The block/tx processing targets moved from v0.6.0 (block import >500/sec, tx validation <10ms) are now in this release — see change.log performance targets.
