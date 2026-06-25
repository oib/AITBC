## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.9.0 Suggestions

## Status
**CLAIMS CONFIRMED** — HTLC vs two-phase commit undecided (now DECIDED: HTLC). Highest-risk release. No auditor engaged.

## Confirmed Gaps (verified in /opt/aitbc)
1. **HTLC vs two-phase commit**: Both presented as alternatives, no decision. HTLC has partial implementation (`bridge_enhanced.py` lines 471-529, `CrossChainAtomicSwap.sol` 145 lines). Two-phase commit has NO implementation. **Decision made: HTLC.**
2. **No security audit engagement**: This is the highest-risk release (same class as Wormhole $325M, Ronin $625M, Poly Network $611M hacks).
3. **Chaos testing infrastructure**: Does not exist, must be built from scratch.
4. **Timeout verification**: Cross-chain timeout with different block times and clock skew is underspecified.

## Recommendations
- **HTLC is the chosen approach.** Two-phase commit is dropped.
- Run at least two independent security audits by firms specializing in bridge/cross-chain security.
- Prototype HTLC on a throwaway testnet first. Do not implement on mainnet without 6+ months of chaos testing.
- Define timeout calculation per chain pair: source block time, dest block time, clock skew tolerance, safety margin.
- Consider whether v1.0.0 can ship with non-atomic settlement (manual admin refund) and defer atomic settlement to v1.1.0.
