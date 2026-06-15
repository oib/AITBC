# Testing

## Overview

The Governance Service includes comprehensive testing for both the service endpoints and smart contracts. This document covers testing procedures and results.

## Smart Contract Tests

### Running Tests

```bash
cd /opt/aitbc/contracts/governance
forge test
```

### Test Results

**AITBCGovernanceToken.sol:** 7/7 tests passing
- testInitialState ✅
- testStakeTokens ✅
- testStakeMinimumLockPeriod ✅
- testCannotStakeTwice ✅
- testUnstakeTokens ✅
- testCannotUnstakeBeforeLockPeriod ✅
- testVotingPowerCalculation ✅

**AITBCVoting.sol:** 7/7 tests passing
- testCreateProposal ✅
- testCreateProposalInvalidVotingPeriod ✅
- testVoteOnProposal ✅
- testCannotVoteTwice ✅
- testCannotVoteAfterVotingEnds ✅
- testExecuteProposal ✅
- testCannotExecuteRejectedProposal ✅

**Total:** 14/14 tests passing

### Running Specific Tests

```bash
# Test specific contract
forge test --match-contract AITBCGovernanceTokenTest

# Test specific function
forge test --match-test testStakeTokens

# Run with gas report
forge test --gas-report

# Run with verbosity
forge test -vvv
```

### Test Coverage

**AITBCGovernanceToken.sol Coverage:**
- Token initialization: 100%
- Staking logic: 100%
- Unstaking logic: 100%
- Voting power calculation: 100%
- Transfer with voting power update: 100%

**AITBCVoting.sol Coverage:**
- Proposal creation: 100%
- Voting logic: 100%
- Proposal execution: 100%
- Quorum enforcement: 100%
- Execution delay enforcement: 100%

## Service Tests

### Running Tests

```bash
cd /opt/aitbc/apps/governance
pytest tests/
```

### Test Files

**test_main.py:**
- test_health_check ✅
- test_governance_status ✅
- test_get_governance_profiles ✅
- test_get_governance_proposals ✅
- test_get_governance_votes ✅
- test_get_governance_treasury ✅
- test_get_governance_analytics ✅
- test_stake_tokens ✅ (v0.4.12)
- test_get_voting_power ✅ (v0.4.12)
- test_delegate_voting_power ✅ (v0.4.12)
- test_execute_proposal ✅ (v0.4.12)

### Running Specific Tests

```bash
# Run specific test file
pytest tests/test_main.py

# Run specific test
pytest tests/test_main.py::test_health_check

# Run with coverage
pytest --cov=governance_service tests/

# Run with verbosity
pytest -v tests/
```

## Integration Testing

### Manual API Testing

```bash
# Health check
curl http://localhost:8105/health

# Stake tokens
curl -X POST http://localhost:8105/v1/governance/stake \
  -H "Content-Type: application/json" \
  -d '{"staker_address": "0x123...", "amount": 1000, "lock_period_days": 30}'

# Get voting power
curl http://localhost:8105/v1/governance/voting-power/0x123...

# Delegate voting power
curl -X POST http://localhost:8105/v1/governance/delegate \
  -H "Content-Type: application/json" \
  -d '{"delegator_address": "0x123...", "delegate_address": "0x456...", "amount": 500}'
```

### CLI Testing

```bash
# Test CLI help
aitbc governance --help

# Test staking
aitbc governance stake --address 0x123... --amount 1000 --lock-days 30

# Test voting power query
aitbc governance voting-power 0x123...
```

## Test Data

### Sample Proposal Data

```json
{
  "proposal_id": "prop_123",
  "proposer_id": "user123",
  "title": "Test Proposal",
  "description": "Test description",
  "category": "general",
  "status": "active",
  "voting_starts": "2026-06-07T00:00:00Z",
  "voting_ends": "2026-06-14T00:00:00Z"
}
```

### Sample Vote Data

```json
{
  "vote_id": "vote_123",
  "proposal_id": "prop_123",
  "voter_id": "user456",
  "vote_type": "for",
  "voting_power": 1000,
  "reason": "Support this proposal"
}
```

## Test Environment

### Development Database

Uses SQLite in-memory database for testing:

```python
# In test setup
DATABASE_URL = "sqlite:///:memory:"
```

### Test Configuration

```python
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

## Continuous Integration

### GitHub Actions (Future)

```yaml
name: Governance Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          pip install pytest pytest-cov
          pip install -r requirements.txt
      - name: Run service tests
        run: pytest tests/
      - name: Install Foundry
        run: curl -L https://foundry.paradigm.xyz | bash
      - name: Run contract tests
        run: forge test
```

## Performance Testing

### Load Testing (Future)

Use tools like Locust or k6 for load testing:

```python
# locustfile.py
from locust import HttpUser, task

class GovernanceUser(HttpUser):
    @task
    def health_check(self):
        self.client.get("/health")

    @task
    def get_proposals(self):
        self.client.get("/v1/governance/proposals")
```

## Troubleshooting Tests

### Service Tests Fail

**Issue:** Database connection error

**Solution:**
```bash
# Ensure database directory exists
mkdir -p /var/lib/aitbc/data

# Run migrations
cd /opt/aitbc/apps/governance
/opt/aitbc/venv/bin/alembic upgrade head
```

### Smart Contract Tests Fail

**Issue:** Compilation error

**Solution:**
```bash
# Install OpenZeppelin contracts
cd /opt/aitbc/contracts/governance
forge install OpenZeppelin/openzeppelin-contracts

# Rebuild
forge build
```

### Import Errors

**Issue:** Module not found

**Solution:**
```bash
# Ensure virtual environment is activated
source /opt/aitbc/venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Test Documentation

### Adding New Tests

1. Create test file in `tests/` directory
2. Use pytest conventions (test_ prefix)
3. Follow existing test patterns
4. Update this document

### Test Naming Conventions

- Test files: `test_<module>.py`
- Test classes: `Test<ClassName>`
- Test functions: `test_<description>`

## References

- Pytest Documentation: https://docs.pytest.org/
- Foundry Documentation: https://book.getfoundry.sh/
