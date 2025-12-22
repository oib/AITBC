# AITBC Development Roadmap

This roadmap aggregates high-priority tasks derived from the bootstrap specifications in `docs/bootstrap/` and tracks progress across the monorepo. Update this document as milestones evolve.

## Stage 1 — Upcoming Focus Areas

- **Blockchain Node Foundations**
  - ✅ Bootstrap module layout in `apps/blockchain-node/src/`.
  - ✅ Implement SQLModel schemas and RPC stubs aligned with historical/attested receipts.

- **Explorer Web Enablement**
  - ✅ Finish mock integration across all pages and polish styling + mock/live toggle.
  - ✅ Begin wiring coordinator endpoints (e.g., `/v1/jobs/{job_id}/receipts`).

- **Marketplace Web Scaffolding**
  - ✅ Scaffold Vite/vanilla frontends consuming coordinator receipt history endpoints and SDK examples.

- **Pool Hub Services**
  - ✅ Initialize FastAPI project, scoring registry, and telemetry ingestion hooks leveraging coordinator/miner metrics.

- **CI Enhancements**
  - ✅ Add blockchain-node tests once available and frontend build/lint checks to `.github/workflows/python-tests.yml` or follow-on workflows.
  - ✅ Provide systemd unit + installer scripts under `scripts/` for streamlined deployment.

## Stage 2 — Core Services (MVP)

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
  - ✅ Deliver WebSocket RPC + P2P gossip layer:
    - ✅ Stand up WebSocket subscription endpoints (`apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`) mirroring REST payloads.
    - ✅ Implement pub/sub transport for block + transaction gossip backed by an in-memory broker (Starlette `Broadcast` or Redis) with configurable fan-out.
    - ✅ Add integration tests and load-test harness ensuring gossip convergence and back-pressure handling.
  - ✅ Ship devnet scripts (`apps/blockchain-node/scripts/`).
  - ✅ Add observability hooks (JSON logging, Prometheus metrics) and integrate coordinator mock into devnet tooling.
  - ✅ Expand observability dashboards + miner mock integration:
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
  - ✅ Harden REST API workflows (create/list/unlock/sign) with structured password policy enforcement and deterministic pytest coverage in `apps/wallet-daemon/tests/test_wallet_api.py`.
  - ✅ Implement Wallet SDK receipt ingestion + attestation surfacing:
    - Added `/v1/jobs/{job_id}/receipts` client helpers with cursor pagination, retry/backoff, and summary reporting (`packages/py/aitbc-sdk/src/receipts.py`).
    - Reused crypto helpers to validate miner and coordinator signatures, capturing per-key failure reasons for downstream UX.
    - Surfaced aggregated attestation status (`ReceiptStatus`) and failure diagnostics for SDK + UI consumers; JS helper parity still planned.

## Stage 3 — Pool Hub & Marketplace

- **Pool Hub**
  - ✅ Implement miner registry, scoring engine, and `/v1/match` API with Redis/PostgreSQL backing stores.
  - ✅ Add observability endpoints (`/v1/health`, `/v1/metrics`) plus Prometheus instrumentation and integration tests.

- **Marketplace Web**
  - ✅ Initialize Vite project with vanilla TypeScript (`apps/marketplace-web/`).
  - ✅ Build offer list, bid form, and stats cards powered by mock data fixtures (`public/mock/`).
  - ✅ Provide API abstraction toggling mock/live mode (`src/lib/api.ts`) and wire coordinator endpoints.
  - ✅ Validate live mode against coordinator `/v1/marketplace/*` responses and add auth feature flags for rollout.

- **Explorer Web**
  - ✅ Initialize Vite + TypeScript project scaffold (`apps/explorer-web/`).
  - ✅ Add routed pages for overview, blocks, transactions, addresses, receipts.
  - ✅ Seed mock datasets (`public/mock/`) and fetch helpers powering overview + blocks tables.
  - ✅ Extend mock integrations to transactions, addresses, and receipts pages.
  - ✅ Implement styling system, mock/live data toggle, and coordinator API wiring scaffold.
  - ✅ Render overview stats from mock block/transaction/receipt summaries with graceful empty-state fallbacks.
  - ✅ Validate live mode + responsive polish:
    - Hit live coordinator endpoints (`/v1/blocks`, `/v1/transactions`, `/v1/addresses`, `/v1/receipts`) via `getDataMode() === "live"` and reconcile payloads with UI models.
    - Add fallbacks + error surfacing for partial/failed live responses (toast + console diagnostics).
    - Audit responsive breakpoints (`public/css/layout.css`) and adjust grid/typography for tablet + mobile; add regression checks in Percy/Playwright snapshots.

## Stage 4 — Observability & Production Polish

- **Observability & Telemetry**
  - ✅ Build Grafana dashboards for PoA consensus health (block intervals, proposer rotation cadence) leveraging `poa_last_block_interval_seconds`, `poa_proposer_rotations_total`, and per-proposer counters.
  - ✅ Surface RPC latency histograms/summaries for critical endpoints (`rpc_get_head`, `rpc_send_tx`, `rpc_submit_receipt`) and add Grafana panels with SLO thresholds.
  - ✅ Ingest miner mock telemetry (job throughput, failure rate) into the shared Prometheus registry and wire panels/alerts that correlate miner health with consensus metrics.

- **Explorer Web (Live Mode)**
  - ✅ Finalize live `getDataMode() === "live"` workflow: align API payload contracts, render loading/error states, and persist mock/live toggle preference.
  - ✅ Expand responsive testing (tablet/mobile) and add automated visual regression snapshots prior to launch.
  - ✅ Integrate Playwright smoke tests covering overview, blocks, and transactions pages in live mode.

- **Marketplace Web (Launch Readiness)**
  - ✅ Connect mock listings/bids to coordinator data sources and provide feature flags for live mode rollout.
  - ✅ Implement auth/session scaffolding for marketplace actions and document API assumptions in `apps/marketplace-web/README.md`.
  - ✅ Add Grafana panels monitoring marketplace API throughput and error rates once endpoints are live.

- **Operational Hardening**
  - ✅ Extend Alertmanager rules to cover RPC error spikes, proposer stalls, and miner disconnects using the new metrics.
  - ✅ Document dashboard import + alert deployment steps in `docs/run.md` for operators.
  - ✅ Prepare Stage 3 release checklist linking dashboards, alerts, and smoke tests prior to production cutover.

## Stage 5 — Scaling & Release Readiness

- **Infrastructure Scaling**
  - ✅ Benchmark blockchain node throughput under sustained load; capture CPU/memory targets and suggest horizontal scaling thresholds.
  - ✅ Build Terraform/Helm templates for dev/staging/prod environments, including Prometheus/Grafana bundles.
  - ✅ Implement autoscaling policies for coordinator, miners, and marketplace services with synthetic traffic tests.

- **Reliability & Compliance**
  - ✅ Formalize backup/restore procedures for PostgreSQL, Redis, and ledger storage with scheduled jobs.
  - ✅ Complete security hardening review (TLS termination, API auth, secrets management) and document mitigations in `docs/security.md`.
  - ✅ Add chaos testing scripts (network partition, coordinator outage) and track mean-time-to-recovery metrics.

- **Product Launch Checklist**
  - ✅ Finalize public documentation (API references, onboarding guides) and publish to the docs portal.
  - ✅ Coordinate beta release timeline, including user acceptance testing of explorer/marketplace live modes.
  - ✅ Establish post-launch monitoring playbooks and on-call rotations.

## Stage 6 — Ecosystem Expansion

- **Cross-Chain & Interop**
  - ✅ Prototype cross-chain settlement hooks leveraging external bridges; document integration patterns.
  - ✅ Extend SDKs (Python/JS) with pluggable transport abstractions for multi-network support.
  - ⏳ Evaluate third-party explorer/analytics integrations and publish partner onboarding guides.

- **Marketplace Growth**
  - ⏳ Launch incentive programs (staking, liquidity mining) and expose telemetry dashboards tracking campaign performance.
  - ⏳ Implement governance module (proposal voting, parameter changes) and add API/UX flows to explorer/marketplace.
  - ⏳ Provide SLA-backed coordinator/pool hubs with capacity planning and billing instrumentation.

- **Developer Experience**
  - ⏳ Publish advanced tutorials (custom proposers, marketplace extensions) and maintain versioned API docs.
  - ⏳ Integrate CI/CD pipelines with canary deployments and blue/green release automation.
  - ⏳ Host quarterly architecture reviews capturing lessons learned and feeding into roadmap revisions.

## Stage 7 — Innovation & Ecosystem Services

- **GPU Service Expansion**
  - ✅ Implement dynamic service registry framework for 30+ GPU-accelerated services
  - ✅ Create service definitions for AI/ML (LLM inference, image/video generation, speech recognition, computer vision, recommendation systems)
  - ✅ Create service definitions for Media Processing (video transcoding, streaming, 3D rendering, image/audio processing)
  - ✅ Create service definitions for Scientific Computing (molecular dynamics, weather modeling, financial modeling, physics simulation, bioinformatics)
  - ✅ Create service definitions for Data Analytics (big data processing, real-time analytics, graph analytics, time series analysis)
  - ✅ Create service definitions for Gaming & Entertainment (cloud gaming, asset baking, physics simulation, VR/AR rendering)
  - ✅ Create service definitions for Development Tools (GPU compilation, model training, data processing, simulation testing, code generation)
  - ✅ Deploy service provider configuration UI with dynamic service selection
  - ✅ Implement service-specific validation and hardware requirement checking

- **Advanced Cryptography & Privacy**
  - ✅ Research zk-proof-based receipt attestation and prototype a privacy-preserving settlement flow.
  - ✅ Add confidential transaction support with opt-in ciphertext storage and HSM-backed key management.
  - ✅ Publish threat modeling updates and share mitigations with ecosystem partners.

- **Enterprise Integrations**
  - ✅ Deliver reference connectors for ERP/payment systems and document SLA expectations.
  - ✅ Stand up multi-tenant coordinator infrastructure with per-tenant isolation and billing metrics.
  - ✅ Launch ecosystem certification program (SDK conformance, security best practices) with public registry.

- **Community & Governance**
  - ✅ Establish open RFC process, publish governance website, and schedule regular community calls.
  - ✅ Sponsor hackathons/accelerators and provide grants for marketplace extensions and analytics tooling.
  - ✅ Track ecosystem KPIs (active marketplaces, cross-chain volume) and feed them into quarterly strategy reviews.

## Stage 8 — Frontier R&D & Global Expansion

- **Protocol Evolution**
  - ✅ Launch research consortium exploring next-gen consensus (hybrid PoA/PoS) and finalize whitepapers.
  - ⏳ Prototype sharding or rollup architectures to scale throughput beyond current limits.
  - ⏳ Standardize interoperability specs with industry bodies and submit proposals for adoption.

- **Global Rollout**
  - ⏳ Establish regional infrastructure hubs (multi-cloud) with localized compliance and data residency guarantees.
  - ⏳ Partner with regulators/enterprises to pilot regulated marketplaces and publish compliance playbooks.
  - ⏳ Expand localization (UI, documentation, support) covering top target markets.

- **Long-Term Sustainability**
  - ⏳ Create sustainability fund for ecosystem maintenance, bug bounties, and community stewardship.
  - ⏳ Define succession planning for core teams, including training programs and contributor pathways.
  - ⏳ Publish bi-annual roadmap retrospectives assessing KPI alignment and revising long-term goals.

## Stage 9 — Moonshot Initiatives

- **Decentralized Infrastructure**
  - ⏳ Transition coordinator/miner roles toward community-governed validator sets with incentive alignment.
  - ⏳ Explore decentralized storage/backbone options (IPFS/Filecoin) for ledger and marketplace artifacts.
  - ⏳ Prototype fully trustless marketplace settlement leveraging zero-knowledge rollups.

- **AI & Automation**
  - ⏳ Integrate AI-driven monitoring/anomaly detection for proposer health, market liquidity, and fraud detection.
  - ⏳ Automate incident response playbooks with ChatOps and policy engines.
  - ⏳ Launch research into autonomous agent participation (AI agents bidding/offering in the marketplace) and governance implications.
- **Global Standards Leadership**
  - ⏳ chair industry working groups defining receipt/marketplace interoperability standards.
  - ⏳ Publish annual transparency reports and sustainability metrics for stakeholders.
  - ⏳ Engage with academia and open-source foundations to steward long-term protocol evolution.

### Stage 10 — Stewardship & Legacy Planning

- **Open Governance Maturity**
  - ⏳ Transition roadmap ownership to community-elected councils with transparent voting and treasury controls.
  - ⏳ Codify constitutional documents (mission, values, conflict resolution) and publish public charters.
  - ⏳ Implement on-chain governance modules for protocol upgrades and ecosystem-wide decisions.

- **Educational & Outreach Programs**
  - ⏳ Fund university partnerships, research chairs, and developer fellowships focused on decentralized marketplace tech.
  - ⏳ Create certification tracks and mentorship programs for new validator/operators.
  - ⏳ Launch annual global summit and publish proceedings to share best practices across partners.

- **Long-Term Preservation**
  - ⏳ Archive protocol specs, governance records, and cultural artifacts in decentralized storage with redundancy.
  - ⏳ Establish legal/organizational frameworks to ensure continuity across jurisdictions.
  - ⏳ Develop end-of-life/transition plans for legacy components, documenting deprecation strategies and migration tooling.


## Shared Libraries & Examples
the canonical checklist during implementation. Mark completed tasks with ✅ and add dates or links to relevant PRs as development progresses.

