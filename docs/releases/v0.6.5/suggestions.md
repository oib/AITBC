## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.5 Suggestions

## Gaps
- Agent coordinator (~10K lines) has no release plan beyond a short changelog.
- `coin_requests.py` submits to `/rpc/transaction` without `chain_id` — this is tracked as v0.5.16 Bug 16 (agent-coordinator drops chain_id). Must be fixed in v0.5.16 first.
- No repo-wide audit of auth/decorators on WebSocket handlers.

## Recommendations
- Ship v0.5.16 first and verify `coin_requests.py` / `agent_stream.py` against it before starting v0.6.5.
- Add structured auth handling in one place rather than copying logic.
- Add a small observability layer (request/response logging, error metrics) starting here so all future releases inherit it.
- Note: v0.5.16 Bug 15 fixes the hardcoded port 8202 → 8006 in agent-coordinator. Verify this fix is in place before v0.6.5.
