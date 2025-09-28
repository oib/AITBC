# AITBC Development Roadmap

This roadmap aggregates high-priority tasks derived from the bootstrap specifications in `docs/bootstrap/` and tracks progress across the monorepo. Update this document as milestones evolve.

## Stage 1 — Core Services (MVP)

- **Coordinator API**
  - ✅ Scaffold FastAPI project (`apps/coordinator-api/src/app/`).
  - ✅ Implement job submission, status, result endpoints.
  - ✅ Add miner registration, heartbeat, poll, result routes.
  - ✅ Wire SQLite persistence for jobs, miners, receipts (historical `JobReceipt` table).
  - ✅ Provide `.env.example`, `pyproject.toml`, and run scripts.

- **Miner Node**
  - ✅ Implement capability probe and control loop (register → heartbeat → fetch jobs).
  - ✅ Build CLI and Python runners with sandboxed work dirs (result reporting stubbed to coordinator).

- **Blockchain Node**
  - ✅ Define SQLModel schema for blocks, transactions, accounts, receipts (`apps/blockchain-node/src/aitbc_chain/models.py`).
  - ✅ Harden schema parity across runtime + storage:
    - Alembic baseline + follow-on migrations in `apps/blockchain-node/migrations/` now track the SQLModel schema (blocks, transactions, receipts, accounts).
    - Added `Relationship` + `ForeignKey` wiring in `apps/blockchain-node/src/aitbc_chain/models.py` for block ↔ transaction ↔ receipt joins.
    - Introduced hex/enum validation hooks via Pydantic validators to ensure hash integrity and safe persistence.
  - ✅ Implement PoA proposer loop with block assembly (`apps/blockchain-node/src/aitbc_chain/consensus/poa.py`).
  - ✅ Expose REST RPC endpoints for tx submission, balances, receipts (`apps/blockchain-node/src/aitbc_chain/rpc/router.py`).
  - ⏳ Deliver WebSocket RPC + P2P gossip layer:
    - Stand up WebSocket subscription endpoints (`apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`) mirroring REST payloads.
    - Implement pub/sub transport for block + transaction gossip backed by an in-memory broker (Starlette `Broadcast` or Redis) with configurable fan-out.
    - Add integration tests and load-test harness ensuring gossip convergence and back-pressure handling.
  - ✅ Ship devnet scripts (`apps/blockchain-node/scripts/`).
  - ✅ Add observability hooks (JSON logging, Prometheus metrics) and integrate coordinator mock into devnet tooling.
  - ⏳ Expand observability dashboards + miner mock integration:
    - Build Grafana dashboards for consensus health (block intervals, proposer rotation) and RPC latency (`apps/blockchain-node/observability/`).
    - Expose miner mock telemetry (job throughput, error rates) via shared Prometheus registry and ingest into blockchain-node dashboards.
    - Add alerting rules (Prometheus `Alertmanager`) for stalled proposers, queue saturation, and miner mock disconnects.
    - Wire coordinator mock into devnet tooling to simulate real-world load and validate observability hooks.

- **Receipt Schema**
  - ✅ Finalize canonical JSON receipt format under `protocols/receipts/` (includes sample signed receipts).
  - ✅ Implement signing/verification helpers in `packages/py/aitbc-crypto` (JS SDK pending).
  - ✅ Translate `docs/bootstrap/aitbc_tech_plan.md` contract skeleton into Solidity project (`packages/solidity/aitbc-token/`).
  - ✅ Add deployment/test scripts and document minting flow (`packages/solidity/aitbc-token/scripts/` and `docs/run.md`).

- **Wallet Daemon**
  - ✅ Implement encrypted keystore (Argon2id + XChaCha20-Poly1305) via `KeystoreService`.
  - ✅ Provide REST and JSON-RPC endpoints for wallet management and signing (`api_rest.py`, `api_jsonrpc.py`).
  - ✅ Add mock ledger adapter with SQLite backend powering event history (`ledger_mock/`).
  - ✅ Integrate Python receipt verification helpers (`aitbc_sdk`) and expose API/service utilities validating miner + coordinator signatures.
  - ✅ Implement Wallet SDK receipt ingestion + attestation surfacing:
    - Added `/v1/jobs/{job_id}/receipts` client helpers with cursor pagination, retry/backoff, and summary reporting (`packages/py/aitbc-sdk/src/receipts.py`).
    - Reused crypto helpers to validate miner and coordinator signatures, capturing per-key failure reasons for downstream UX.
    - Surfaced aggregated attestation status (`ReceiptStatus`) and failure diagnostics for SDK + UI consumers; JS helper parity still planned.

## Stage 2 — Pool Hub & Marketplace

- **Pool Hub**
  - ✅ Implement miner registry, scoring engine, and `/v1/match` API with Redis/PostgreSQL backing stores.
  - ✅ Add observability endpoints (`/v1/health`, `/v1/metrics`) plus Prometheus instrumentation and integration tests.

- **Marketplace Web**
  - Initialize Vite project with vanilla TypeScript.
  - Build offer list, bid form, stats views sourcing mock JSON.
  - Provide API abstraction to switch between mock and real backends.

- **Explorer Web**
  - ✅ Initialize Vite + TypeScript project scaffold (`apps/explorer-web/`).
  - ✅ Add routed pages for overview, blocks, transactions, addresses, receipts.
  - ✅ Seed mock datasets (`public/mock/`) and fetch helpers powering overview + blocks tables.
  - ✅ Extend mock integrations to transactions, addresses, and receipts pages.
  - ✅ Implement styling system, mock/live data toggle, and coordinator API wiring scaffold.
  - ✅ Render overview stats from mock block/transaction/receipt summaries with graceful empty-state fallbacks.
  - ⏳ Validate live mode + responsive polish:
    - Hit live coordinator endpoints (`/v1/blocks`, `/v1/transactions`, `/v1/addresses`, `/v1/receipts`) via `getDataMode() === "live"` and reconcile payloads with UI models.
    - Add fallbacks + error surfacing for partial/failed live responses (toast + console diagnostics).
    - Audit responsive breakpoints (`public/css/layout.css`) and adjust grid/typography for tablet + mobile; add regression checks in Percy/Playwright snapshots.

## Shared Libraries & Examples

- **Python SDK (`packages/py/aitbc-sdk`)**
  - ✅ Implement coordinator receipt client + verification helpers (miner + coordinator attestation support).
  - ⏳ Extend helpers to pool hub + wallet APIs and typed models:
    - Add REST clients for upcoming Pool Hub endpoints (`/v1/match`, `/v1/miners`) and wallet daemon routes (`/v1/wallets`, `/v1/sign`) with retry/backoff helpers.
    - Introduce pydantic/SQLModel-derived typed models mirroring `protocols/api/` and `protocols/receipts/` schemas.
    - Provide end-to-end tests + examples validating Pool Hub + wallet flows leveraging the coordinator receipt verification primitives.

- **JavaScript SDK (`packages/js/aitbc-sdk`)**
  - ✅ Provide fetch-based wrapper for web clients with TypeScript definitions and basic auth helpers.

- **Examples**
  - Populate quickstart clients (Python/JS) with working code.
  - Add receipt sign/verify samples using finalized schema.

## Tooling & Operations

- **Scripts & CI**
  - ✅ Populate `scripts/ci/run_python_tests.sh` to run coordinator, SDK, wallet-daemon pytest suites with shared `PYTHONPATH` scaffolding.
  - ✅ Add GitHub Actions workflow `.github/workflows/python-tests.yml` invoking the shared script on pushes/PRs targeting `main`.

- **Configs**
  - Author systemd unit files in `configs/systemd/` for each service.
  - Provide Nginx snippets in `configs/nginx/` for reverse proxies.

## Tracking

Use this roadmap as the canonical checklist during implementation. Mark completed tasks with ✅ and add dates or links to relevant PRs as development progresses.

## Upcoming Focus Areas

- **Blockchain Node**: bootstrap module layout (`apps/blockchain-node/src/`), implement SQLModel schemas and RPC stubs aligned with historical/attested receipts.
- **Explorer Web**: finish mock integration across all pages, add styling + mock/live toggle, and begin wiring coordinator endpoints (e.g., `/v1/jobs/{job_id}/receipts`).
  - Current focus: reuse new overview metrics scaffolding for blocks/transactions detail views and expand coverage to live data mode.
- **Marketplace Web**: scaffold Vite/vanilla frontends with mock integrations consuming the coordinator receipt history endpoints and SDK examples.
- **Pool Hub**: initialize FastAPI project, scoring registry, and telemetry ingestion hooks leveraging coordinator/miner metrics.
- **CI Enhancements**: add blockchain-node tests once available and frontend build/lint checks to `.github/workflows/python-tests.yml` or follow-on workflows.
  - ⏳ Add systemd unit and installer scripts under `scripts/`.
