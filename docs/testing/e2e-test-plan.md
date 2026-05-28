# AITBC End-to-End Test Plan

**Version:** 1.0
**Date:** 2026-05-11
**Status:** Draft
**Purpose:** Define comprehensive end-to-end testing strategy for AITBC platform

## Current State

### Existing Test Infrastructure

**Integration Tests Location:** `/opt/aitbc/tests/integration/`

**Existing Test Files:**
- `test_full_workflow.py` - Integration tests for job execution, payment flow, P2P sync, marketplace, security
- `test_agent_coordinator.py` - Agent coordinator integration tests (141KB)
- `test_agent_coordinator_api.py` - Agent coordinator API tests
- `test_blockchain_nodes.py` - Blockchain node integration tests
- `test_staking_lifecycle.py` - Staking lifecycle tests
- `test_working_integration.py` - Working integration tests
- `test_basic_integration.py` - Basic integration tests
- `test_blockchain_simple.py` - Simple blockchain tests
- `test_blockchain_final.py` - Final blockchain tests
- `test_integration_simple.py` - Simple integration tests

### Current Limitations

1. **Mock Clients:** Most integration tests use mock clients rather than real services
2. **Service Dependencies:** Tests require running services (coordinator, blockchain, marketplace, wallet)
3. **No True E2E:** Tests don't span full user journeys from registration to completion
4. **Environment Setup:** No dedicated E2E test environment configuration
5. **Test Data:** No comprehensive test data fixtures for E2E scenarios

## E2E Test Scope

### Test Scenarios

#### 1. User Registration and Wallet Creation
**Objective:** Verify complete user onboarding flow

**Steps:**
1. User registers via CLI
2. Wallet is created automatically
3. Private key is generated and stored securely
4. User receives wallet address
5. User can view wallet balance

**Success Criteria:**
- Registration completes without errors
- Wallet is created with valid address
- Private key is securely stored
- User can access wallet information

**Prerequisites:**
- Coordinator API running
- Wallet daemon running
- Blockchain node running

#### 2. Job Submission and Processing
**Objective:** Verify complete job lifecycle

**Steps:**
1. User submits AI inference job via CLI
2. Job is queued in coordinator
3. Miner picks up job via polling
4. Miner processes job (GPU execution)
5. Miner submits result
6. User receives result
7. Payment is processed

**Success Criteria:**
- Job is successfully submitted
- Job transitions through states: QUEUED → ASSIGNED → PROCESSING → COMPLETED
- Result is returned to user
- Payment is transferred correctly
- Transaction is recorded on blockchain

**Prerequisites:**
- Coordinator API running
- GPU miner running
- Wallet daemon running
- Blockchain node running
- Marketplace service running

#### 3. Payment and Receipt Generation
**Objective:** Verify payment flow and receipt generation

**Steps:**
1. Job is submitted with payment
2. Payment is escrowed in smart contract
3. Job completes successfully
4. Payment is released to miner
5. Receipt is generated
6. Receipt is stored on blockchain
7. User can retrieve receipt

**Success Criteria:**
- Payment is escrowed correctly
- Payment is released on job completion
- Receipt is generated with all required fields
- Receipt is stored on blockchain
- User can retrieve and verify receipt

**Prerequisites:**
- Coordinator API running
- Wallet daemon running
- Blockchain node running
- Smart contracts deployed

#### 4. Miner Registration and Operation
**Objective:** Verify miner onboarding and operation

**Steps:**
1. Miner registers with coordinator
2. Miner provides GPU capabilities
3. Miner creates marketplace offer
4. Miner receives jobs
5. Miner processes jobs
6. Miner receives payments
7. Miner updates capabilities

**Success Criteria:**
- Miner registration succeeds
- Capabilities are recorded correctly
- Marketplace offer is created
- Jobs are assigned to miner
- Payments are received
- Capability updates succeed

**Prerequisites:**
- Coordinator API running
- GPU miner running
- Wallet daemon running
- Marketplace service running
- Blockchain node running

#### 5. Agent Communication
**Objective:** Verify agent-to-agent communication

**Steps:**
1. Agent A registers with coordinator
2. Agent B registers with coordinator
3. Agent A sends message to Agent B
4. Agent B receives message
5. Agent B responds
6. Communication is encrypted
7. Message is logged on blockchain

**Success Criteria:**
- Agents register successfully
- Message is delivered
- Response is received
- Communication is encrypted
- Message is recorded on blockchain

**Prerequisites:**
- Coordinator API running
- Agent daemon running
- Blockchain node running
- Smart contracts deployed

#### 6. Blockchain Transactions
**Objective:** Verify blockchain transaction processing

**Steps:**
1. User initiates transaction
2. Transaction is submitted to blockchain
3. Transaction is validated
4. Transaction is included in block
5. Block is propagated to network
6. Transaction is confirmed
7. Receipt is generated

**Success Criteria:**
- Transaction is submitted successfully
- Transaction is validated
- Transaction is included in block
- Block is propagated
- Transaction is confirmed
- Receipt is generated

**Prerequisites:**
- Blockchain node running (multiple nodes for network testing)
- Wallet daemon running
- Consensus mechanism operational

#### 7. API Interactions
**Objective:** Verify API contract compliance

**Steps:**
1. Test all API endpoints
2. Verify request/response formats
3. Test authentication/authorization
4. Test error handling
5. Test rate limiting
6. Test pagination
7. Test filtering and sorting

**Success Criteria:**
- All endpoints respond correctly
- Request/response formats match API spec
- Authentication/authorization works correctly
- Errors are handled appropriately
- Rate limiting is enforced
- Pagination works correctly
- Filtering and sorting work correctly

**Prerequisites:**
- All API services running
- API documentation available
- Test users with different roles

## Test Environment Setup

### Infrastructure Requirements

#### Hardware
- **Minimum:** 4 CPU cores, 16GB RAM, 100GB storage
- **Recommended:** 8 CPU cores, 32GB RAM, 500GB storage
- **GPU:** NVIDIA GPU with CUDA support (for miner testing)

#### Software
- **Operating System:** Debian stable (bookworm)
- **Python:** 3.13 or 3.14
- **PostgreSQL:** 15 or later
- **Redis:** 7 or later

### Services Required

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| Coordinator API | 8011 | Job management | Required |
| Blockchain Node | 8080 | Blockchain RPC | Required |
| Wallet Daemon | 8081 | Wallet management | Required |
| GPU Miner | - | Job processing | Required |
| Marketplace | 8102 | Service marketplace | Required |
| Exchange | 8082 | Trading platform | Required |
| Agent Coordinator | 8011 | Agent management | Required |
| PostgreSQL | 5432 | Database | Required |
| Redis | 6379 | Cache | Required |

### Service Orchestration (Systemd)

AITBC uses systemd for service orchestration. Services are managed via systemd unit files.

#### Starting Services

```bash
# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Start Redis
sudo systemctl start redis
sudo systemctl enable redis

# Start AITBC services
sudo systemctl start aitbc-blockchain-node
sudo systemctl start aitbc-coordinator-api
sudo systemctl start aitbc-marketplace
sudo systemctl start aitbc-exchange

# Check service status
sudo systemctl status aitbc-blockchain-node
sudo systemctl status aitbc-coordinator-api
sudo systemctl status aitbc-marketplace
```

#### Service Health Checks

```bash
# Check coordinator API
curl -s http://localhost:8011/v1/health

# Check blockchain node
curl -s http://localhost:8080/v1/health

# Check marketplace
curl -s http://localhost:8102/v1/health
```

### Configuration

#### Environment Variables
```bash
# Coordinator API
COORDINATOR_URL=http://localhost:8011
CLIENT_API_KEY=test-api-key
ADMIN_API_KEY=test-admin-key

# Blockchain
BLOCKCHAIN_URL=http://localhost:8080
BLOCKCHAIN_DATA_DIR=/tmp/blockchain-test

# Wallet
WALLET_DAEMON_URL=http://localhost:8081
WALLET_DATA_DIR=/tmp/wallet-test

# Marketplace
MARKETPLACE_URL=http://localhost:8102

# Database
POSTGRES_URL=postgresql://aitbc:test@localhost:5432/aitbc_test
REDIS_URL=redis://localhost:6379/0
```

#### Test Data
- Test users with different roles
- Test wallets with pre-funded accounts
- Test blockchain state (genesis block)
- Test marketplace offers
- Test job templates

## Test Implementation

### Test Framework

**Recommended Framework:** pytest with pytest-asyncio

**Additional Tools:**
- `httpx` for HTTP client
- `playwright` for browser automation (if UI testing needed)
- Systemd services for service orchestration

### Test Structure

```
tests/e2e/
├── conftest.py                 # E2E fixtures and configuration
├── test_user_registration.py   # User registration E2E tests
├── test_job_lifecycle.py       # Job submission and processing E2E tests
├── test_payment_flow.py        # Payment and receipt E2E tests
├── test_miner_operations.py    # Miner registration and operation E2E tests
├── test_agent_communication.py # Agent communication E2E tests
├── test_blockchain_transactions.py # Blockchain transaction E2E tests
├── test_api_compliance.py      # API contract compliance E2E tests
├── fixtures/                   # Test data fixtures
│   ├── users.py
│   ├── wallets.py
│   ├── jobs.py
│   └── blockchain.py
└── utils/                      # Test utilities
    ├── helpers.py
    └── assertions.py
```

### Sample Test Structure

```python
import pytest
import httpx
from datetime import datetime, timedelta

@pytest.mark.e2e
class TestJobLifecycle:
    """End-to-end test for complete job lifecycle"""
    
    @pytest.fixture
    async def client(self):
        """HTTP client for API calls"""
        async with httpx.AsyncClient() as client:
            yield client
    
    async def test_complete_job_execution(self, client):
        """Test complete job from submission to completion"""
        # 1. Submit job
        job_data = {
            "payload": {
                "job_type": "ai_inference",
                "parameters": {
                    "model": "gpt-4",
                    "prompt": "Test prompt",
                    "max_tokens": 100
                }
            },
            "ttl_seconds": 900
        }
        
        response = await client.post(
            "http://localhost:8011/v1/jobs",
            json=job_data,
            headers={"X-Api-Key": "test-api-key"}
        )
        assert response.status_code == 201
        job = response.json()
        job_id = job["job_id"]
        
        # 2. Wait for job assignment
        await self._wait_for_job_state(client, job_id, "ASSIGNED", timeout=60)
        
        # 3. Wait for job completion
        await self._wait_for_job_state(client, job_id, "COMPLETED", timeout=300)
        
        # 4. Verify result
        response = await client.get(
            f"http://localhost:8011/v1/jobs/{job_id}",
            headers={"X-Api-Key": "test-api-key"}
        )
        assert response.status_code == 200
        job = response.json()
        assert job["state"] == "COMPLETED"
        assert "result" in job
        
        # 5. Verify payment
        response = await client.get(
            f"http://localhost:8011/v1/jobs/{job_id}/payment",
            headers={"X-Api-Key": "test-api-key"}
        )
        assert response.status_code == 200
        payment = response.json()
        assert payment["status"] == "completed"
    
    async def _wait_for_job_state(self, client, job_id, expected_state, timeout):
        """Wait for job to reach expected state"""
        start = datetime.now()
        while (datetime.now() - start).total_seconds() < timeout:
            response = await client.get(
                f"http://localhost:8011/v1/jobs/{job_id}",
                headers={"X-Api-Key": "test-api-key"}
            )
            job = response.json()
            if job["state"] == expected_state:
                return
            await asyncio.sleep(1)
        
        pytest.fail(f"Job did not reach state {expected_state} within {timeout}s")
```

## Test Execution

### Manual Execution

```bash
# Run all E2E tests
pytest tests/e2e/ -v --tb=short

# Run specific test suite
pytest tests/e2e/test_job_lifecycle.py -v

# Run with timeout
pytest tests/e2e/ --timeout=600 -v
```

### Automated Execution

**CI/CD Integration:**
- Run E2E tests nightly
- Run E2E tests on release candidates
- Run E2E tests after major changes

**GitHub Actions Example:**
```yaml
name: E2E Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio httpx
      - name: Start services
        run: docker-compose -f docker-compose.test.yml up -d
      - name: Wait for services
        run: ./scripts/wait-for-services.sh
      - name: Run E2E tests
        run: pytest tests/e2e/ -v --tb=short
      - name: Stop services
        if: always()
        run: docker-compose -f docker-compose.test.yml down
```

## Test Data Management

### Fixtures

**User Fixtures:**
- Regular user
- Admin user
- Miner user
- Agent user

**Wallet Fixtures:**
- Pre-funded wallets
- Empty wallets
- Wallets with staked tokens

**Job Fixtures:**
- Simple inference job
- Complex inference job
- Confidential job
- Batch jobs

**Blockchain Fixtures:**
- Genesis block
- Pre-populated accounts
- Sample transactions

### Data Cleanup

**Before Each Test:**
- Reset database to known state
- Clear blockchain test data
- Reset cache

**After Each Test:**
- Clean up created resources
- Reset service states
- Verify no data leaks

## Reporting

### Test Report Format

```markdown
# E2E Test Report

**Date:** [Date]
**Environment:** [Environment]
**Test Suite:** [Suite Name]

## Summary
- Total Tests: [Count]
- Passed: [Count]
- Failed: [Count]
- Skipped: [Count]
- Duration: [Time]

## Results by Scenario
| Scenario | Tests | Passed | Failed | Duration |
|----------|-------|--------|--------|----------|
| [Scenario 1] | [Count] | [Count] | [Count] | [Time] |
| [Scenario 2] | [Count] | [Count] | [Count] | [Time] |

## Failed Tests
### [Test Name]
- **Error:** [Error message]
- **Stack Trace:** [Trace]
- **Logs:** [Relevant logs]

## Recommendations
- [Recommendation 1]
- [Recommendation 2]
```

### Metrics to Track

- Test execution time
- Test success rate
- Test flakiness
- Resource utilization during tests
- Service restart count

## Maintenance

### Regular Updates

- **Weekly:** Review test failures and flakiness
- **Monthly:** Update test data and fixtures
- **Quarterly:** Review and update test scenarios
- **Annually:** Full test suite review and refactoring

### Test Maintenance Checklist

- [ ] Tests are up to date with API changes
- [ ] Test data is relevant and current
- [ ] Test environment matches production
- [ ] Test execution time is acceptable
- [ ] Test coverage is adequate
- [ ] Test documentation is current

## Risks and Mitigations

### Risks

1. **Service Dependencies:** Tests depend on multiple services
   - **Mitigation:** Use docker-compose for service orchestration, implement service health checks

2. **Test Data Management:** Managing test data across tests
   - **Mitigation:** Implement robust fixture system, use database transactions for rollback

3. **Test Execution Time:** E2E tests can be slow
   - **Mitigation:** Parallelize tests where possible, use test selection for targeted testing

4. **Environment Differences:** Test environment may not match production
   - **Mitigation:** Use production-like configuration, regular environment audits

5. **Test Flakiness:** E2E tests can be flaky due to timing issues
   - **Mitigation:** Implement proper waits and retries, use idempotent operations

## Success Criteria

### Before Production Deployment

- [ ] All critical E2E test scenarios implemented
- [ ] Test success rate >95%
- [ ] Test execution time <30 minutes
- [ ] Test environment matches production configuration
- [ ] Test data is comprehensive and current
- [ ] Tests integrated into CI/CD pipeline
- [ ] Test documentation is complete and current

### Ongoing

- [ ] Tests run at least daily
- [ ] Test failures are investigated and resolved
- [ ] Test suite is reviewed and updated quarterly
- [ ] Test metrics are tracked and reported

## Next Steps

### Immediate (1-2 weeks)
1. Set up E2E test environment
2. Implement service orchestration (docker-compose)
3. Create test fixtures
4. Implement critical test scenarios (job lifecycle, payment flow)

### Short-term (1 month)
1. Implement remaining test scenarios
2. Integrate tests into CI/CD
3. Set up test reporting
4. Document test procedures

### Long-term (3 months)
1. Optimize test execution time
2. Implement parallel test execution
3. Add UI testing (if applicable)
4. Implement test data management system

## Appendix

### A. Service Startup Order

1. PostgreSQL
2. Redis
3. Blockchain Node
4. Wallet Daemon
5. Coordinator API
6. Marketplace
7. Exchange
8. GPU Miner
9. Agent Coordinator

### B. Test Data Examples

**Sample User:**
```json
{
  "user_id": "test-user-001",
  "email": "test@example.com",
  "role": "user",
  "wallet_address": "ait1testuser001"
}
```

**Sample Job:**
```json
{
  "job_id": "test-job-001",
  "job_type": "ai_inference",
  "parameters": {
    "model": "gpt-4",
    "prompt": "Test prompt",
    "max_tokens": 100
  },
  "state": "QUEUED",
  "payment_amount": 100,
  "payment_currency": "AITBC"
}
```

### C. Troubleshooting

**Service Won't Start:**
- Check logs: `sudo journalctl -u [service-name] -f`
- Verify configuration: `sudo systemctl status [service-name]`
- Check port conflicts: `netstat -tulpn`

**Test Times Out:**
- Check service health: `curl http://localhost:[port]/health`
- Verify service dependencies: `sudo systemctl status [service-name]`
- Check for resource exhaustion: `htop`

**Test Fails Intermittently:**
- Review test logs for timing issues
- Increase wait times in tests
- Implement retries for flaky operations
- Check for race conditions

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Lead | | | |
| Engineering Lead | | | |
| DevOps Lead | | | |
