# Completed Deployments

This document tracks components that have been successfully deployed and are operational.

## Container Services (aitbc.bubuit.net)

- ✅ **Main Website** - Deployed at https://aitbc.bubuit.net/
  - Static HTML/CSS with responsive design
  - Features overview, architecture, roadmap, platform status
  - Documentation portal integrated

- ✅ **Explorer Web** - Deployed at https://aitbc.bubuit.net/explorer/
  - Full-featured blockchain explorer
  - Mock data with genesis block (height 0) displayed
  - Blocks, transactions, addresses, receipts tracking
  - Mock/live data toggle functionality (live mode backed by Coordinator API)
  - Live API (nginx): `/api/explorer/*`

- ✅ **Marketplace Web** - Deployed at https://aitbc.bubuit.net/marketplace/
  - Vite + TypeScript frontend
  - Offer list, bid form, stats cards
  - Mock data fixtures with API abstraction
  - Integration tests now connect to live marketplace

- ✅ **Coordinator API** - Deployed in container
  - FastAPI service running on port 8000
  - Health endpoint: `/api/v1/health` returns `{"status":"ok","env":"dev"}`
  - nginx proxy: `/api/` routes to container service (so `/api/v1/*` works)
  - Explorer API (nginx): `/api/explorer/*` → backend `/v1/explorer/*`
  - Users API: `/api/v1/users/*` (compat: `/api/users/*` for Exchange)
  - ZK Applications API: /api/zk/ endpoints for privacy-preserving features
  - Integration tests use real ZK proof features

- ✅ **Wallet Daemon** - Deployed in container
  - FastAPI service with encrypted keystore (Argon2id + XChaCha20-Poly1305)
  - REST and JSON-RPC endpoints for wallet management
  - Mock ledger adapter with SQLite backend
  - Running on port 8002, nginx proxy: /wallet/
  - Dependencies: aitbc-sdk, aitbc-crypto, fastapi, uvicorn
  - Bitcoin payment gateway implemented

- ✅ **Documentation** - Deployed at https://aitbc.bubuit.net/docs/
  - Split documentation for different audiences
  - Miner, client, developer guides
  - API references and technical specs

- ✅ **Trade Exchange** - Deployed at https://aitbc.bubuit.net/Exchange/
  - Bitcoin wallet integration for AITBC purchases
  - User management system with individual wallets
  - QR code generation for payments
  - Real-time payment monitoring
  - Session-based authentication
  - Exchange rate: 1 BTC = 100,000 AITBC

## Integration Tests

- ✅ **Test Suite Updates** - Completed 2026-01-26
  - Security tests now use real ZK proof features
  - Marketplace tests connect to live service
  - Performance tests removed (too early)
  - Wallet-coordinator integration added to roadmap
  - 6 tests passing, 1 skipped (wallet integration)

- ✅ **ZK Applications** - Privacy-preserving features deployed
  - Circom compiler v2.2.3 installed
  - ZK circuits compiled (receipt_simple with 300 constraints)
  - Trusted setup ceremony completed (Powers of Tau)
  - Available features:
    - Identity commitments
    - Stealth addresses
    - Private receipt attestation
    - Group membership proofs
    - Private bidding
    - Computation proofs
  - API endpoints: /api/zk/

## Host Services (GPU Access)

- ✅ **Blockchain Node** - Running on host
  - SQLModel-based blockchain with PoA consensus
  - RPC API on ports 8081/8082 (proxied via /rpc/ and /rpc2/)
  - Mock coordinator on port 8090 (proxied via /v1/)
  - Devnet scripts and observability hooks
  - Cross-site RPC synchronization enabled
  - Transaction propagation between sites
- ✅ **Host GPU Miner** - Running on host (RTX 4060 Ti)
  - Real GPU inference via Ollama
  - Connects to container coordinator through Incus proxy on `127.0.0.1:18000`
  - Receives jobs, submits results, and completes successfully

## Infrastructure

- ✅ **Incus Container** - 'aitbc' container deployed
  - RAID1 configuration for data redundancy
  - nginx reverse proxy for all web services
  - Bridge networking (10.1.223.1 gateway)

- ✅ **nginx Configuration** - All routes configured
  - /explorer/ → Explorer Web
  - /marketplace/ → Marketplace Web  
  - /api/ → Coordinator API (container)
  - /api/v1/ → Coordinator API (container)
  - /api/explorer/ → Explorer API (container)
  - /api/users/ → Users API (container, Exchange compatibility)
  - /api/zk/ → ZK Applications API (container)
  - /rpc/ → Blockchain RPC (host)
  - /v1/ → Mock Coordinator (host)
  - /wallet/ → Wallet Daemon (container)
  - /docs/ → Documentation portal

- ✅ **SSL/HTTPS** - Configured and working
  - All services accessible via https://aitbc.bubuit.net/
  - Proper security headers implemented

- ✅ **DNS Resolution** - Fully operational
  - All endpoints accessible via domain name
  - SSL certificates properly configured

## Deployment Architecture

- **Container Services**: Public web access, no GPU required
  - Website, Explorer, Marketplace, Coordinator API, Wallet Daemon, Docs, ZK Apps
- **Host Services**: GPU access required, private network
  - Blockchain Node, Mining operations
- **nginx Proxy**: Routes requests between container and host
  - Seamless user experience across all services

## Current Status

**Production Ready**: All core services deployed and operational
- ✅ 9 container services running (including ZK Applications and Trade Exchange)
- ✅ 2 host services running (blockchain node + GPU miner)
- ✅ Complete nginx proxy configuration
- ✅ SSL/HTTPS fully configured
- ✅ DNS resolution working
- ✅ Trade Exchange with Bitcoin integration
- ✅ Zero-Knowledge proof capabilities enabled
- ✅ Explorer live API integration complete

## Remaining Tasks

- Fix full Coordinator API codebase import issues (low priority)
- Fix Blockchain Node SQLModel/SQLAlchemy compatibility issues (low priority)
- Configure additional monitoring and observability
- Set up automated backup procedures

## Recent Updates (2026-01-29)

### Cross-Site Synchronization Implementation
- ✅ **Multi-site Deployment**: Successfully deployed cross-site synchronization across 3 nodes
- ✅ **Technical Implementation**: 
  - Created `/src/aitbc_chain/cross_site.py` module
  - Integrated into node lifecycle in `main.py`
  - Added configuration in `config.py`
  - Added `/blocks/import` POST endpoint in `router.py`
- ✅ **Network Configuration**:
  - Local nodes: https://aitbc.bubuit.net/rpc/, /rpc2/
  - Remote node: http://aitbc.keisanki.net/rpc/
- ✅ **Current Status**: 
  - Transaction sync working
  - ✅ Block import endpoint fully functional with transaction support
  - ✅ Transaction data properly saved to database during block import
  - Endpoint validates blocks and handles imports correctly
  - Node heights: Local (771153), Remote (40324)
  - Nginx routing fixed to port 8081 for blockchain-rpc-2

- ✅ **Technical Fixes Applied**
  - Fixed URL paths for correct RPC endpoint access
  - Integrated sync lifecycle into main node process
  - Resolved Python compatibility issues (removed AbstractAsyncContextManager)

- ✅ **Network Configuration**
  - Site A (localhost): https://aitbc.bubuit.net/rpc/ and /rpc2/
  - Site C (remote): http://aitbc.keisanki.net/rpc/
  - All nodes maintain independent chains (PoA design)
  - Cross-site sync enabled with 10-second polling interval

## Recent Updates (2026-01-28)

### Transaction-Dependent Block Creation
- ✅ **PoA Proposer Enhancement** - Modified blockchain nodes to only create blocks when transactions are pending
  - Updated PoA proposer to check RPC mempool before creating blocks
  - Implemented HTTP polling mechanism to check mempool size every 2 seconds
  - Added transaction storage in blocks with proper tx_count field
  - Fixed syntax errors and import issues in poa.py
  - Node 1 now active and operational with new block creation logic
  - Eliminates empty blocks from the blockchain

- ✅ **Architecture Implementation**
  - RPC Service (port 8082): Receives and stores transactions in in-memory mempool
  - Node Process: Checks RPC metrics endpoint for mempool_size
  - If mempool_size > 0: Creates block with transactions
  - If mempool_size == 0: Skips block creation, logs "No pending transactions"
  - Removes processed transactions from mempool after block creation

## Recent Updates (2026-01-21)

### Service Maintenance and Fixes

- ✅ **Container Service Recovery** - Fixed all failing AITBC services
  - Resolved duplicate service conflicts (aitbc-coordinator-api, aitbc-exchange-frontend)
  - Fixed marketplace service by creating proper server.py file
  - Identified and disabled redundant services to prevent port conflicts
  - All essential services now running correctly

- ✅ **Service Status Summary**:
  - aitbc-blockchain.service - Running ✅
  - aitbc-exchange-api.service - Running ✅
  - aitbc-exchange.service - Running ✅
  - aitbc-marketplace.service - Running ✅ (Fixed)
  - aitbc-miner-dashboard.service - Running ✅
  - coordinator-api.service - Running ✅
  - wallet-daemon.service - Running ✅

- ✅ **SSH Access Configuration** - Set up passwordless SSH access
  - Created dedicated SSH key for Cascade automation
  - Configured SSH alias 'aitbc-cascade' for seamless access
  - Enabled secure service management and monitoring

### Skills Framework Implementation (2025-01-19)

- ✅ **Deploy-Production Skill** - Created comprehensive deployment workflow skill
  - Location: `.windsurf/skills/deploy-production/`
  - Features: Pre-deployment checks, environment templates, rollback procedures
  - Scripts: `pre-deploy-checks.sh`, `health-check.py`
  use cases: Automated production deployments with safety checks

- ✅ **Blockchain-Operations Skill** - Created blockchain operations management skill
  - Location: `.windsurf/skills/blockchain-operations/`
  - Features: Node health monitoring, transaction debugging, mining optimization
  - Scripts: `node-health.sh`, `tx-tracer.py`, `mining-optimize.sh`, `sync-monitor.py`, `network-diag.py`
  - Use cases: Node management, mining optimization, network diagnostics

### Skills Benefits

- Standardized workflows for complex operations
- Automated safety checks and validation
- Comprehensive documentation and error handling
- Integration with Cascade for intelligent execution

## Recent Updates (2026-01-23)

- ✅ **Host GPU Miner (Real GPU)**
  - Host miner runs on RTX 4060 Ti with Ollama inference.
  - Uses Incus proxy on `127.0.0.1:18000` to reach the container coordinator.
  - Result submission fixed and jobs complete successfully.
- ✅ **Coordinator Systemd Alignment**
  - `coordinator-api.service` enabled in container for startup on boot.
  - Legacy `aitbc-coordinator-api.service` removed to avoid conflicts.
- ✅ **Proxy Health Check (Host)**
  - Added systemd timer `aitbc-coordinator-proxy-health.timer` to monitor proxy availability.

## Recent Updates (2026-01-24)

### Ollama GPU Inference End-to-End Testing
- ✅ **Complete Workflow Verification**
  - Job submission via CLI → Coordinator API → Miner polling → Ollama inference → Result submission → Receipt generation → Blockchain recording
  - Successfully processed test job in 11.12 seconds with 218 tokens
  - Receipt generated with proper payment amounts: 11.846 gpu_seconds @ 0.02 AITBC = 0.23692 AITBC
  
- ✅ **Bash CLI Wrapper Script**
  - Created unified CLI tool at `/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh`
  - Commands: submit, status, browser, blocks, receipts, cancel, admin-miners, admin-jobs, admin-stats, health
  - Environment variable overrides for URL and API keys
  - Made executable and documented in localhost testing scenario

- ✅ **Coordinator API Bug Fix**
  - Fixed `NameError: name '_coerce_float' is not defined` in receipt service
  - Added missing helper function to `/opt/coordinator-api/src/app/services/receipts.py`
  - Deployed fix to incus container via SSH
  - Result submission now returns 200 OK instead of 500 Internal Server Error

- ✅ **Miner Configuration Fix**
  - Updated miner ID from `host-gpu-miner` to `REDACTED_MINER_KEY` for proper job assignment
  - Added explicit flush logging handler for better systemd journal visibility
  - Enhanced systemd unit with unbuffered logging environment variables

- ✅ **Blockchain-Operations Skill Enhancement**
  - Updated skill with comprehensive Ollama testing scenarios
  - Created detailed test documentation in `ollama-test-scenario.md`
  - Added end-to-end test automation script template
  - Documented common issues, troubleshooting, and performance metrics

- ✅ **Documentation Updates**
  - Updated `docs/developer/testing/localhost-testing-scenario.md` with CLI wrapper usage
  - Converted all examples to use localhost URLs (127.0.0.1) instead of production
  - Added host user paths and quick start commands
  - Documented complete testing workflow from setup to verification

### Explorer Live Data Integration
- ✅ **Explorer API Integration**
  - Switched explorer from mock data to live Coordinator API
  - Fixed receipt display: jobId, miner, payment amounts now shown correctly
  - Fixed address balances: calculated from actual job receipts
  - Updated all page text to indicate "Live data from AITBC coordinator API"

- ✅ **CLI Tool Enhancement**
  - Added `admin-cancel-running` command to cancel all hanging jobs at once
  - Useful for cleaning up stuck jobs from dev/test sessions

### Repository Reorganization
- ✅ **Root Level Cleanup** - Moved 60+ loose files to proper directories
  - `scripts/deploy/` - 9 deployment scripts
  - `scripts/gpu/` - 13 GPU miner files
  - `scripts/test/` - 7 test/verify scripts
  - `scripts/service/` - 7 service management scripts
  - `systemd/` - 4 systemd service files
  - `infra/nginx/` - 5 nginx config files
  - `website/dashboards/` - 2 dashboard HTML files
  - `docs/` - 8 documentation MD files

- ✅ **Website/Docs Folder Structure**
  - Moved HTML documentation to `/website/docs/`
  - Created shared CSS: `/website/docs/css/docs.css` (1232 lines)
  - Created theme toggle JS: `/website/docs/js/theme.js`
  - Migrated all HTML files to use external CSS (reduced file sizes 45-66%)
  - Cleaned `/docs/` folder to only contain mkdocs markdown files

- ✅ **Dark Theme Fixes**
  - Fixed background color consistency across all docs pages
  - Added dark theme support to `full-documentation.html`
  - Fixed Quick Start section cascade styling in docs-miners.html
  - Fixed SDK Examples cascade indentation in docs-clients.html
  - Updated API endpoint example to use Python/FastAPI (matches actual codebase)

- ✅ **Path References Updated**
  - Updated systemd service file with new `scripts/gpu/gpu_miner_host.py` path
  - Updated skill documentation with new file locations
  - Updated localhost-testing-scenario.md with correct paths

- ✅ **Comprehensive .gitignore**
  - Expanded from 39 to 145 lines with organized sections
  - Added project-specific rules for coordinator, explorer, GPU miner

### Repository File Audit & Cleanup
- ✅ **File Audit Document** (`docs/files.md`)
  - Created comprehensive audit of all 849 repository files
  - Categorized into Whitelist (60), Greylist (0), Placeholders (12), Removed (35)
  - All greylist items resolved - no pending reviews

- ✅ **Abandoned Folders Removed** (35 items total)
  - `ecosystem*/` (4 folders), `enterprise-connectors/`, `research/`
  - `apps/client-web/`, `apps/marketplace-ui/`, `apps/wallet-cli/`
  - `apps/miner-node/`, `apps/miner-dashboard/`
  - `packages/py/aitbc-core/`, `aitbc-p2p/`, `aitbc-scheduler/`
  - `packages/js/ui-widgets/`
  - `python-sdk/`, `windsurf/`, `configs/`, `docs/user-guide/`, `docs/bootstrap/`
  - `api/`, `governance/`, `protocols/`
  - 5 GPU miner variants, 3 extension variants

- ✅ **Docs Folder Reorganization**
  - Root now contains only: `done.md`, `files.md`, `roadmap.md`
  - Created new subfolders: `_config/`, `reference/components/`, `reference/governance/`
  - Created: `operator/deployment/`, `operator/migration/`
  - Created: `developer/testing/`, `developer/integration/`
  - Moved 25 files to appropriate subfolders
  - Moved receipt spec: `protocols/receipts/spec.md` → `docs/reference/specs/receipt-spec.md`

- ✅ **Roadmap Updates**
  - Added Stage 19: Placeholder Content Development
  - Added Stage 20: Technical Debt Remediation (blockchain-node, solidity-token, ZKReceiptVerifier)

### Stage 19: Placeholder Content Development (2026-01-24)

- ✅ **Phase 1: Documentation** (17 files created)
  - User Guides (`docs/user/guides/`): 8 files
    - `getting-started.md`, `job-submission.md`, `payments-receipts.md`, `troubleshooting.md`
  - Developer Tutorials (`docs/developer/tutorials/`): 5 files
    - `building-custom-miner.md`, `coordinator-api-integration.md`
    - `marketplace-extensions.md`, `zk-proofs.md`, `sdk-examples.md`
  - Reference Specs (`docs/reference/specs/`): 4 files
    - `api-reference.md` (OpenAPI 3.0), `protocol-messages.md`, `error-codes.md`

- ✅ **Phase 2: Infrastructure** (8 files created)
  - Terraform Environments (`infra/terraform/environments/`):
    - `staging/main.tf`, `prod/main.tf`, `variables.tf`, `secrets.tf`, `backend.tf`
  - Helm Chart Values (`infra/helm/values/`):
    - `dev/values.yaml`, `staging/values.yaml`, `prod/values.yaml`

- ✅ **Phase 3: Application Components** (13 files created)
  - Pool Hub Service (`apps/pool-hub/src/app/`):
    - `routers/`: miners.py, pools.py, jobs.py, health.py, __init__.py
    - `registry/`: miner_registry.py, __init__.py
    - `scoring/`: scoring_engine.py, __init__.py
  - Coordinator Migrations (`apps/coordinator-api/migrations/`):
    - `001_initial_schema.sql`, `002_indexes.sql`, `003_data_migration.py`, `README.md`

### Stage 20: Technical Debt Remediation (2026-01-24)

- ✅ **Blockchain Node SQLModel Fixes**
  - Fixed `models.py`: Added `__tablename__`, proper `Relationship` definitions
  - Fixed type hints: `List["Transaction"]` instead of `list["Transaction"]`
  - Added `sa_relationship_kwargs={"lazy": "selectin"}` for efficient loading
  - Updated tests: 2 passing, 1 skipped (SQLModel validator limitation documented)
  - Created `docs/SCHEMA.md` with ERD and usage examples

- ✅ **Solidity Token Audit**
  - Reviewed `AIToken.sol` and `AITokenRegistry.sol`
  - Added comprehensive tests: 17 tests passing
    - AIToken: 8 tests (minting, replay, zero address, zero units, non-coordinator)
    - AITokenRegistry: 9 tests (registration, updates, access control)
  - Created `docs/DEPLOYMENT.md` with full deployment guide

- ✅ **ZK Receipt Verifier Integration**
  - Fixed `ZKReceiptVerifier.sol` to match `receipt_simple` circuit
  - Updated `publicSignals` to `uint[1]` (1 public signal: receiptHash)
  - Fixed authorization checks: `require(authorizedVerifiers[msg.sender])`
  - Created `contracts/docs/ZK-VERIFICATION.md` with integration guide

### Recent Updates (2026-01-29)

- ✅ **Cross-Site Synchronization Issue Resolved**
  - Fixed database foreign key constraint in transaction/receipt tables
  - Updated import code to use block.id instead of block.height
  - Applied database migration to all nodes
  - Full details in: `docs/issues/2026-01-29_cross-site-sync-resolved.md`

- ✅ **Ollama GPU Provider Test Workflow**
  - Complete end-to-end test from client submission to blockchain recording
  - Created `/home/oib/windsurf/aitbc/home/test_ollama_blockchain.py`
  - Updated skill: `.windsurf/skills/ollama-gpu-provider/SKILL.md` (v2.0)
  - Created workflow: `.windsurf/workflows/ollama-gpu-test.md`
  - Verified payment flow: Client → Miner (0.05206 AITBC for inference)

- ✅ **Issue Management Workflow**
  - Created `.windsurf/workflows/issue-management.md`
  - Established process for tracking and archiving resolved issues
  - Moved resolved cross-site sync issue to `docs/issues/`

- ✅ **Pytest Warning Fixes**
  - Fixed `PytestReturnNotNoneWarning` in `test_blockchain_nodes.py`
  - Fixed `PydanticDeprecatedSince20` by migrating to V2 style validators
  - Fixed `PytestUnknownMarkWarning` by moving `pytest.ini` to project root

- ✅ **Directory Organization**
  - Created `docs/guides/` and moved 2 guide files from root
  - Created `docs/reports/` and moved 10 report files from root
  - Created `scripts/testing/` and moved 13 test scripts from root
  - Created `dev-utils/` and moved `aitbc-pythonpath.pth`
  - Updated `docs/files.md` with new structure
  - Fixed systemd service path for GPU miner
