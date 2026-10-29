# bounty

Bounty system for incentivized tasks and contributions.

## Domain Models

- None (stub)

## Routes

Served by `routers/bounty_flat.py` under `/v1/bounty` (mounted lazily in
main.py). The former `/bounties*` table was stale — that router was deleted
(never mounted; see issue #654 note in `routers/__init__.py`).

- POST /bounty/create
- GET /bounty/list
- GET /bounty/stats
- GET /bounty/health
- GET /bounty/{bounty_id}
- POST /bounty/claim
- POST /bounty/submit
- POST /bounty/verify

## Services

- None (stub)
