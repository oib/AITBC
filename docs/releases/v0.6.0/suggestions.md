## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.0 Suggestions

## Status
**RESCOPED** — Performance targets that depend on parallel processing (block import >500/sec, tx validation <10ms, mempool >5,000/sec) have been moved to v0.6.1. v0.6.0 is now scoped to DB/network/caching only. See change.log for the updated plan.

## Resolved Issues
- ~~Remove or defer performance targets that depend on v0.6.1 (parallel validation)~~ → Done. Block/tx processing targets moved to v0.6.1.
- ~~Changelog is vague: no concrete code targets, no file paths~~ → Scope clarification added with file/line references (poa.py lines 239-327, merkle_patricia_trie.py lines 402-419).

## Gaps
- Still missing: how new indexes are defined (Alembic vs `create_all`) — need to specify migration approach.
- Still missing: Redis/Memcached bootstrap and configuration strategy.
- Still missing: test strategy for caching behavior (cache invalidation, TTL, per-chain cache keys).
- No baseline performance measurements exist — need to benchmark current DB/network performance before optimizing.

## Recommendations
- Add precise code touchpoints before starting: database files (`aitbc/database/`), caching markers, network I/O layers (`aitbc/network/`).
- Define a maintenance plan for cache invalidation per chain (cache keys must include `chain_id`).
- Benchmark current performance first: measure DB query latency, network transfer times, block import DB write overhead.
- Specify whether caching uses in-process memory, Redis, or both — and the cache invalidation strategy for each.
- Use Alembic migrations for new indexes (per AGENTS.md conventions: `if_not_exists=True`).
