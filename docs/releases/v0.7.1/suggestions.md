## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.1 Suggestions

## Status
**CLAIMS CONFIRMED** — No threat model exists. Security audit not sequenced.

## Confirmed Gaps (verified in /opt/aitbc)
1. **No threat_model.md**: Does not exist anywhere in the codebase. No dedicated bridge security documentation folder.
2. **Security audit not sequenced**: Required before merge but no auditor named, no threat model versioning.
3. **Consensus-critical code changes**: Bridge transaction flow changes touch consensus-critical code.

## Recommendations
- Freeze bridge RPC API and proof schema first; audit the freeze, not a moving target.
- Create `docs/architecture/bridge-threat-model.md` before coding starts. Cover: attack surfaces, attack vectors, mitigations, residual risk.
- Define the exact scope for the auditor so "security audit" isn't a blocking TBD.
- Sequence: code freeze → threat model → audit → fix findings → merge.
