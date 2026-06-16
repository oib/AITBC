# AITBC Staking Tests Documentation

## Overview

This directory contains tests for the AITBC staking system, including the AgentStaking smart contract and the Python staking service.

## Test Structure

```
tests/
├── fixtures/
│   └── staking_fixtures.py          # Shared fixtures for staking tests
├── services/
│   └── test_staking_service.py       # Service-level tests
├── integration/
│   └── test_staking_lifecycle.py    # Integration tests
└── staking/
    └── README.md                     # This file
```

## Test Files

### Service Tests (`tests/services/test_staking_service.py`)

Tests the Python staking service business logic.

**Status**: 8/8 tests passing ✓

**Tests Covered**:
- Create stake with valid parameters
- Get stake by ID
- Get user stakes with filters
- Add to stake
- Calculate rewards
- Unsupported agent validation
- Invalid amount validation
- APY calculation verification

**Dependencies**:
- pytest
- sqlmodel
- SQLite (in-memory database)

**Run Command**:
```bash
/opt/aitbc/venv/bin/python -m pytest tests/services/test_staking_service.py -v
```

### Integration Tests (`tests/integration/test_staking_lifecycle.py`)

Tests the complete staking lifecycle end-to-end.

**Status**: 4/4 tests passing ✓

**Tests Covered**:
- Complete staking lifecycle (create, unbond, complete)
- Stake accumulation over time
- Multiple stakes on same agent
- Stakes with different performance tiers

**Dependencies**:
- pytest
- sqlmodel
- SQLite (in-memory database)

**Run Command**:
```bash
/opt/aitbc/venv/bin/python -m pytest tests/integration/test_staking_lifecycle.py -v
```

### Contract Tests (`contracts/test/AgentStaking.test.js`)

Tests the AgentStaking smart contract using Hardhat.

**Status**: Blocked by compilation errors in unrelated contracts

**Tests Implemented**:
- Create stake with valid parameters
- Initiate unbonding after lock period
- Complete unbonding after unbonding period

**Issue**: Unrelated contracts have DocstringParsingError and TypeError

**Run Command** (when unblocked):
```bash
cd /opt/aitbc/contracts
npx hardhat test test/AgentStaking.test.js
```

## Shared Fixtures (`tests/fixtures/staking_fixtures.py`)

Reusable fixtures for staking tests to avoid duplication.

**Available Fixtures**:
- `db_session` - In-memory SQLite database
- `staking_service` - StakingService instance
- `agent_wallet` - Default test agent wallet
- `staker_address` - Default test staker address
- `agent_metrics` - GOLD tier agent metrics
- `agent_metrics_bronze` - BRONZE tier agent metrics
- `agent_metrics_diamond` - DIAMOND tier agent metrics
- `staking_pool` - Test staking pool
- `stake_data` - Default stake creation data
- `large_stake_data` - Large stake data
- `small_stake_data` - Small stake data
- `invalid_stake_data` - Invalid stake data
- `created_stake` - Pre-created stake for testing
- `active_stake` - Active stake in database
- `unbonding_stake` - Unbonding stake in database
- `completed_stake` - Completed stake in database
- `multiple_stakes` - Multiple stakes for testing

**Helper Functions**:
- `calculate_expected_apy()` - Calculate expected APY
- `get_tier_multiplier()` - Get tier multiplier
- `get_lock_multiplier()` - Get lock period multiplier

## Test Runner

A dedicated test runner script is available to execute all staking tests:

**Location**: `/opt/aitbc/scripts/testing/run_staking_tests.sh`

**Run Command**:
```bash
/opt/aitbc/scripts/testing/run_staking_tests.sh
```

**Features**:
- Runs service, integration, and contract tests
- Generates combined test report
- Saves logs to `/var/log/aitbc/tests/staking/`
- Provides pass/fail status for each test suite

## Test Data Requirements

### Required Test Data
- Agent wallet addresses (for different performance tiers)
- Staker addresses (for creating stakes)
- Agent performance metrics (accuracy, success rates, submission counts)
- Staking pool data (initial state)

### Test Data Generation
Test data can be generated using the fixtures or by creating test data manually in fixtures.

## Known Issues

### Deprecation Warnings
- **Issue**: 63 deprecation warnings about `datetime.utcnow()`
- **Impact**: Warnings only - tests pass successfully
- **Fix**: Requires database migration to timezone-aware datetimes
- **Status**: Deferred - not critical for functionality

### Contract Test Blocking
- **Issue**: Compilation errors in unrelated contracts
- **Error Types**: DocstringParsingError, TypeError
- **Impact**: Cannot run AgentStaking contract tests
- **Fix Options**:
  1. Fix compilation errors in affected contracts (proper solution)
  2. Isolate AgentStaking testing with separate Hardhat config
  3. Use mock contract deployment for initial testing
- **Status**: Deferred - service and integration tests provide good coverage

## Test Execution

### Run All Staking Tests
```bash
/opt/aitbc/scripts/testing/run_staking_tests.sh
```

### Run Service Tests Only
```bash
/opt/aitbc/venv/bin/python -m pytest tests/services/test_staking_service.py -v
```

### Run Integration Tests Only
```bash
/opt/aitbc/venv/bin/python -m pytest tests/integration/test_staking_lifecycle.py -v
```

### Run Contract Tests Only (when unblocked)
```bash
cd /opt/aitbc/contracts
npx hardhat test test/AgentStaking.test.js
```

## Test Coverage

### Current Coverage
- **Service Tests**: 8/8 tests passing (100%)
- **Integration Tests**: 4/4 tests passing (100%)
- **Contract Tests**: 0/3 tests (blocked)

### Coverage Areas
- ✅ Stake creation and validation
- ✅ APY calculation
- ✅ Unbonding operations
- ✅ Reward calculation
- ✅ Agent metrics management
- ✅ Staking pool operations
- ❌ Contract deployment (blocked)
- ❌ Contract execution (blocked)
- ❌ Contract events (blocked)

## Future Improvements

### High Priority
- [ ] Improve service test coverage with edge cases
- [ ] Add error handling tests
- [ ] Add performance tests

### Medium Priority
- [ ] Create test data generator script
- [ ] Add CI/CD integration
- [ ] Implement test parallelization
- [ ] Add performance benchmarks

### Low Priority (When Contract Tests Unblocked)
- [ ] Fix contract compilation errors
- [ ] Run contract tests
- [ ] Add contract-service integration tests
- [ ] Implement comprehensive end-to-end tests

## Troubleshooting

### Service Tests Fail
1. Check SQLite in-memory database initialization
2. Verify SQLModel imports are correct
3. Check session commit and refresh operations
4. Review fixture dependencies

### Integration Tests Fail
1. Verify service test dependencies
2. Check database session management
3. Ensure fixtures are properly isolated
4. Review time simulation logic

### Contract Tests Fail
1. Check Hardhat configuration
2. Verify contract dependencies (AIToken, PerformanceVerifier)
3. Ensure contract compilation succeeds
4. Review gas limits and transaction parameters

## Reports

Test reports are generated in `/var/log/aitbc/tests/staking/`:
- `service_tests_*.log` - Service test output
- `integration_tests_*.log` - Integration test output
- `contract_tests_*.log` - Contract test output
- `staking_test_report_*.txt` - Combined test report

## References

- **Test Plan**: `/opt/aitbc/tests/contracts/staking_test_plan.md`
- **Implementation Plan**: `/root/.windsurf/plans/staking-high-priority-tests-6c2d50.md`
- **Service Code**: `/opt/aitbc/apps/coordinator-api/src/app/services/staking_service.py`
- **Domain Models**: `/opt/aitbc/apps/coordinator-api/src/app/domain/bounty.py`
