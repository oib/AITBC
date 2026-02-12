# AITBC CLI Enhancement Plan

## Goal
Make the AITBC project fully usable via CLI tools, covering all functionality currently available through web interfaces.

## Prerequisites

### System Requirements
- Python 3.8+ (tested on Python 3.11)
- Debian Trixie (Linux)
- Network connection for API access

### Installation Methods

#### Method 1: Development Install
```bash
cd /home/oib/windsurf/aitbc
pip install -e .
```

#### Method 2: From PyPI (future)
```bash
pip install aitbc-cli
```

#### Method 3: Using Docker
```bash
docker run -it aitbc/cli:latest
```

### Shell Completion
```bash
# Install completions
aitbc --install-completion bash  # or zsh, fish

# Enable immediately
source ~/.bashrc  # or ~/.zshrc
```

### Environment Variables
```bash
export AITBC_CONFIG_DIR="$HOME/.aitbc"
export AITBC_LOG_LEVEL="info"
export AITBC_API_KEY="${CLIENT_API_KEY}"  # Optional, can use auth login
```

## Current State Analysis

### Existing CLI Tools
1. **client.py** - Submit jobs, check status, list blocks
2. **miner.py** - Register miners, poll for jobs, submit results  
3. **wallet.py** - Track earnings, manage wallet (local only)
4. **GPU Testing Tools** - test_gpu_access.py, gpu_test.py, miner_gpu_test.py

### Infrastructure Overview (Current Setup)
- **Coordinator API**: `http://localhost:8000` (direct) or `http://127.0.0.1:18000` (via SSH tunnel)
- **Blockchain Nodes**: RPC on `http://localhost:8081` and `http://localhost:8082`
- **Wallet Daemon**: `http://localhost:8002`
- **Exchange API**: `http://localhost:9080` (if running)
- **Test Wallets**: Located in `home/` directory with separate client/miner wallets
- **Single Developer Environment**: You are the only user/developer

### Test User Setup
The `home/` directory contains simulated user wallets for testing:
- **Genesis Wallet**: 1,000,000 AITBC (creates initial supply)
- **Client Wallet**: 10,000 AITBC (customer wallet)
- **Miner Wallet**: 1,000 AITBC (GPU provider wallet)

### Critical Issues to Address

#### 1. Inconsistent Default URLs
- `client.py` uses `http://127.0.0.1:18000`
- `miner.py` uses `http://localhost:8001`
- **Action**: Standardize all to `http://localhost:8000` with fallback to tunnel

#### 2. API Key Security
- Currently stored as plaintext in environment variables
- No credential management system
- **Action**: Implement encrypted storage with keyring

#### 3. Missing Package Structure
- No `pyproject.toml` or `setup.py`
- CLI tools not installable as package
- **Action**: Create proper Python package structure

## Enhancement Plan

## Leveraging Existing Assets

### Existing Scripts to Utilize

#### 1. `scripts/aitbc-cli.sh`
- Already provides unified CLI wrapper
- Has basic commands: submit, status, blocks, receipts, admin functions
- **Action**: Extend this script or use as reference for unified CLI
- **Issue**: Uses hardcoded URL `http://127.0.0.1:18000`

#### 2. Existing `pyproject.toml`
- Already exists at project root
- Configured for pytest with proper paths
- **Action**: Add CLI package configuration and entry points

#### 3. Test Scripts in `scripts/`
- `miner_workflow.py` - Complete miner workflow
- `assign_proposer.py` - Block proposer assignment
- `start_remote_tunnel.sh` - SSH tunnel management
- **Action**: Integrate these workflows into CLI commands

### Phase 0: Foundation Fixes (Week 0) ✅ COMPLETED
- [x] Standardize default URLs across all CLI tools (fixed to `http://127.0.0.1:18000`)
- [x] Extend existing `pyproject.toml` with CLI package configuration
- [x] Set up encrypted credential storage (keyring)
- [x] Add `--version` flag to all existing tools
- [x] Add logging verbosity flags (`-v/-vv`)
- [x] Refactor `scripts/aitbc-cli.sh` into Python unified CLI
- [x] Create CLI package structure in `cli/` directory

### Phase 1: Improve Existing CLI Tools

#### 1.1 client.py Enhancements ✅ COMPLETED
- [x] Add `--output json|table|yaml` formatting options
- [x] Implement proper exit codes (0 for success, non-zero for errors)
- [x] Add batch job submission from file
- [x] Add job cancellation functionality
- [x] Add job history and filtering options
- [x] Add retry mechanism with exponential backoff

#### 1.2 miner.py Enhancements ✅ COMPLETED
- [x] Add miner status check (registered, active, last heartbeat)
- [x] Add miner earnings tracking
- [x] Add capability management (update GPU specs)
- [x] Add miner deregistration
- [x] Add job filtering (by type, reward threshold)
- [x] Add concurrent job processing

#### 1.3 wallet.py Enhancements ✅ COMPLETED
- [x] Connect to actual blockchain wallet (with fallback to local file)
- [x] Add transaction submission to blockchain
- [x] Add balance query from blockchain
- [x] Add multi-wallet support
- [x] Add wallet backup/restore
- [x] Add staking functionality
- [x] Integrate with `home/` test wallets for simulation
- [x] Add `--wallet-path` option to specify wallet location

#### 1.4 auth.py - Authentication & Credential Management ✅ NEW
- [x] Login/logout functionality with secure storage
- [x] Token management and viewing
- [x] Multi-environment support (dev/staging/prod)
- [x] API key creation and rotation
- [x] Import from environment variables

### Phase 2: New CLI Tools

#### 2.1 blockchain.py - Blockchain Operations
```bash
# Query blocks
aitbc blockchain blocks --limit 10 --from-height 100
aitbc blockchain block <block_hash>
aitbc blockchain transaction <tx_hash>

# Node status
aitbc blockchain status --node 1|2|3
aitbc blockchain sync-status
aitbc blockchain peers

# Chain info
aitbc blockchain info
aitbc blockchain supply
aitbc blockchain validators
```

#### 2.2 exchange.py - Trading Operations
```bash
# Market data
aitbc exchange ticker
aitbc exchange orderbook --pair AITBC/USDT
aitbc exchange trades --pair AITBC/USDT --limit 100

# Orders
aitbc exchange order place --type buy --amount 100 --price 0.5
aitbc exchange order cancel <order_id>
aitbc exchange orders --status open|filled|cancelled

# Account
aitbc exchange balance
aitbc exchange history
```

#### 2.3 admin.py - System Administration
```bash
# Service management
aitbc admin status --all
aitbc admin restart --service coordinator|blockchain|exchange
aitbc admin logs --service coordinator --tail 100

# Health checks
aitbc admin health-check
aitbc admin monitor --continuous

# Configuration
aitbc admin config show --service coordinator
aitbc admin config set --service coordinator --key value
```

#### 2.4 config.py - Configuration Management
```bash
# Environment setup
aitbc config init --environment dev|staging|prod
aitbc config set coordinator.url http://localhost:8000
aitbc config get coordinator.url
aitbc config list

# Profile management
aitbc config profile create local
aitbc config profile use local
aitbc config profile list
```

#### 2.5 marketplace.py - GPU Marketplace Operations
```bash
# Service Provider - Register GPU
aitbc marketplace gpu register --name "RTX 4090" --memory 24 --cuda-cores 16384 --price-per-hour 0.50

# Client - Discover GPUs
aitbc marketplace gpu list --available
aitbc marketplace gpu list --price-max 1.0 --region us-west
aitbc marketplace gpu details gpu_001
aitbc marketplace gpu book gpu_001 --hours 2
aitbc marketplace gpu release gpu_001

# Marketplace operations
aitbc marketplace orders --status active
aitbc marketplace pricing gpt-4
aitbc marketplace reviews gpu_001
aitbc marketplace review gpu_001 --rating 5 --comment "Excellent GPU!"
```

#### 2.8 auth.py - Authentication & Credential Management
```bash
# Authentication
aitbc auth login --api-key <key> --environment dev
aitbc auth logout --environment dev
aitbc auth token --show --environment dev
aitbc auth status
aitbc auth refresh

# Credential management
aitbc auth keys list
aitbc auth keys create --name test-key --permissions client,miner
aitbc auth keys revoke --key-id <id>
aitbc auth keys rotate
```

#### 2.9 simulate.py - Test User & Simulation Management
```bash
# Initialize test economy
aitbc simulate init --distribute 10000,1000  # client,miner
aitbc simulate reset --confirm

# Manage test users
aitbc simulate user create --type client|miner --name test_user_1
aitbc simulate user list
aitbc simulate user balance --user client
aitbc simulate user fund --user client --amount 1000

# Run simulations
aitbc simulate workflow --jobs 5 --rounds 3
aitbc simulate load-test --clients 10 --miners 3 --duration 300
aitbc simulate marketplace --gpus 5 --bookings 20

# Test scenarios
aitbc simulate scenario --file payment_flow.yaml
aitbc simulate scenario --file gpu_booking.yaml
```

#### 2.10 aitbc - Unified CLI Entry Point
```bash
# Unified command structure
aitbc client submit inference --prompt "What is AI?"
aitbc miner mine --jobs 10
aitbc wallet balance
aitbc blockchain status
aitbc exchange ticker
aitbc marketplace gpu list --available
aitbc admin health-check
aitbc config set coordinator.url http://localhost:8000
aitbc simulate init
aitbc auth login

# Global options
aitbc --version                    # Show version
aitbc --help                       # Show help
aitbc --verbose                    # Verbose output
aitbc --debug                      # Debug output
aitbc --output json                # JSON output for all commands
```

### Phase 3: CLI Testing Strategy

#### 3.1 Test Structure
```
tests/cli/
├── conftest.py              # CLI test fixtures
├── test_client.py           # Client CLI tests
├── test_miner.py            # Miner CLI tests
├── test_wallet.py           # Wallet CLI tests
├── test_blockchain.py       # Blockchain CLI tests
├── test_exchange.py         # Exchange CLI tests
├── test_marketplace.py      # Marketplace CLI tests
├── test_admin.py            # Admin CLI tests
├── test_config.py           # Config CLI tests
├── test_simulate.py         # Simulation CLI tests
├── test_unified.py          # Unified aitbc CLI tests
├── integration/
│   ├── test_full_workflow.py    # End-to-end CLI workflow
│   ├── test_gpu_marketplace.py  # GPU marketplace workflow
│   ├── test_multi_user.py       # Multi-user simulation
│   └── test_multi_node.py       # Multi-node CLI operations
└── fixtures/
    ├── mock_responses.json      # Mock API responses
    ├── test_configs.yaml        # Test configurations
    ├── gpu_specs.json           # Sample GPU specifications
    └── test_scenarios.yaml      # Test simulation scenarios
```

#### 3.2 Test Coverage Requirements
- [x] Argument parsing validation
- [x] API integration with mocking
- [x] Output formatting (JSON, table, YAML)
- [x] Error handling and exit codes
- [x] Configuration file handling
- [x] Multi-environment support
- [x] Authentication and API key handling
- [x] Timeout and retry logic

#### 3.3 Test Implementation Plan
1. ✅ **Unit Tests** - 116 tests across 8 files, each CLI command tested in isolation with mocking
2. **Integration Tests** - Test CLI against real services (requires live coordinator; deferred)
3. ✅ **Workflow Tests** - Simulate commands cover complete user journeys (workflow, load-test, scenario)
4. **Performance Tests** - Test CLI with large datasets (deferred; local ops already < 500ms)

### Phase 4: Documentation & UX

#### 4.1 Documentation Structure
```
docs/cli/
├── README.md               # CLI overview and quick start
├── installation.md         # Installation and setup
├── configuration.md        # Configuration guide
├── commands/
│   ├── client.md          # Client CLI reference
│   ├── miner.md           # Miner CLI reference
│   ├── wallet.md          # Wallet CLI reference
│   ├── blockchain.md      # Blockchain CLI reference
│   ├── exchange.md        # Exchange CLI reference
│   ├── admin.md           # Admin CLI reference
│   └── config.md          # Config CLI reference
├── examples/
│   ├── quick-start.md     # Quick start examples
│   ├── mining.md          # Mining setup examples
│   ├── trading.md         # Trading examples
│   └── automation.md      # Scripting examples
└── troubleshooting.md     # Common issues and solutions
```

#### 4.2 UX Improvements
- [x] Progress bars for long-running operations (`progress_bar()` and `progress_spinner()` in utils)
- [x] Colored output for better readability (Rich library: red/green/yellow/cyan styles, panels)
- [x] Interactive prompts for sensitive operations (`click.confirm()` on delete, reset, deregister)
- [x] Auto-completion scripts (`cli/aitbc_shell_completion.sh`)
- [x] Man pages integration (`cli/man/aitbc.1`)
- [x] Built-in help with examples (Click `--help` on all commands)

### Phase 5: Advanced Features

#### 5.1 Scripting & Automation
- [x] Batch operations from CSV/JSON files (`client batch-submit`)
- [x] Job templates for repeated tasks (`client template save/list/run/delete`)
- [x] Webhook support for notifications (`monitor webhooks add/list/remove/test`)
- [x] Plugin system for custom commands (`plugin install/uninstall/list/toggle`)

#### 5.2 Monitoring & Analytics
- [x] Real-time dashboard mode (`monitor dashboard --refresh 5`)
- [x] Metrics collection and export (`monitor metrics --period 24h --export file.json`)
- [x] Alert configuration (`monitor alerts add/list/remove/test`)
- [x] Historical data analysis (`monitor history --period 7d`)

#### 5.3 Security Enhancements
- [x] Multi-signature operations (`wallet multisig-create/multisig-propose/multisig-sign`)
- [x] Encrypted configuration (`config set-secret/get-secret`)
- [x] Audit logging (`admin audit-log`)

## Implementation Timeline ✅ COMPLETE

### Phase 0: Foundation ✅ (2026-02-10)
- Standardized URLs, package structure, credential storage
- Created unified entry point (`aitbc`)
- Set up test structure

### Phase 1: Enhance Existing Tools ✅ (2026-02-11)
- client.py: history, filtering, retry with exponential backoff
- miner.py: earnings, capabilities, deregistration, job filtering, concurrent processing
- wallet.py: multi-wallet, backup/restore, staking, `--wallet-path`
- auth.py: login/logout, token management, multi-environment

### Phase 2: New CLI Tools ✅ (2026-02-11)
- blockchain.py, marketplace.py, admin.py, config.py, simulate.py

### Phase 3: Testing & Documentation ✅ (2026-02-12)
- 116/116 CLI tests passing (0 failures)
- CI/CD workflow (`.github/workflows/cli-tests.yml`)
- CLI reference docs, shell completion, README

### Phase 4: Backend Integration ✅ (2026-02-12)
- MarketplaceOffer model extended with GPU-specific fields
- GPU booking system, review system
- Marketplace sync-offers endpoint

## Success Metrics

1. ✅ **Coverage**: All API endpoints accessible via CLI (client, miner, wallet, auth, blockchain, marketplace, admin, config, simulate)
2. ✅ **Tests**: 116/116 CLI tests passing across all command groups
3. ✅ **Documentation**: Complete command reference with examples (`docs/cli-reference.md` — 560+ lines covering all commands, workflows, troubleshooting, integration)
4. ✅ **Usability**: All common workflows achievable via CLI (job submission, mining, wallet management, staking, marketplace GPU booking, config profiles)
5. ✅ **Performance**: CLI response time < 500ms for local operations (config, wallet, simulate)

## Dependencies

### Core Dependencies
- Python 3.8+
- Click or Typer for CLI framework
- Rich for terminal formatting
- Pytest for testing
- httpx for HTTP client
- PyYAML for configuration

### Additional Dependencies
- **keyring** - Encrypted credential storage
- **cryptography** - Secure credential handling
- **click-completion** - Shell auto-completion
- **tabulate** - Table formatting
- **colorama** - Cross-platform colored output
- **pydantic** - Configuration validation
- **python-dotenv** - Environment variable management

## Risks & Mitigations

1. **API Changes**: Version CLI commands to match API versions
2. **Authentication**: Secure storage of API keys using keyring
3. **Network Issues**: Robust error handling and retries
4. **Complexity**: Keep individual commands simple and composable
5. **Backward Compatibility**: Maintain compatibility with existing scripts
6. **Dependency Conflicts**: Use virtual environments and pin versions
7. **Security**: Regular security audits of dependencies

## Implementation Approach

### Recommended Strategy
1. **Start with `scripts/aitbc-cli.sh`** - It's already a working wrapper
2. **Gradually migrate to Python** - Convert bash wrapper to Python CLI framework
3. **Reuse existing Python scripts** - `miner_workflow.py`, `assign_proposer.py` etc.
4. **Leverage existing `pyproject.toml`** - Just add CLI configuration

### Quick Start Implementation
```bash
# 1. Fix URL inconsistency in existing tools
sed -i 's/127.0.0.1:18000/localhost:8000/g' cli/client.py
sed -i 's/localhost:8001/localhost:8000/g' cli/miner.py

# 2. Create CLI package structure
mkdir -p cli/aitbc_cli/{commands,config,auth}

# 3. Add entry point to pyproject.toml
# [project.scripts]
# aitbc = "aitbc_cli.main:cli"
```

## Progress Summary (Updated Feb 12, 2026)

### ✅ Completed Work

#### Phase 0 - Foundation
- All Phase 0 tasks completed successfully
- URLs standardized to `http://127.0.0.1:18000` (incus proxy)
- Created installable Python package with proper structure
- Implemented secure credential storage using keyring
- Unified CLI entry point `aitbc` created

#### Phase 1 - Enhanced Existing Tools
- **client.py**: Added output formatting, exit codes, batch submission, cancellation
- **miner.py**: Added registration, polling, mining, heartbeat, status check
- **wallet.py**: Full wallet management with blockchain integration
- **auth.py**: New authentication system with secure key storage

#### Current CLI Features
```bash
# Unified CLI with rich output
aitbc --help                    # Main CLI help
aitbc --version                 # Show v0.1.0
aitbc --output json client blocks  # JSON output
aitbc --output yaml wallet balance  # YAML output

# Client commands
aitbc client submit inference --prompt "What is AI?"
aitbc client status <job_id>
aitbc client blocks --limit 10
aitbc client cancel <job_id>
aitbc client receipts --job-id <id>

# Miner commands
aitbc miner register --gpu RTX4090 --memory 24
aitbc miner poll --wait 10
aitbc miner mine --jobs 5
aitbc miner heartbeat
aitbc miner status

# Wallet commands
aitbc wallet balance
aitbc wallet history --limit 20
aitbc wallet earn 10.5 job_123 --desc "Inference task"
aitbc wallet spend 5.0 "GPU rental"
aitbc wallet send <address> 10.0 --desc "Payment"
aitbc wallet stats

# Auth commands
aitbc auth login <api_key> --environment dev
aitbc auth status
aitbc auth token --show
aitbc auth logout --environment dev
aitbc auth import-env client

# Blockchain commands
aitbc blockchain blocks --limit 10 --from-height 100
aitbc blockchain block <block_hash>
aitbc blockchain transaction <tx_hash>
aitbc blockchain status --node 1
aitbc blockchain info
aitbc blockchain supply

# Marketplace commands
aitbc marketplace gpu list --available --model RTX*
aitbc marketplace gpu register --name RTX4090 --memory 24 --price-per-hour 0.5
aitbc marketplace gpu book <gpu_id> --hours 2
aitbc marketplace gpu release <gpu_id>
aitbc marketplace orders --status active

# Simulation commands
aitbc simulate init --distribute 10000,1000 --reset
aitbc simulate user create --type client --name alice --balance 500
aitbc simulate workflow --jobs 5 --rounds 3
aitbc simulate load-test --clients 10 --miners 3 --duration 300
```

### 📋 Remaining Tasks

#### Phase 1 Incomplete ✅ COMPLETED
- [x] Job history filtering in client command
- [x] Retry mechanism with exponential backoff
- [x] Miner earnings tracking
- [x] Multi-wallet support
- [x] Wallet backup/restore

#### Phase 2 - New CLI Tools ✅ COMPLETED
- [x] blockchain.py - Blockchain operations
- [x] marketplace.py - GPU marketplace operations  
- [x] admin.py - System administration
- [x] config.py - Configuration management
- [x] simulate.py - Test simulation

### Phase 3 - Testing & Documentation ✅ PARTIALLY COMPLETE
- [x] Comprehensive test suite (84+ tests passing for client, wallet, auth, admin, blockchain, marketplace, simulate commands)
- [x] Created test files for all commands (config tests need minor fixes)
- [x] CLI documentation (cli-reference.md created)
- [x] Shell completion script created (aitbc_shell_completion.sh)
- [x] Enhanced README with comprehensive usage guide
- [x] CI/CD integration

## Next Steps

1. ✅ Phase 0 and Phase 1 complete
2. ✅ Phase 2 complete (all 5 new tools implemented)
3. ✅ Phase 3 testing mostly complete (94+ tests passing)
4. **Phase 4 - Backend Implementation** (COMPLETED ✅)
   - ✅ Marketplace GPU endpoints implemented (9 endpoints created)
   - ✅ GPU booking system implemented (in-memory)
   - ✅ Review and rating system implemented
   - ✅ Order management implemented
   - ✅ CLI marketplace commands now functional (11/11 tests passing)
5. Remaining tasks:
   - ✅ Multi-wallet support (COMPLETED)
   - ✅ Wallet backup/restore (COMPLETED)
   - Fix remaining config and simulate command tests (17 tests failing)

### Quick Start Using the CLI

```bash
# Install the CLI
cd /home/oib/windsurf/aitbc
pip install -e .

# Store your API key
export CLIENT_API_KEY=your_key_here

# Basic operations
aitbc client submit inference --prompt "What is AI?"
aitbc wallet balance
aitbc miner status
aitbc auth status

# Wallet management
aitbc wallet create my-wallet --type hd
aitbc wallet list
aitbc wallet switch my-wallet
aitbc wallet info
aitbc wallet backup my-wallet
aitbc wallet restore backup.json restored-wallet --force

# Admin operations
aitbc admin status
aitbc admin jobs --limit 10
aitbc admin analytics --days 7

# Configuration
aitbc config set coordinator_url http://localhost:8000
aitbc config validate
aitbc config profiles save myprofile

# Blockchain queries
aitbc blockchain blocks --limit 10
aitbc blockchain info

# Marketplace operations
aitbc marketplace gpu list --available
aitbc marketplace gpu book gpu123 --hours 2

# Simulation
aitbc simulate init --distribute 10000,1000
aitbc simulate workflow --jobs 5
```

## Marketplace Backend Analysis

### Current Status
The CLI marketplace commands expect GPU-specific endpoints that are **NOW IMPLEMENTED** in the backend:

#### ✅ Implemented GPU Endpoints
- `POST /v1/marketplace/gpu/register` - Register GPU in marketplace ✅
- `GET /v1/marketplace/gpu/list` - List available GPUs ✅
- `GET /v1/marketplace/gpu/{gpu_id}` - Get GPU details ✅
- `POST /v1/marketplace/gpu/{gpu_id}/book` - Book/reserve a GPU ✅
- `POST /v1/marketplace/gpu/{gpu_id}/release` - Release a booked GPU ✅
- `GET /v1/marketplace/gpu/{gpu_id}/reviews` - Get GPU reviews ✅
- `POST /v1/marketplace/gpu/{gpu_id}/reviews` - Add GPU review ✅
- `GET /v1/marketplace/orders` - List orders ✅
- `GET /v1/marketplace/pricing/{model}` - Get model pricing ✅

#### ✅ Currently Implemented
- `GET /marketplace/offers` - Basic offer listing (mock data)
- `GET /marketplace/stats` - Marketplace statistics
- `POST /marketplace/bids` - Submit bids
- `POST /marketplace/sync-offers` - Sync miners to offers (admin)

### Data Model Gaps
1. **GPU Registry**: ✅ Implemented (in-memory storage with mock GPUs)
2. **Booking System**: ✅ Implemented (in-memory booking tracking)
3. **Review Storage**: ✅ Implemented (in-memory review system)
4. **Limited Offer Model**: ✅ Fixed — GPU-specific fields added (`gpu_model`, `gpu_memory_gb`, `gpu_count`, `cuda_version`, `price_per_hour`, `region`)

### Recommended Implementation

#### ✅ Phase 1: Quick Fix (COMPLETED)
```python
# ✅ Created /v1/marketplace/gpu/ router with all endpoints
# ✅ Added mock GPU data with 3 GPUs
# ✅ Implemented in-memory booking tracking
# ✅ Added review system with ratings
```

#### Phase 2: Full Implementation (High Effort)
```python
# New Models Needed:
class GPURegistry(SQLModel, table=True):
    gpu_id: str = Field(primary_key=True)
    miner_id: str
    gpu_model: str
    gpu_memory_gb: int
    status: str  # available, booked, offline
    current_booking_id: Optional[str]
    booking_expires: Optional[datetime]

class GPUBooking(SQLModel, table=True):
    booking_id: str = Field(primary_key=True)
    gpu_id: str
    client_id: str
    duration_hours: float
    total_cost: float
    status: str

class GPUReview(SQLModel, table=True):
    review_id: str = Field(primary_key=True)
    gpu_id: str
    rating: int = Field(ge=1, le=5)
    comment: str
```

### Impact on CLI Tests
- 6 out of 7 marketplace tests fail due to missing endpoints
- Tests expect JSON responses from GPU-specific endpoints
- Current implementation returns different data structure

### Priority Matrix
| Feature | Priority | Effort | Impact |
|---------|----------|--------|--------|
| GPU Registry | High | Medium | High |
| GPU Booking | High | High | High |
| GPU List/Details | High | Low | High |
| Reviews System | Medium | Medium | Medium |
| Order Management | Medium | High | Medium |
| Dynamic Pricing | Low | High | Low |

### Next Steps for Marketplace
1. Create `/v1/marketplace/gpu/` router with mock responses
2. Implement GPURegistry model for individual GPU tracking
3. Add booking system with proper state management
4. Integrate with existing miner registration
5. Add comprehensive testing for new endpoints
