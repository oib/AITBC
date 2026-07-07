# rewards

Rewards — distribution, claiming, and reward program management.

## Domain Models

- None (stub)

## Routes

- GET /profile
- GET /profile/{agent_id}
- POST /profile/{agent_id}
- POST /calculate-and-distribute
- GET /tier-progress/{agent_id}
- POST /batch-process
- GET /analytics
- GET /leaderboard
- GET /tiers
- GET /milestones/{agent_id}
- GET /distributions/{agent_id}
- POST /simulate-reward

## Services

- reward_service.py
