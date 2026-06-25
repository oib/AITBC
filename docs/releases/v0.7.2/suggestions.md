## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.2 Suggestions

## Status
**RESCOPED** — The original plan assumed external oracle infrastructure (`oracle1.aitbc.bubuit.net`, `oracle2.aitbc.bubuit.net`) that does not exist. v0.7.2 has been rescoped to use in-process cryptographic verification with existing Merkle Patricia Trie infrastructure. See change.log for the updated plan.

## Resolved Issues
- ~~Oracle endpoints are listed in env examples but not confirmed as existing infrastructure.~~ → Confirmed: oracle endpoints do NOT exist. Rescoped to in-process verification.
- ~~Workflow requires integrating new external libraries (merkle verification, light client) before code is ready.~~ → No external libraries needed. Uses existing `merkle_patricia_trie.verify_proof`.

## Gaps
- Bridge can't move forward safely without v0.7.1 auditor sign-off; this release may end up being theory-only if v0.7.1 slips.
- Validator set epoch tracking needs a persistence strategy (DB schema for validator set history).
- Block header finality tracking requires per-chain block header storage — current code may not store headers from other chains.

## Recommendations
- Do not start coding before v0.7.1 is merged and tested.
- Define the finality threshold per chain (default 6 blocks, configurable).
- Implement validator set cache with DB-backed persistence to survive node restarts.
- Add a `threat_model.md` to the bridge folder before coding starts (carried forward from v0.7.1).
- Future oracle integration (v0.8.x+): pre-decide oracle fallback policy — when do we fall back to in-process verification (1 of N down? X seconds timeout?).
