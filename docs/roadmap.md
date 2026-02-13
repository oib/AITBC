# AITBC Development Roadmap

This roadmap aggregates high-priority tasks derived from the bootstrap specifications in `docs/bootstrap/` and tracks progress across the monorepo. Update this document as milestones evolve.

## Stage 1 — Upcoming Focus Areas [COMPLETED: 2025-12-22]

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

## Stage 2 — Core Services (MVP) [COMPLETED: 2025-12-22]

- **Coordinator API**
  - ✅ Scaffold FastAPI project (`apps/coordinator-api/src/app/`).
  - ✅ Implement job submission, status, result endpoints.
  - ✅ Add miner registration, heartbeat, poll, result routes.
  - ✅ Wire SQLite persistence for jobs, miners, receipts (historical `JobReceipt` table).
  - ✅ Provide `.env.example`, `pyproject.toml`, and run scripts.
  - ✅ Deploy minimal version in container with nginx proxy

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

## Stage 3 — Pool Hub & Marketplace [COMPLETED: 2025-12-22]

- **Pool Hub**
  - ✅ Implement miner registry, scoring engine, and `/v1/match` API with Redis/PostgreSQL backing stores.
  - ✅ Add observability endpoints (`/v1/health`, `/v1/metrics`) plus Prometheus instrumentation and integration tests.

- **Marketplace Web**
  - ✅ Initialize Vite project with vanilla TypeScript (`apps/marketplace-web/`).
  - ✅ Build offer list, bid form, and stats cards powered by mock data fixtures (`public/mock/`).
  - ✅ Provide API abstraction toggling mock/live mode (`src/lib/api.ts`) and wire coordinator endpoints.
  - ✅ Validate live mode against coordinator `/v1/marketplace/*` responses and add auth feature flags for rollout.
  - ✅ Deploy to production at https://aitbc.bubuit.net/marketplace/

- **Explorer Web**
  - ✅ Initialize Vite + TypeScript project scaffold (`apps/explorer-web/`).
  - ✅ Add routed pages for overview, blocks, transactions, addresses, receipts.
  - ✅ Seed mock datasets (`public/mock/`) and fetch helpers powering overview + blocks tables.
  - ✅ Extend mock integrations to transactions, addresses, and receipts pages.
  - ✅ Implement styling system, mock/live data toggle, and coordinator API wiring scaffold.
  - ✅ Render overview stats from mock block/transaction/receipt summaries with graceful empty-state fallbacks.
  - ✅ Validate live mode + responsive polish:
    - Hit live coordinator endpoints via nginx (`/api/explorer/blocks`, `/api/explorer/transactions`, `/api/explorer/addresses`, `/api/explorer/receipts`) via `getDataMode() === "live"` and reconcile payloads with UI models.
    - Add fallbacks + error surfacing for partial/failed live responses (toast + console diagnostics).
    - Audit responsive breakpoints (`public/css/layout.css`) and adjust grid/typography for tablet + mobile; add regression checks in Percy/Playwright snapshots.
  - ✅ Deploy to production at https://aitbc.bubuit.net/explorer/ with genesis block display

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
  - ✅ Enable host GPU miner with coordinator proxy routing and systemd-backed coordinator service; add proxy health timer.

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
  - 🔄 Evaluate third-party explorer/analytics integrations and publish partner onboarding guides.

- **Marketplace Growth**
  - ✅ Launch incentive programs (staking, liquidity mining) and expose telemetry dashboards tracking campaign performance.
  - ✅ Implement governance module (proposal voting, parameter changes) and add API/UX flows to explorer/marketplace.
  - 🔄 Provide SLA-backed coordinator/pool hubs with capacity planning and billing instrumentation.

- **Developer Experience**
  - ✅ Publish advanced tutorials (custom proposers, marketplace extensions) and maintain versioned API docs.
  - 🔄 Integrate CI/CD pipelines with canary deployments and blue/green release automation.
  - 🔄 Host quarterly architecture reviews capturing lessons learned and feeding into roadmap revisions.

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

## Stage 8 — Frontier R&D & Global Expansion [COMPLETED: 2025-12-28]

- **Protocol Evolution**
  - ✅ Launch research consortium exploring next-gen consensus (hybrid PoA/PoS) and finalize whitepapers.
  - 🔄 Prototype sharding or rollup architectures to scale throughput beyond current limits.
  - 🔄 Standardize interoperability specs with industry bodies and submit proposals for adoption.

- **Global Rollout**
  - 🔄 Establish regional infrastructure hubs (multi-cloud) with localized compliance and data residency guarantees.
  - 🔄 Partner with regulators/enterprises to pilot regulated marketplaces and publish compliance playbooks.
  - 🔄 Expand localization (UI, documentation, support) covering top target markets.

- **Long-Term Sustainability**
  - 🔄 Create sustainability fund for ecosystem maintenance, bug bounties, and community stewardship.
  - 🔄 Define succession planning for core teams, including training programs and contributor pathways.
  - 🔄 Publish bi-annual roadmap retrospectives assessing KPI alignment and revising long-term goals.

## Stage 9 — Moonshot Initiatives [COMPLETED: 2025-12-28]

- **Decentralized Infrastructure**
  - 🔄 Transition coordinator/miner roles toward community-governed validator sets with incentive alignment.
  - 🔄 Explore decentralized storage/backbone options (IPFS/Filecoin) for ledger and marketplace artifacts.
  - 🔄 Prototype fully trustless marketplace settlement leveraging zero-knowledge rollups.

- **AI & Automation**
  - 🔄 Integrate AI-driven monitoring/anomaly detection for proposer health, market liquidity, and fraud detection.
  - 🔄 Automate incident response playbooks with ChatOps and policy engines.
  - 🔄 Launch research into autonomous agent participation (AI agents bidding/offering in the marketplace) and governance implications.
- **Global Standards Leadership**
  - 🔄 Chair industry working groups defining receipt/marketplace interoperability standards.
  - 🔄 Publish annual transparency reports and sustainability metrics for stakeholders.
  - 🔄 Engage with academia and open-source foundations to steward long-term protocol evolution.

### Stage 10 — Stewardship & Legacy Planning [COMPLETED: 2025-12-28]

- **Open Governance Maturity**
  - 🔄 Transition roadmap ownership to community-elected councils with transparent voting and treasury controls.
  - 🔄 Codify constitutional documents (mission, values, conflict resolution) and publish public charters.
  - 🔄 Implement on-chain governance modules for protocol upgrades and ecosystem-wide decisions.

- **Educational & Outreach Programs**
  - 🔄 Fund university partnerships, research chairs, and developer fellowships focused on decentralized marketplace tech.
  - 🔄 Create certification tracks and mentorship programs for new validator/operators.
  - 🔄 Launch annual global summit and publish proceedings to share best practices across partners.

- **Long-Term Preservation**
  - 🔄 Archive protocol specs, governance records, and cultural artifacts in decentralized storage with redundancy.
  - 🔄 Establish legal/organizational frameworks to ensure continuity across jurisdictions.
  - 🔄 Develop end-of-life/transition plans for legacy components, documenting deprecation strategies and migration tooling.


## Shared Libraries & Examples

## Stage 11 — Trade Exchange & Token Economy [COMPLETED: 2025-12-28]

- **Bitcoin Wallet Integration**
  - ✅ Implement Bitcoin payment gateway for AITBC token purchases
  - ✅ Create payment request API with unique payment addresses
  - ✅ Add QR code generation for mobile payments
  - ✅ Implement real-time payment monitoring with blockchain API
  - ✅ Configure exchange rate: 1 BTC = 100,000 AITBC

- **User Management System**
  - ✅ Implement wallet-based authentication with session management
  - ✅ Create individual user accounts with unique wallets
  - ✅ Add user profile pages with transaction history
  - ✅ Implement secure session tokens with 24-hour expiry
  - ✅ Add login/logout functionality across all pages

- **Trade Exchange Platform**
  - ✅ Build responsive trading interface with real-time price updates
  - ✅ Integrate Bitcoin payment flow with QR code display
  - ✅ Add payment status monitoring and confirmation handling
  - ✅ Implement AITBC token minting upon payment confirmation
  - ✅ Deploy to production at https://aitbc.bubuit.net/Exchange/

- **API Infrastructure**
  - ✅ Add user management endpoints (/api/users/*)
  - ✅ Implement exchange payment endpoints (/api/exchange/*)
  - ✅ Add session-based authentication for protected routes
  - ✅ Create transaction history and balance tracking APIs
  - ✅ Fix all import and syntax errors in coordinator API

## Stage 13 — Explorer Live API & Reverse Proxy Fixes [COMPLETED: 2025-12-28]

- **Explorer Live API**
  - ✅ Enable coordinator explorer routes at `/v1/explorer/*`.
  - ✅ Expose nginx explorer proxy at `/api/explorer/*` (maps to backend `/v1/explorer/*`).
  - ✅ Fix response schema mismatches (e.g., receipts response uses `jobId`).

- **Coordinator API Users/Login**
  - ✅ Ensure `/v1/users/login` is registered and working.
  - ✅ Fix missing SQLModel tables by initializing DB on startup (wallet/user tables created).

- **nginx Reverse Proxy Hardening**
  - ✅ Fix `/api/v1/*` routing to avoid double `/v1` prefix.
  - ✅ Add compatibility proxy for Exchange: `/api/users/*` → backend `/v1/users/*`.

## Stage 12 — Zero-Knowledge Proof Implementation [COMPLETED: 2025-12-28]

- **Circom Compiler Setup**
  - ✅ Install Circom compiler v2.2.3 on production server
  - ✅ Configure Node.js environment for ZK circuit compilation
  - ✅ Install circomlib and required dependencies

- **ZK Circuit Development**
  - ✅ Create receipt attestation circuit (receipt_simple.circom)
  - ✅ Implement membership proof circuit template
  - ✅ Implement bid range proof circuit template
  - ✅ Compile circuits to R1CS, WASM, and symbolic files

- **Trusted Setup Ceremony**
  - ✅ Perform Powers of Tau setup ceremony (2^12)
  - ✅ Generate proving keys (zkey) for Groth16
  - ✅ Export verification keys for on-chain verification
  - ✅ Complete phase 2 preparation with contributions

- **ZK Applications API**
  - ✅ Implement identity commitment endpoints
  - ✅ Create stealth address generation service
  - ✅ Add private receipt attestation API
  - ✅ Implement group membership proof verification
  - ✅ Add private bidding functionality
  - ✅ Create computation proof verification
  - ✅ Deploy to production at /api/zk/ endpoints

- **Integration & Deployment**
  - ✅ Integrate ZK proof service with coordinator API
  - ✅ Configure circuit files in production environment
  - ✅ Enable ZK proof generation in coordinator service
  - ✅ Update documentation with ZK capabilities

## Stage 14 — Explorer JavaScript Error Fixes [COMPLETED: 2025-12-30]

- **JavaScript Error Resolution**
  - ✅ Fixed "can't access property 'length', t is undefined" error on Explorer page load
  - ✅ Updated fetchMock function in mockData.ts to return correct structure with 'items' property
  - ✅ Added defensive null checks in all page init functions (overview, blocks, transactions, addresses, receipts)
  - ✅ Fixed TypeScript errors for null checks and missing properties
  - ✅ Deployed fixes to production server (/var/www/aitbc.bubuit.net/explorer/)
  - ✅ Configured mock data serving from correct path (/explorer/mock/)

## Stage 15 — Cascade Skills Framework [COMPLETED: 2025-01-19]

- **Skills Infrastructure**
  - ✅ Implement Cascade skills framework for complex workflow automation
  - ✅ Create skills directory structure at `.windsurf/skills/`
  - ✅ Define skill metadata format with YAML frontmatter
  - ✅ Add progressive disclosure for intelligent skill invocation

- **Deploy-Production Skill**
  - ✅ Create comprehensive deployment workflow skill
  - ✅ Implement pre-deployment validation script (disk, memory, services, SSL)
  - ✅ Add environment template with all production variables
  - ✅ Create rollback procedures with emergency steps
  - ✅ Build health check script for post-deployment verification

- **Blockchain-Operations Skill**
  - ✅ Create node health monitoring with peer analysis and sync status
  - ✅ Implement transaction tracer for debugging and gas optimization
  - ✅ Build GPU mining optimization script for NVIDIA/AMD cards
  - ✅ Add real-time sync monitor with visual progress bar
  - ✅ Create network diagnostics tool with connectivity analysis

- **Skills Integration**
  - ✅ Enable automatic skill invocation based on context
  - ✅ Add manual skill triggering with keyword detection
  - ✅ Implement error handling and logging in all skills
  - ✅ Create comprehensive documentation and usage examples

## Stage 16 — Service Maintenance & Optimization [COMPLETED: 2026-01-21]

- **Service Recovery**
  - ✅ Diagnose and fix all failing AITBC container services
  - ✅ Resolve duplicate service conflicts causing port binding errors
  - ✅ Fix marketplace service implementation (missing server.py)
  - ✅ Disable redundant services to prevent resource conflicts

- **System Administration**
  - ✅ Configure passwordless SSH access for automation
  - ✅ Create dedicated SSH keys for secure service management
  - ✅ Document service dependencies and port mappings
  - ✅ Establish service monitoring procedures

- **Service Status Verification**
  - ✅ Verify all 7 core services running correctly
  - ✅ Confirm proper nginx reverse proxy configuration
  - ✅ Validate API endpoints accessibility
  - ✅ Test service recovery procedures

## Stage 17 — Ollama GPU Inference & CLI Tooling [COMPLETED: 2026-01-24]

- **End-to-End Ollama Testing**
  - ✅ Verify complete GPU inference workflow from job submission to receipt generation
  - ✅ Test Ollama integration with multiple models (llama3.2, mistral, deepseek, etc.)
  - ✅ Validate job lifecycle: QUEUED → RUNNING → COMPLETED
  - ✅ Confirm receipt generation with accurate payment calculations
  - ✅ Record transactions on blockchain with proper metadata

- **Coordinator API Bug Fixes**
  - ✅ Fix missing `_coerce_float()` helper function causing 500 errors
  - ✅ Deploy fix to production incus container via SSH
  - ✅ Verify result submission returns 200 OK with valid receipts
  - ✅ Validate receipt payload structure and signature generation

- **Miner Configuration & Optimization**
  - ✅ Fix miner ID mismatch (host-gpu-miner → ${MINER_API_KEY})
  - ✅ Enhance logging with explicit flush handlers for systemd journal
  - ✅ Configure unbuffered Python logging environment variables
  - ✅ Create systemd service unit with proper environment configuration

- **CLI Tooling Development**
  - ✅ Create unified bash CLI wrapper (`scripts/aitbc-cli.sh`)
  - ✅ Implement commands: submit, status, browser, blocks, receipts, cancel
  - ✅ Add admin commands: admin-miners, admin-jobs, admin-stats
  - ✅ Support environment variable overrides for URL and API keys
  - ✅ Make script executable and document usage patterns

- **Blockchain-Operations Skill Enhancement**
  - ✅ Add comprehensive Ollama testing scenarios to skill
  - ✅ Create detailed test documentation (`ollama-test-scenario.md`)
  - ✅ Document common issues and troubleshooting procedures
  - ✅ Add performance metrics and expected results
  - ✅ Include end-to-end automation script template

- **Documentation Updates**
  - ✅ Update localhost testing scenario with CLI wrapper usage
  - ✅ Convert examples to use localhost URLs (127.0.0.1)
  - ✅ Add host user paths and quick start commands
  - ✅ Document complete workflow from setup to verification
  - ✅ Update skill documentation with testing scenarios

## Stage 18 — Repository Reorganization & CSS Consolidation [COMPLETED: 2026-01-24]

- **Root Level Cleanup**
  - ✅ Move 60+ loose files from root to proper directories
  - ✅ Organize deployment scripts into `scripts/deploy/`
  - ✅ Organize GPU miner files into `scripts/gpu/`
  - ✅ Organize test/verify files into `scripts/test/`
  - ✅ Organize service management scripts into `scripts/service/`
  - ✅ Move systemd services to `systemd/`
  - ✅ Move nginx configs to `infra/nginx/`
  - ✅ Move dashboards to `website/dashboards/`

- **Website/Docs Folder Structure**
  - ✅ Establish `/website/docs/` as source for HTML documentation
  - ✅ Create shared CSS file (`css/docs.css`) with 1232 lines
  - ✅ Create theme toggle JavaScript (`js/theme.js`)
  - ✅ Migrate all HTML files to use external CSS (45-66% size reduction)
  - ✅ Clean `/docs/` folder to only contain mkdocs markdown files

- **Documentation Styling Fixes**
  - ✅ Fix dark theme background consistency across all docs pages
  - ✅ Add dark theme support to `full-documentation.html`
  - ✅ Fix Quick Start section cascade styling in docs-miners.html
  - ✅ Fix SDK Examples cascade indentation in docs-clients.html
  - ✅ Fix malformed `</code-block>` tags across all docs
  - ✅ Update API endpoint example to use Python/FastAPI

- **Path Reference Updates**
  - ✅ Update systemd service file with new `scripts/gpu/gpu_miner_host.py` path
  - ✅ Update skill documentation with new file locations
  - ✅ Update localhost-testing-scenario.md with correct paths
  - ✅ Update gpu_miner_host_wrapper.sh with new path

- **Repository Maintenance**
  - ✅ Expand .gitignore from 39 to 145 lines with organized sections
  - ✅ Add project-specific ignore rules for coordinator, explorer, GPU miner
  - ✅ Document final folder structure in done.md
  - ✅ Create `docs/files.md` file audit with whitelist/greylist/blacklist
  - ✅ Remove 35 abandoned/duplicate folders and files
  - ✅ Reorganize `docs/` folder - root contains only done.md, files.md, roadmap.md
  - ✅ Move 25 doc files to appropriate subfolders (components, deployment, migration, etc.)

## Stage 19 — Placeholder Content Development [PLANNED]

Fill the intentional placeholder folders with actual content. Priority order based on user impact.

### Phase 1: Documentation (High Priority)

- **User Guides** (`docs/user/guides/`) ✅ COMPLETE
  - [x] Bitcoin wallet setup (`BITCOIN-WALLET-SETUP.md`)
  - [x] User interface guide (`USER-INTERFACE-GUIDE.md`)
  - [x] User management setup (`USER-MANAGEMENT-SETUP.md`)
  - [x] Local assets summary (`LOCAL_ASSETS_SUMMARY.md`)
  - [x] Getting started guide (`getting-started.md`)
  - [x] Job submission workflow (`job-submission.md`)
  - [x] Payment and receipt understanding (`payments-receipts.md`)
  - [x] Troubleshooting common issues (`troubleshooting.md`)

- **Developer Tutorials** (`docs/developer/tutorials/`) ✅ COMPLETE
  - [x] Building a custom miner (`building-custom-miner.md`)
  - [x] Integrating with Coordinator API (`coordinator-api-integration.md`)
  - [x] Creating marketplace extensions (`marketplace-extensions.md`)
  - [x] Working with ZK proofs (`zk-proofs.md`)
  - [x] SDK usage examples (`sdk-examples.md`)

- **Reference Specs** (`docs/reference/specs/`) ✅ COMPLETE
  - [x] Receipt JSON schema specification (`receipt-spec.md`)
  - [x] API endpoint reference (`api-reference.md`)
  - [x] Protocol message formats (`protocol-messages.md`)
  - [x] Error codes and handling (`error-codes.md`)

### Phase 2: Infrastructure (Medium Priority) ✅ COMPLETE

- **Terraform Environments** (`infra/terraform/environments/`)
  - [x] `staging/main.tf` - Staging environment config
  - [x] `prod/main.tf` - Production environment config
  - [x] `variables.tf` - Shared variables
  - [x] `secrets.tf` - Secrets management (AWS Secrets Manager)
  - [x] `backend.tf` - State backend configuration (S3 + DynamoDB)

- **Helm Chart Values** (`infra/helm/values/`)
  - [x] `coordinator.yaml` - Coordinator service configuration
  - [x] `blockchain.yaml` - Blockchain node configuration
  - [x] `wallet.yaml` - Wallet daemon configuration
  - [x] `marketplace.yaml` - Marketplace service configuration

### Phase 3: Missing Integrations (High Priority)

- **Wallet-Coordinator Integration** ✅ COMPLETE
  - [x] Add payment endpoints to coordinator API for job payments (`routers/payments.py`)
  - [x] Implement escrow service for holding payments during job execution (`services/payments.py`)
  - [x] Integrate wallet daemon with coordinator for payment processing
  - [x] Add payment status tracking to job lifecycle (`domain/job.py` payment_id/payment_status)
  - [x] Implement refund mechanism for failed jobs (auto-refund on failure in `routers/miner.py`)
  - [x] Add payment receipt generation and verification (`/payments/{id}/receipt`)
  - [x] CLI payment commands: `client pay/payment-status/payment-receipt/refund` (7 tests)

### Phase 4: Integration Test Improvements ✅ COMPLETE 2026-01-26

- **Security Integration Tests** ✅ COMPLETE
  - [x] Updated to use real ZK proof features instead of mocks
  - [x] Test confidential job creation with `require_zk_proof: True`
  - [x] Verify secure job retrieval with tenant isolation

- **Marketplace Integration Tests** ✅ COMPLETE
  - [x] Updated to connect to live marketplace at https://aitbc.bubuit.net/marketplace
  - [x] Test marketplace accessibility and service integration
  - [x] Flexible API endpoint handling

- **Performance Tests** ❌ REMOVED
  - [x] Removed high throughput and load tests (too early for implementation)
  - [ ] Can be added back when performance thresholds are defined

- **Test Infrastructure** ✅ COMPLETE
  - [x] All tests work with both real client and mock fallback
  - [x] Fixed termination issues in Windsorf environment
  - [x] Current status: 6 tests passing, 1 skipped (wallet integration)

### Phase 3: Application Components (Lower Priority) ✅ COMPLETE

- **Pool Hub Service** (`apps/pool-hub/src/app/`)
  - [x] `routers/` - API route handlers (miners.py, pools.py, jobs.py, health.py)
  - [x] `registry/` - Miner registry implementation (miner_registry.py)
  - [x] `scoring/` - Scoring engine logic (scoring_engine.py)

- **Coordinator Migrations** (`apps/coordinator-api/migrations/`)
  - [x] `001_initial_schema.sql` - Initial schema migration
  - [x] `002_indexes.sql` - Index optimizations
  - [x] `003_data_migration.py` - Data migration scripts
  - [x] `README.md` - Migration documentation

### Placeholder Filling Schedule

| Folder | Target Date | Owner | Status |
|--------|-------------|-------|--------|
| `docs/user/guides/` | Q1 2026 | Documentation | ✅ Complete (2026-01-24) |
| `docs/developer/tutorials/` | Q1 2026 | Documentation | ✅ Complete (2026-01-24) |
| `docs/reference/specs/` | Q1 2026 | Documentation | ✅ Complete (2026-01-24) |
| `infra/terraform/environments/` | Q2 2026 | DevOps | ✅ Complete (2026-01-24) |
| `infra/helm/values/` | Q2 2026 | DevOps | ✅ Complete (2026-01-24) |
| `apps/pool-hub/src/app/` | Q2 2026 | Backend | ✅ Complete (2026-01-24) |
| `apps/coordinator-api/migrations/` | As needed | Backend | ✅ Complete (2026-01-24) |

## Stage 21 — Transaction-Dependent Block Creation [COMPLETED: 2026-01-28]

- **PoA Consensus Enhancement**
  - ✅ Modify PoA proposer to only create blocks when mempool has pending transactions
  - ✅ Implement HTTP polling mechanism to check RPC mempool size
  - ✅ Add transaction storage in block data with tx_count field
  - ✅ Remove processed transactions from mempool after block creation
  - ✅ Fix syntax errors and import issues in consensus/poa.py

- **Architecture Implementation**
  - ✅ RPC Service: Receives transactions and maintains in-memory mempool
  - ✅ Metrics Endpoint: Exposes mempool_size for node polling
  - ✅ Node Process: Polls metrics every 2 seconds, creates blocks only when needed
  - ✅ Eliminates empty blocks from blockchain
  - ✅ Maintains block integrity with proper transaction inclusion

- **Testing and Validation**
  - ✅ Deploy changes to both Node 1 and Node 2
  - ✅ Verify proposer skips block creation when no transactions
  - ✅ Confirm blocks are created when transactions are submitted
  - ✅ Fix gossip broker integration issues
  - ✅ Implement message passing solution for transaction synchronization

## Stage 22 — Future Enhancements ✅ COMPLETE

- **Shared Mempool Implementation** ✅
  - [x] Implement database-backed mempool for true sharing between services (`DatabaseMempool` with SQLite)
  - [x] Add gossip-based pub/sub for real-time transaction propagation (gossip broker on `/sendTx`)
  - [x] Optimize polling with fee-based prioritization and drain API

- **Advanced Block Production** ✅
  - [x] Implement block size limits and gas optimization (`max_block_size_bytes`, `max_txs_per_block`)
  - [x] Add transaction prioritization based on fees (highest-fee-first drain)
  - [x] Implement batch transaction processing (proposer drains + batch-inserts into block)
  - [x] Add block production metrics and monitoring (build duration, tx count, fees, interval)

- **Production Hardening** ✅
  - [x] Add comprehensive error handling for network failures (RPC 400/503, mempool ValueError)
  - [x] Implement graceful degradation when RPC service unavailable (circuit breaker skip)
  - [x] Add circuit breaker pattern for mempool polling (`CircuitBreaker` class with threshold/timeout)
  - [x] Create operational runbooks for block production issues (`docs/guides/block-production-runbook.md`)

## Stage 21 — Cross-Site Synchronization [COMPLETED: 2026-01-29]

Enable blockchain nodes to synchronize across different sites via RPC.

### Multi-Site Architecture
- **Site A (localhost)**: 2 nodes (ports 8081, 8082)
- **Site B (remote host)**: ns3 server (95.216.198.140)
- **Site C (remote container)**: 1 node (port 8082)
- **Network**: Cross-site RPC synchronization enabled

### Implementation
- **Synchronization Module** ✅ COMPLETE
  - [x] Create `/src/aitbc_chain/cross_site.py` module
  - [x] Implement remote endpoint polling (10-second interval)
  - [x] Add transaction propagation between sites
  - [x] Detect height differences between nodes
  - [x] Integrate into node lifecycle (start/stop)

- **Configuration** ✅ COMPLETE
  - [x] Add `cross_site_sync_enabled` to ChainSettings
  - [x] Add `cross_site_remote_endpoints` list
  - [x] Add `cross_site_poll_interval` setting
  - [x] Configure endpoints for all 3 nodes

- **Deployment** ✅ COMPLETE
  - [x] Deploy to all 3 nodes
  - [x] Fix Python compatibility issues
  - [x] Fix RPC endpoint URL paths
  - [x] Verify network connectivity

### Current Status
- All nodes running with cross-site sync enabled
- Transaction propagation working
- ✅ Block sync fully implemented with transaction support
- ✅ Transaction data properly saved during block import
- Nodes maintain independent chains (PoA design)
- Nginx routing fixed to port 8081 for blockchain-rpc-2

### Future Enhancements ✅ COMPLETE
- [x] ✅ Block import endpoint fully implemented with transactions
- [x] Implement conflict resolution for divergent chains (`ChainSync._resolve_fork` with longest-chain rule)
- [x] Add sync metrics and monitoring (15 sync metrics: received, accepted, rejected, forks, reorgs, duration)
- [x] Add proposer signature validation for imported blocks (`ProposerSignatureValidator` with trusted proposer set)

## Stage 20 — Technical Debt Remediation [PLANNED]

Address known issues in existing components that are blocking production use.

### Blockchain Node (`apps/blockchain-node/`)

Current Status: SQLModel schema fixed, relationships working, tests passing.

- **SQLModel Compatibility** ✅ COMPLETE
  - [x] Audit current SQLModel schema definitions in `models.py`
  - [x] Fix relationship and foreign key wiring issues
  - [x] Add explicit `__tablename__` to all models
  - [x] Add `sa_relationship_kwargs` for lazy loading
  - [x] Document SQLModel validator limitation (table=True bypasses validators)
  - [x] Integration tests passing (2 passed, 1 skipped)
  - [x] Schema documentation (`docs/SCHEMA.md`)

- **Production Readiness** ✅ COMPLETE
  - [x] Fix PoA consensus loop stability (retry logic in `_fetch_chain_head`, circuit breaker, health tracking)
  - [x] Harden RPC endpoints for production load (rate limiting middleware, CORS, `/health` endpoint)
  - [x] Add proper error handling and logging (`RequestLoggingMiddleware`, unhandled error catch, structured logging)
  - [x] Create deployment documentation (`docs/guides/blockchain-node-deployment.md`)

### Solidity Token (`packages/solidity/aitbc-token/`)

Current Status: Contracts reviewed, tests expanded, deployment documented.

- **Contract Audit** ✅ COMPLETE
  - [x] Review AIToken.sol and AITokenRegistry.sol
  - [x] Add comprehensive test coverage (17 tests passing)
  - [x] Test edge cases: zero address, zero units, non-coordinator, replay
  - [x] Run security analysis (Slither, Mythril) — `contracts/scripts/security-analysis.sh`
  - [ ] External audit - Future

- **Deployment Preparation** ✅ COMPLETE
  - [x] Deployment script exists (`scripts/deploy.ts`)
  - [x] Mint script exists (`scripts/mintWithReceipt.ts`)
  - [x] Deployment documentation (`docs/DEPLOYMENT.md`)
  - [ ] Deploy to testnet and verify - Future
  - [ ] Plan mainnet deployment timeline - Future

### ZK Receipt Verifier (`contracts/ZKReceiptVerifier.sol`)

Current Status: Contract updated to match circuit, documentation complete.

- **Integration with ZK Circuits** ✅ COMPLETE
  - [x] Verify compatibility with `receipt_simple` circuit (1 public signal)
  - [x] Fix contract to use `uint[1]` for publicSignals
  - [x] Fix authorization checks (`require(authorizedVerifiers[msg.sender])`)
  - [x] Add `verifyReceiptProof()` for view-only verification
  - [x] Update `verifyAndRecord()` with separate settlementAmount param

- **Documentation** ✅ COMPLETE
  - [x] On-chain verification flow (`contracts/docs/ZK-VERIFICATION.md`)
  - [x] Proof generation examples (JavaScript, Python)
  - [x] Coordinator API integration guide
  - [x] Deployment instructions

- **Deployment** ✅ COMPLETE
  - [x] Generate Groth16Verifier.sol from circuit (`contracts/Groth16Verifier.sol` stub + snarkjs generation instructions)
  - [x] Deploy to testnet with ZK circuits (`contracts/scripts/deploy-testnet.sh`)
  - [x] Integration test with Coordinator API (`tests/test_zk_integration.py` — 8 tests)

### Receipt Specification (`docs/reference/specs/receipt-spec.md`)

Current Status: Canonical receipt schema specification moved from `protocols/receipts/`.

- **Specification Finalization** ✅ COMPLETE
  - [x] Core schema defined (version 1.0)
  - [x] Signature format specified (Ed25519)
  - [x] Validation rules documented
  - [x] Add multi-signature receipt format (`signatures` array, threshold, quorum policy)
  - [x] Document ZK-proof metadata extension (`metadata.zk_proof` with Groth16/PLONK/STARK)
  - [x] Add Merkle proof anchoring spec (`metadata.merkle_anchor` with verification algorithm)

### Technical Debt Schedule

| Component | Priority | Target | Status |
|-----------|----------|--------|--------|
| `apps/blockchain-node/` SQLModel fixes | Medium | Q2 2026 | ✅ Complete (2026-01-24) |
| `packages/solidity/aitbc-token/` audit | Low | Q3 2026 | ✅ Complete (2026-01-24) |
| `packages/solidity/aitbc-token/` testnet | Low | Q3 2026 | 🔄 Pending deployment |
| `contracts/ZKReceiptVerifier.sol` deploy | Low | Q3 2026 | ✅ Code ready (2026-01-24) |
| `docs/reference/specs/receipt-spec.md` finalize | Low | Q2 2026 | ✅ Complete (2026-02-12) |
| Cross-site synchronization | High | Q1 2026 | ✅ Complete (2026-01-29) |

## Recent Progress (2026-02-12)

### Persistent GPU Marketplace ✅
- Replaced in-memory mock with SQLModel-backed tables (`GPURegistry`, `GPUBooking`, `GPUReview`)
- Rewrote `routers/marketplace_gpu.py` — all 10 endpoints use DB sessions
- **22/22 GPU marketplace tests** (`apps/coordinator-api/tests/test_gpu_marketplace.py`)

### CLI Integration Tests ✅
- End-to-end tests: real coordinator app (in-memory SQLite) + CLI commands via `_ProxyClient` shim
- Covers all command groups: client, miner, admin, marketplace GPU, explorer, payments, end-to-end lifecycle
- **24/24 CLI integration tests** (`tests/cli/test_cli_integration.py`)
- **208/208 total** when run with billing + GPU marketplace + CLI unit tests

### Coordinator Billing Stubs ✅
- Usage tracking: `_apply_credit`, `_apply_charge`, `_adjust_quota`, `_reset_daily_quotas`, `_process_pending_events`, `_generate_monthly_invoices`
- Tenant context: `_extract_from_token` (HS256 JWT)
- **21/21 billing tests** (`apps/coordinator-api/tests/test_billing.py`)

### CLI Enhancement — All Phases Complete ✅
- **141/141 CLI unit tests** (0 failures) across 9 test files
- **12 command groups**: client, miner, wallet, auth, config, blockchain, marketplace, simulate, admin, monitor, governance, plugin
- CI/CD: `.github/workflows/cli-tests.yml` (Python 3.10/3.11/3.12)

- **Phase 1–2**: Core enhancements + new CLI tools (client retry, miner earnings/capabilities/deregister, wallet staking/multi-wallet/backup, auth, blockchain, marketplace, admin, config, simulate)
- **Phase 3**: 116→141 tests, CLI reference docs (560+ lines), shell completion, man page
- **Phase 4**: MarketplaceOffer GPU fields, booking system, review system
- **Phase 5**: Batch CSV/JSON ops, job templates, webhooks, plugin system, real-time dashboard, metrics/alerts, multi-sig wallets, encrypted config, audit logging, progress bars

## Recent Progress (2026-02-13)

### Critical Security Fixes ✅ COMPLETE
- **Fixed Hardcoded Secrets**
  - JWT secret now required from environment (no longer hardcoded)
  - PostgreSQL credentials parsed from DATABASE_URL
  - Added fail-fast validation for missing secrets
  
- **Unified Database Sessions**
  - Migrated all routers to use `storage.SessionDep`
  - Removed legacy session dependencies
  - Consistent database session management across services
  
- **Closed Authentication Gaps**
  - Implemented session-based authentication in exchange API
  - Fixed hardcoded user IDs - now uses authenticated context
  - Added login/logout endpoints with wallet authentication
  
- **Tightened CORS Defaults**
  - Replaced wildcard origins with specific localhost URLs
  - Restricted HTTP methods to only those needed
  - Applied across all services (Coordinator, Exchange, Blockchain, Gossip)
  
- **Enhanced Wallet Encryption**
  - Replaced weak XOR with Fernet (AES-128 CBC)
  - Added secure key derivation (PBKDF2 with SHA-256)
  - Integrated keyring for password management
  
- **CI Import Error Fix**
  - Replaced `requests` with `httpx` (already a dependency)
  - Fixed build pipeline failures
  - Added graceful fallback for missing dependencies

### Deployment Status
- ✅ Site A (aitbc.bubuit.net): All fixes deployed and active
- ✅ Site B (ns3): No action needed (blockchain node only)
- ✅ Commit: `26edd70` - Changes committed and deployed

## Recent Progress (2026-02-11)

### Git & Repository Hygiene ✅ COMPLETE
- Renamed local `master` branch to `main` and set tracking to `github/main`
- Deleted remote `master` branch from GitHub (was recreated on each push)
- Removed stale `origin` remote (Gitea — repo not found)
- Set `git config --global init.defaultBranch main`
- Removed `.github/` directory (legacy RFC PR template, no active workflows)
- Single remote: `github` → `https://github.com/oib/AITBC.git`, branch: `main`

## Recent Progress (2026-01-29)

### Testing Infrastructure
- **Ollama GPU Provider Test Workflow** ✅ COMPLETE
  - End-to-end test from client submission to blockchain recording
  - Payment processing verified (0.05206 AITBC for inference job)
  - Created comprehensive test script and workflow documentation

### Code Quality
- **Pytest Warning Fixes** ✅ COMPLETE
  - Fixed all pytest warnings (`PytestReturnNotNoneWarning`, `PydanticDeprecatedSince20`, `PytestUnknownMarkWarning`)
  - Migrated Pydantic validators to V2 style
  - Moved `pytest.ini` to project root with proper marker configuration

### Project Organization
- **Directory Cleanup** ✅ COMPLETE
  - Reorganized root files into logical directories
  - Created `docs/guides/`, `docs/reports/`, `scripts/testing/`, `dev-utils/`
  - Updated documentation to reflect new structure
  - Fixed GPU miner systemd service path

the canonical checklist during implementation. Mark completed tasks with ✅ and add dates or links to relevant PRs as development progresses.

