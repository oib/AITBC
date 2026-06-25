## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.8.0 Suggestions

## Status
**CLAIMS CONFIRMED** — InterChainTrade schema not defined. Dispute resolution not scoped. CLI breaking change identified.

## Confirmed Gaps (verified in /opt/aitbc)
1. **InterChainTrade schema not defined**: No SQLModel class exists. Related models (TradeRequest, TradeMatch, etc.) in `apps/coordinator-api/src/app/contexts/trading/domain/trading.py` but none named `InterChainTrade`.
2. **Dispute resolution not scoped**: Mentioned but no framework defined.
3. **CLI breaking change**: `aitbc market run` → `aitbc trade create/match/agree` will break existing scripts.

## Recommendations
- Implement and freeze the InterChainTrade database schema before building the matching engine.
- Run marketplace integration tests against actual trading service endpoints early.
- Add migration notes and backward-compatible aliases for CLI changes.
- Consider whether atomic settlement (v0.9.0) can be simplified to manual refund-with-timelock for v1.0.0.
