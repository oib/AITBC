# reputation

Reputation system — scoring, history, and reputation services.

## Domain Models

- None (stub)

## Routes

- GET /profile/{agent_id}
- POST /profile/{agent_id}
- POST /feedback/{agent_id}
- POST /job-completion
- GET /trust-score/{agent_id}
- GET /leaderboard
- GET /metrics
- GET /feedback/{agent_id}
- GET /events/{agent_id}
- PUT /profile/{agent_id}/specialization
- PUT /profile/{agent_id}/region
- GET /{agent_id}/cross-chain
- POST /{agent_id}/cross-chain/sync
- GET /cross-chain/leaderboard
- POST /cross-chain/events
- GET /cross-chain/analytics

## Services

- reputation_service.py
