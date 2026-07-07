# governance

Governance — proposals, voting, DAO operations, and policy management.

## Domain Models

- None (stub)

## Routes

- POST /profiles
- POST /profiles/{profile_id}/delegate
- POST /proposals
- POST /proposals/{proposal_id}/vote
- POST /proposals/{proposal_id}/process
- POST /proposals/{proposal_id}/execute
- POST /analytics/reports
- POST /regional-councils
- GET /regional-councils
- POST /regional-proposals
- POST /regional-proposals/{proposal_id}/vote
- GET /treasury/balance
- POST /treasury/allocate
- GET /treasury/transactions
- POST /staking/pools
- GET /staking/pools
- GET /staking/calculate-rewards
- POST /staking/distribute-rewards/{pool_id}
- GET /analytics/governance
- GET /analytics/regional-health/{region}
- POST /profiles/create
- POST /profiles/delegate
- GET /profiles/{user_id}
- GET /jurisdictions
- GET /compliance/check/{user_address}
- GET /health
- GET /status

## Services

- dao_governance_service.py
- governance_service.py
