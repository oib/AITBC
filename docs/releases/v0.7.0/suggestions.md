## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.0 Suggestions

## Status
**CLAIM CONFIRMED** — `aitbc-bridge-service` does not exist. Migration guide corrected in change.log.

## Confirmed Gaps (verified in /opt/aitbc)
1. **Bridge service boundary unclear**: Changelog referenced `aitbc-bridge-service` (non-existent). Bridge code is in:
   - `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py`
   - `apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py`
   - `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py`
   - `apps/coordinator-api/src/app/contexts/cross_chain/services/cross_chain/bridge.py`
   - `apps/bridge-monitor/` (monitoring only)
2. **v0.5.16 prerequisite**: Bridge is still forgeable until v0.5.16 ships.

## Recommendations
- Bridge RPC remains hosted in `blockchain-node`. No standalone bridge service in this release.
- Audit bridge-active files after v0.5.16 ships, then re-align changelog with current module names.
- Add explicit upgrade cutover notes from old bridge endpoints to v0.7.0 naming.
