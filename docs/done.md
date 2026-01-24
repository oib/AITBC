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

- ✅ **Coordinator API** - Deployed in container
  - FastAPI service running on port 8000
  - Health endpoint: `/api/v1/health` returns `{"status":"ok","env":"dev"}`
  - nginx proxy: `/api/` routes to container service (so `/api/v1/*` works)
  - Explorer API (nginx): `/api/explorer/*` → backend `/v1/explorer/*`
  - Users API: `/api/v1/users/*` (compat: `/api/users/*` for Exchange)
  - ZK Applications API: /api/zk/ endpoints for privacy-preserving features

- ✅ **Wallet Daemon** - Deployed in container
  - FastAPI service with encrypted keystore (Argon2id + XChaCha20-Poly1305)
  - REST and JSON-RPC endpoints for wallet management
  - Mock ledger adapter with SQLite backend
  - Running on port 8002, nginx proxy: /wallet/
  - Dependencies: aitbc-sdk, aitbc-crypto, fastapi, uvicorn

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
  - RPC API on port 9080 (proxied via /rpc/)
  - Mock coordinator on port 8090 (proxied via /v1/)
  - Devnet scripts and observability hooks
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
