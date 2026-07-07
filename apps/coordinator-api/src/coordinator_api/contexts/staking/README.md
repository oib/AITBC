# staking

Staking — delegation, rewards, and staking service operations.

## Domain Models

- None (stub)

## Routes

- POST /stake
- GET /stake/{stake_id}
- GET /stakes
- POST /stake/{stake_id}/add
- POST /stake/{stake_id}/unbond
- POST /stake/{stake_id}/complete
- GET /stake/{stake_id}/rewards
- GET /agents/{agent_wallet}/metrics
- GET /agents/{agent_wallet}/staking-pool
- GET /agents/{agent_wallet}/apy
- POST /agents/{agent_wallet}/performance
- POST /agents/{agent_wallet}/distribute-earnings
- GET /agents/supported
- GET /staking/stats
- GET /staking/leaderboard
- GET /staking/my-positions
- GET /staking/my-rewards
- POST /staking/claim-rewards
- GET /staking/risk-assessment/{agent_wallet}

## Services

- staking_service.py
