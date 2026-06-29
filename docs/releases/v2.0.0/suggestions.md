## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v2.0.0 Suggestions

## Status
**CLAIMS CONFIRMED** — Futures/options/margin confirmed copy-pasted from DEX template. Feature re-evaluation required. Vision release — not fit until after v1.0.0 (production readiness).

## Confirmed Gaps (verified in /opt/aitbc)
1. **Futures/options/margin copy-pasted**: v2.0.0 changelog (lines 26-35) explicitly states "Nobody trades futures contracts on GPU rental", "zero code for futures, options, margin, expiry, strike prices, or leverage". Actual `TradeType` enum is `AI_POWER`, `COMPUTE_RESOURCES`, `DATA_SERVICES`, `MODEL_SERVICES`, `INFERENCE_TASKS`, `TRAINING_TASKS`.
2. **No decision framework**: 11 deferred features need individual DROP/RE-SCOPE/RE-SCHEDULE decisions.
3. **Over-engineering claims**: Adaptive gossip fanout, sparse Merkle trees need quantitative justification against actual scale.

## Recommendations
- **DROP** futures, options, and margin trading — confirmed not matching AITBC's compute marketplace domain.
- Formally close each of the 11 deferred features with a one-sentence decision: DROP, RE-SCOPE, or RE-SCHEDULE.
- If all features are dropped or re-scoped, remove v2.0.0 from the roadmap and fold any re-scoped features into their natural releases.
- Keep re-evaluation conclusions in this change.log rather than a separate document.
