# AGENTS.md — AITBC Project Rules & Agent Plans

This file is the source of truth for project conventions, verification commands, and per-agent task plans. Agent-specific plans live at `docs/releases/<version>/AGENTS.md`; this root file holds the stable conventions and the **current** in-flight plan.

## Project Layout

- `aitbc/` — shared core library (types, config, db, logging, queues, crypto, network, agent_bridge, agent_protocols, agent_registry, etc.)
- `apps/` — microservices (coordinator-api, blockchain-node, exchange, wallet, marketplace, miner, edge, gpu, governance, …)
- `cli/` — `aitbc_cli` command-line tool
- `packages/py/` — publishable Python packages
- `tests/` — `unit/`, `integration/`, `e2e/`, `coordinator/`
- `scripts/` — ops, deployment, monitoring, migration, security
- `docs/releases/<version>/` — per-release changelogs and agent task assignment

## Verification Commands

```bash
# Type check (shared core)
./venv/bin/python -m mypy --show-error-codes aitbc/

# Lint (whole repo)
./venv/bin/python -m ruff check .

# Tests (note: requires pytest-rerunfailures + pytest-asyncio; add -o addopts="" to bypass if missing)
./venv/bin/python -m pytest tests/unit -q
./venv/bin/python -m pytest tests/integration -q

# Coordinator-api tests (needs PYTHONPATH=src and aitbc_shared installed)
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

## Conventions

- **Python 3.13**, line length 127 (black + ruff), `target-version = "py313"`.
- **SQLModel** for ORM models in `apps/coordinator-api/src/app/domain/`. Add `index=True` on columns filtered/ordered at the SQL layer. Composite indexes via `sqlalchemy.Index(...)` in `__table_args__` tuple.
- **Config**: `pydantic_settings.BaseSettings`. Shared base lives in `apps/shared-core/src/app/core/config.py` (`ServiceSettings`, `DatabaseConfig`). New services should subclass these rather than redefining `DatabaseConfig`.
- **Logging**: `aitbc.aitbc_logging` is canonical. `aitbc/log_utils/logging.py` is a thin re-export shim — do not duplicate logging setup.
- **Constants**: `aitbc/constants.py` sources `REPO_DIR` from `AITBC_REPO_DIR` env var (defaults to `/opt/aitbc`).
- **DB init**: services call `SQLModel.metadata.create_all` (or `Base.metadata.create_all`). `create_all` only adds indexes to fresh DBs; for existing DBs add an Alembic migration under `apps/coordinator-api/alembic/versions/` using `if_not_exists=True`.
- **Commit style**: `type(scope): subject` — see `git log --oneline`. Include `Generated with [Devin]` trailer + Co-Authored-By when committing via Devin.
- **Do not** edit files outside your agent's ownership without coordinating (see conflict boundaries in the release plan).

## Agent Roles (stable across releases)

| Agent | Domain | Owns |
|-------|--------|------|
| **Agent A** | Type safety & shared core (`aitbc/`) | All of `aitbc/` except `aitbc/constants.py`, `aitbc/log_utils/` |
| **Agent B** | Bug fixes, infrastructure & apps | `aitbc/constants.py`, `aitbc/log_utils/`, all `apps/`, `cli/`, systemd config |

**Conflict boundary**: both agents must not edit the same file. Shared files (`aitbc/database/replica.py`, `aitbc/network/circuit_breaker.py`, agent bridge imports) are sequenced — see the Coordination Protocol below.

### Coordination Protocol

When both agents need to touch shared files or adjacent code paths, follow this protocol:

1. **Declare intent**: Before starting work on a shared file, the agent posts in the release's `AGENTS.md` (under a "Coordination" section) which file(s) they intend to modify and when.
2. **Sequence, don't parallelize**: Shared files are edited sequentially, not concurrently. Agent A goes first for `aitbc/` shared files; Agent B goes first for `apps/` shared files.
3. **Lock files during editing**: The agent currently editing a shared file adds a `# WIP: Agent X` comment at the top of the file while editing. The other agent waits until the comment is removed.
4. **Shared files list** (must be sequenced):
   - `aitbc/database/replica.py` — both agents touch DB replica logic
   - `aitbc/network/circuit_breaker.py` — both agents touch circuit breaker
   - `aitbc/agent_bridge/` — Agent A owns types, Agent B owns implementations
   - `apps/blockchain-node/src/aitbc_chain/rpc/router.py` — Agent B owns, but Agent A may touch for type fixes
   - `apps/blockchain-node/src/aitbc_chain/sync.py` — Agent B owns, but shared with network layer
5. **Conflict resolution**: If both agents edit the same file despite the protocol, the agent whose domain owns the file wins. The other agent rebases.

---

## Completed Releases

All prior release plans are complete. Details are in the respective changelogs:

- **v0.5.12** — Duplication elimination & large-file decomposition: <ref_file file="/opt/aitbc/docs/releases/v0.5.12/change.log" />
- **v0.5.13** — coordinator-api bounded context (P1–P4, T1–T3): <ref_file file="/opt/aitbc/docs/releases/v0.5.13/change.log" />
- **v0.5.14** — Cross-context dependency elimination (X1–X9, L1–L19): <ref_file file="/opt/aitbc/docs/releases/v0.5.14/change.log" />
- **v0.5.15** — Flat-to-context migration + test suite repair (P1–P7): <ref_file file="/opt/aitbc/docs/releases/v0.5.15/change.log" />
- **v0.5.16** — Security Hardening & Multi-Chain Preparation (18 bugs fixed + signing-scheme regression fix + key model migration to secp256k1): <ref_file file="/opt/aitbc/docs/releases/v0.5.16/change.log" />
- **v0.5.17** — Test Infrastructure (multi-chain fixtures, multi-node harness, stub test conversion, bridge test suite): <ref_file file="/opt/aitbc/docs/releases/v0.5.17/change.log" />
- **v0.6.5** — Agent Coordination Service (chain_id/island_id awareness, PaymentEscrow, chain-aware task distribution): <ref_file file="/opt/aitbc/docs/releases/v0.6.5/change.log" />

### Security Audit & Status

- **Bridge Security Audit** (Bug #3 + Bug #4 fixed, regression tests passing): <ref_file file="/opt/aitbc/docs/releases/AUDIT.md" />
- **Release Status Overview** (all releases, config defaults, audit summary): <ref_file file="/opt/aitbc/docs/releases/STATUS.md" />

## Planned Releases

The release roadmap is split into two interleaved tracks: **infrastructure** (blockchain, bridge, sync, settlement) and **product** (agent coordination, compute marketplace, pool hub, governance). Product releases are interleaved after the multi-chain foundation is complete. Version numbers are monotonic — each release has a higher version than the one before it.

### Immediate Bugfix (Patch)
- **v0.5.18** — Test Suite Repair (green the `apps/blockchain-node/tests/` suite: 64 failed + 8 errors, all pre-existing; prevent CI hangs; quarantine Redis/Postgres tests; add the suite to `testpaths`). Establishes the green baseline v0.6.0 needs: <ref_file file="/opt/aitbc/docs/releases/v0.5.18/change.log" /> ✅ complete
- **v0.5.19** — Tech Debt Cleanup (cross-context import refactor, dead pricing models, fakeredis): <ref_file file="/opt/aitbc/docs/releases/v0.5.19/change.log" /> ✅ complete

### Infrastructure Track (multi-chain foundation)
- **v0.6.0** — Database & Network Optimization (query indexing, connection pooling, N+1 elimination, batch writes, block header caching, network compression): <ref_file file="/opt/aitbc/docs/releases/v0.6.0/change.log" /> ✅ complete
- **v0.6.1** — Parallel Processing (parallel tx validation via dependency analysis, deterministic scheduling, pure state transitions): <ref_file file="/opt/aitbc/docs/releases/v0.6.1/change.log" /> ✅ complete
- **v0.6.2** — Sync & Gossip Optimization (gossip protocol versioning, message prioritization, compact blocks, parallel sync from multiple peers, delta sync): <ref_file file="/opt/aitbc/docs/releases/v0.6.2/change.log" /> 🚧 planned
- **v0.6.3** — Multi-Island Node Support: <ref_file file="/opt/aitbc/docs/releases/v0.6.3/change.log" /> 🚧 planned
- **v0.6.4** — Multi-Chain Per Island: <ref_file file="/opt/aitbc/docs/releases/v0.6.4/change.log" /> 🚧 planned

### Product Track (interleaved after v0.6.4)
- **v0.6.5** — Agent Coordination Service: <ref_file file="/opt/aitbc/docs/releases/v0.6.5/change.log" /> ✅ complete
- **v0.6.6** — Compute Marketplace: <ref_file file="/opt/aitbc/docs/releases/v0.6.6/change.log" /> 🚧 planned
- **v0.6.7** — Pool Hub & Mining: <ref_file file="/opt/aitbc/docs/releases/v0.6.7/change.log" /> 🚧 planned

### Infrastructure + Product (bridge + governance)
- **v0.7.0** — Bridge Basics: <ref_file file="/opt/aitbc/docs/releases/v0.7.0/change.log" /> ✅ complete
- **v0.7.1** — Bridge Security: <ref_file file="/opt/aitbc/docs/releases/v0.7.1/change.log" /> ✅ complete
- **v0.7.2** — Bridge Verification (In-Process Crypto): <ref_file file="/opt/aitbc/docs/releases/v0.7.2/change.log" /> ✅ complete
- **v0.7.3** — Governance: <ref_file file="/opt/aitbc/docs/releases/v0.7.3/change.log" /> ✅ complete
- **v0.7.4** — Deferred v0.7.x Items (External Oracle, Cross-Chain Governance, Parameter Automation, Emergency Proposals, Coordinator-API Bridge): <ref_file file="/opt/aitbc/docs/releases/v0.7.4/change.log" /> ✅ complete
- **v0.7.5** — Consensus Activation (MultiValidatorPoA + PBFT: fix 6 Critical + 6 High findings from security review, then activate): <ref_file file="/opt/aitbc/docs/releases/v0.7.4/security-review-multivalidator-poa.md" /> ⚠️ code complete, enabled for homebrew testing in v0.10.0 (no external security audit — poor homebrew project)

### Infrastructure Track (trading + settlement)
- **v0.8.0** — Inter-Chain Trading Basics: <ref_file file="/opt/aitbc/docs/releases/v0.8.0/change.log" /> ✅ complete
- **v0.8.1** — Cross-Chain Offer Sync (polling-based): <ref_file file="/opt/aitbc/docs/releases/v0.8.1/change.log" /> ✅ complete
- **v0.8.2** — Advanced Offer Sync (subscription, real-time, search index): <ref_file file="/opt/aitbc/docs/releases/v0.8.2/change.log" /> ✅ complete
- **v0.9.0** — Atomic Cross-Chain Settlement: <ref_file file="/opt/aitbc/docs/releases/v0.9.0/change.log" /> 🚧 code complete (A1-A6 ✅, B1-B12 ✅; all tests passing; external security audit pending)

### Patch Releases
- **v0.10.0** — Runtime Bug Fixes, Service Modernization & Feature Activation (consensus state root fix, SharedHttpClient classmethod fix, DB column migration, session_scope chain_id fix, PyCUDA log noise, exchange module entry point, miner logging, enable multi-validator consensus + atomic settlement for homebrew testing): <ref_file file="/opt/aitbc/docs/releases/v0.10.0/change.log" /> ✅ complete
- **v0.10.1** — Gap Fill for v0.6.0–v0.8.2 (20 tasks: CLI endpoint paths, island ID bug, node CLI crash, HTTP RPC compression, P2P→sync wiring, feature flag activation, MultiChainManager init, edge-advertise/registration/health/payment, pool join/leave, mining RPC wired to coordinator, parameter automation, duplicate bridge removal, trading service deploy + gossip integration + lease tracker + polling fallback): <ref_file file="/opt/aitbc/docs/releases/v0.10.1/change.log" /> ✅ complete

### Post-v1 Vision (not fit until after v1.0.0)
- **v2.0.0** — Vision/Questionable Features — Parked for Re-Evaluation: <ref_file file="/opt/aitbc/docs/releases/v2.0.0/change.log" /> 🅿️ parked

### Release Sequence (monotonic)

```
v0.5.16  (security hardening + multi-chain preparation) ✅ complete
  → v0.5.17  (test infrastructure) ✅ complete
  → v0.5.18  (test suite repair — blockchain-node suite green + gated) ✅ complete
  → v0.5.19  (tech debt cleanup — cross-context imports, dead pricing models, fakeredis)
  → v0.6.0 → v0.6.1 → v0.6.2 → v0.6.3 → v0.6.4  (infra: db/network opt ✅, parallel processing ✅, sync, multi-island, multi-chain)
  → v0.6.5 → v0.6.6 → v0.6.7                      (product: agents ✅, marketplace, pool hub)
  → v0.7.0 → v0.7.1 → v0.7.2 → v0.7.3 → v0.7.4 → v0.7.5  (infra+product: bridge basics, bridge security, bridge verification, governance, deferred v0.7.x items, consensus activation)
  → v0.8.0 → v0.8.1 → v0.8.2 → v0.9.0               (infra: trading basics, offer sync polling, offer sync subscription, atomic settlement)
  → v0.10.0                                         (patch: runtime bug fixes — consensus state root, SharedHttpClient, DB migration, service modernization) ✅
  → v0.10.1                                         (gap fill: 20 tasks fixing v0.6.0–v0.8.2 unwired/deployed/broken features) ✅
  → v1.0.0                                          (production readiness)
  → v2.0.0                                          (vision — questionable features, parked for re-evaluation)
```

### Scope Correction Notes

- **v0.6.0 vs v0.6.1 split**: v0.6.0 was originally bundled with parallel block/tx processing targets (block import >500/sec, tx validation <10ms). These require fundamental architectural changes (dependency analysis, deterministic scheduling, conflict resolution) that caching/DB optimization cannot achieve. The sequential tx loop in `poa.py` (lines 239-327) and full state root recomputation in `merkle_patricia_trie.py` (lines 402-419) are the bottlenecks. v0.6.0 is now scoped to DB/network/caching only; block/tx processing targets moved to v0.6.1 (Parallel Processing). v0.7.0 (Bridge Basics) requires both v0.6.0 AND v0.6.1.

- **v0.7.2 rescope**: The original v0.7.2 plan assumed external oracle infrastructure (`oracle1.aitbc.bubuit.net`, `oracle2.aitbc.bubuit.net`) that does not exist. No oracle client code, light client library, or deployed oracle network are present. v0.7.2 is now rescoped to use **in-process cryptographic verification** with existing Merkle Patricia Trie infrastructure (`merkle_patricia_trie.verify_proof`). External oracle integration is deferred to a future release (v0.8.x or v0.9.x). The trivially forgeable `_validate_proof` in `cross_chain/bridge.py` (lines 244-257) is replaced with Merkle proof + block header signature + finality verification.

- **CLI command gaps**: Release plans referenced CLI commands that don't exist yet. Each affected release's change.log now includes a "🖥️ CLI Commands" section listing the exact commands to implement:
  - v0.6.2: `sync status`
  - v0.6.3: `chain sync-status`, `node island health`, `node island list` (alias)
  - v0.6.4: `chain start`, `chain stop`, `chain list --island`
  - v0.7.1: `bridge security-status`, `bridge register-validator`
  - v0.7.2: `bridge oracle-status`
  - v0.7.4: `governance propagate`, `governance aggregate-votes`, `bridge oracle-status` (real impl), `consensus validators`, `consensus status`
  - v0.8.0: entire `trade` command group (create, list, chains, get, status)
  - v0.8.1: `trade discover`, `trade sync`, `trade sync-status`
  - v0.8.2: `trade watch`, `trade subscription-status`
  - v0.9.0: `trade lock-escrow`, `trade settle`

### Suggestions.md Investigation Results

All 19 `suggestions.md` files across release folders were read, investigated, and incorporated into change.logs. Key findings:

- **v0.5.16**: ~~All 7 original confirmed bugs STILL PRESENT in codebase.~~ **RE-VERIFIED 2026-06-29: ALL 7 FIXED** across v0.5.16–v0.6.7. 5 fully fixed (TransactionRequest chain_id, sync.py chain_id, agent_stream chain_id, marketplace hardcoded DB path, marketplace raw SQL). 1 partially fixed + fenced (bridge `_validate_proof` — proposer-set membership + Merkle proof deferred to v0.7.2, release fenced behind `BRIDGE_RELEASE_ENABLED=false`). 1 was NOT A BUG (agent_stream port 8202 is correct; the original suggestion had the port direction backwards — 8006 is the stale port, 8202 is correct per blockchain-node config.py:89). **UPDATE 2026-06-18: Bridge `_validate_proof` security audit completed — Bug #3 (proposer signature validator-set membership) and Bug #4 (Merkle proof enforcement) fixed with regression tests. See [AUDIT.md](docs/releases/AUDIT.md).**
- **v0.6.3**: All 4 claims confirmed — SubscriptionClient single-hub/chain (`subscription_client.py:23-26`), island manager tasks disabled (`main.py:283-288`), CHAIN_SYNC_SOURCES not implemented, gossip topic not chain-specific (`main.py:146` vs `174`).
- **v0.6.4**: Dead code confirmed — MultiChainManager (`multi_chain_manager.py:56`), MultiValidatorPoA (`multi_validator_poa.py:33`), PBFT (`pbft.py:48`). join_island has 8 call sites inventoried.
- **v0.6.6**: GPU service submits transactions without chain_id (`gpu_service/main.py:272-291`). Marketplace direct SQLite already in v0.5.16.
- **v0.6.7**: Pool-hub app does not exist yet. No reward policy constants anywhere in codebase.
- **v0.7.0**: `aitbc-bridge-service` does not exist — migration guide corrected to `aitbc-blockchain-node`. Bridge code is in blockchain-node.
- **v0.7.1**: No `threat_model.md` exists. Security audit not sequenced — must freeze API first, then audit.
- **v0.7.2**: Rescoped from external oracle to in-process verification (oracle endpoints don't exist).
- **v0.8.0**: InterChainTrade schema not defined (no SQLModel). Dispute resolution not scoped.
- **v0.8.1**: IslandManager is membership registry only (264 lines, 14 methods, no offer sync).
- **v0.9.0**: **DECISION: HTLC** (not two-phase commit). HTLC has partial implementation, two-phase commit has none. Requires dual security audits.
- **v2.0.0**: Futures/options/margin confirmed copy-pasted from DEX template. **DROP** decision. (Was v0.10.0 — moved to v2.0.0 as a vision release not fit until after v1.0.0.)
- **v1.0.0**: Rewritten from stale v0.4.26-era plan to match current architecture.

Each release's `change.log` now includes a "Verified Code Targets (from suggestions.md investigation)" subsection with specific file paths and line numbers. Each `suggestions.md` has been updated with verification status.
