# AgentStaking Contract + Staking Service Test Plan

## Overview
Test plan for the AgentStaking smart contract (`/opt/aitbc/contracts/contracts/AgentStaking.sol`) and the Python staking service (`/opt/aitbc/apps/coordinator-api/src/app/services/staking_service.py`).

## Test Environment
- Contract: AgentStaking.sol (Solidity ^0.8.19)
- Service: staking_service.py (Python)
- Database: SQLModel with AgentStake, AgentMetrics, StakingPool models
- Blockchain: ait-testnet (multi-chain mode)

## Test Categories

### 1. Contract Unit Tests (Solidity)

#### 1.1 Staking Operations
- **Test 1.1.1**: Create stake with valid parameters
  - Input: valid agent wallet, amount within limits, valid lock period
  - Expected: Stake created with correct APY, status ACTIVE
  - Verify: StakeCreated event emitted, stake stored correctly

- **Test 1.1.2**: Create stake with insufficient balance
  - Input: amount > user balance
  - Expected: Transaction reverts with "Insufficient balance"
  - Verify: No stake created, no tokens transferred

- **Test 1.1.3**: Create stake with invalid amount (below minimum)
  - Input: amount < 100 AITBC
  - Expected: Transaction reverts with "Invalid stake amount"
  - Verify: No stake created

- **Test 1.1.4**: Create stake with invalid amount (above maximum)
  - Input: amount > 100,000 AITBC
  - Expected: Transaction reverts with "Invalid stake amount"
  - Verify: No stake created

- **Test 1.1.5**: Create stake on unsupported agent
  - Input: agent wallet not in supported agents list
  - Expected: Transaction reverts with "Agent not supported"
  - Verify: No stake created

- **Test 1.1.6**: Create stake with invalid lock period (too short)
  - Input: lock period < 1 day
  - Expected: Transaction reverts with "Lock period too short"
  - Verify: No stake created

- **Test 1.1.7**: Create stake with invalid lock period (too long)
  - Input: lock period > 365 days
  - Expected: Transaction reverts with "Lock period too long"
  - Verify: No stake created

#### 1.2 APY Calculation
- **Test 1.2.1**: APY calculation for Bronze tier (1x multiplier)
  - Input: agent tier = BRONZE, lock period = 30 days
  - Expected: APY = 5% * 1.0 * 1.1 = 5.5%

- **Test 1.2.2**: APY calculation for Diamond tier (3x multiplier)
  - Input: agent tier = DIAMOND, lock period = 365 days
  - Expected: APY = 5% * 3.0 * 2.0 = 30% (capped at 20%)

- **Test 1.2.3**: APY capping at maximum
  - Input: high tier + long lock period
  - Expected: APY capped at 20%

#### 1.3 Adding to Stake
- **Test 1.3.1**: Add to active stake
  - Input: valid stake ID, additional amount
  - Expected: Stake amount updated, APY recalculated
  - Verify: StakeUpdated event emitted

- **Test 1.3.2**: Add to non-existent stake
  - Input: invalid stake ID
  - Expected: Transaction reverts with "Stake does not exist"

- **Test 1.3.3**: Add to unbonding stake
  - Input: stake with UNBONDING status
  - Expected: Transaction reverts with "Stake not active"

#### 1.4 Unbonding Operations
- **Test 1.4.1**: Initiate unbonding after lock period
  - Input: stake ID, lock period elapsed
  - Expected: Stake status = UNBONDING, rewards calculated
  - Verify: StakeUnbonded event emitted

- **Test 1.4.2**: Initiate unbonding before lock period
  - Input: stake ID, lock period not elapsed
  - Expected: Transaction reverts with "Lock period not ended"

- **Test 1.4.3**: Complete unbonding after unbonding period
  - Input: stake ID, unbonding period elapsed
  - Expected: Stake status = COMPLETED, tokens returned + rewards
  - Verify: StakeCompleted event emitted

- **Test 1.4.4**: Complete unbonding with early penalty
  - Input: stake ID, completed within 30 days
  - Expected: 10% penalty applied
  - Verify: Penalty deducted from returned amount

#### 1.5 Reward Distribution
- **Test 1.5.1**: Distribute earnings to stakers
  - Input: agent wallet, total earnings
  - Expected: Earnings distributed proportionally, platform fee deducted
  - Verify: PoolRewardsDistributed event emitted

- **Test 1.5.2**: Distribute with no stakers
  - Input: agent wallet with no stakers
  - Expected: Transaction reverts with "No stakers in pool"

#### 1.6 Agent Performance Updates
- **Test 1.6.1**: Update agent performance (tier upgrade)
  - Input: agent wallet, high accuracy, successful submission
  - Expected: Agent tier upgraded, all active stakes APY updated
  - Verify: AgentTierUpdated event emitted

- **Test 1.6.2**: Update agent performance (tier downgrade)
  - Input: agent wallet, low accuracy, failed submission
  - Expected: Agent tier downgraded, all active stakes APY updated
  - Verify: AgentTierUpdated event emitted

#### 1.7 Configuration Updates
- **Test 1.7.1**: Update base APY
  - Input: new base APY (within limits)
  - Expected: baseAPY updated
  - Verify: New APY applies to future stakes

- **Test 1.7.2**: Update APY with invalid values
  - Input: base APY > max APY
  - Expected: Transaction reverts with "Base APY cannot exceed max APY"

### 2. Service Integration Tests (Python)

#### 2.1 Staking Service Operations
- **Test 2.1.1**: Create stake via service
  - Input: valid staker address, agent wallet, amount, lock period
  - Expected: Stake created in database, agent metrics updated
  - Verify: Database contains stake, agent total_staked increased

- **Test 2.1.2**: Get stake by ID
  - Input: valid stake ID
  - Expected: Stake details returned
  - Verify: All stake fields present

- **Test 2.1.3**: Get user stakes with filters
  - Input: user address, status filter, tier filter
  - Expected: Filtered list of stakes returned
  - Verify: Pagination works correctly

- **Test 2.1.4**: Add to stake via service
  - Input: stake ID, additional amount
  - Expected: Stake amount updated in database
  - Verify: Agent metrics updated

- **Test 2.1.5**: Calculate rewards
  - Input: stake ID
  - Expected: Current reward amount calculated
  - Verify: Calculation matches expected formula

#### 2.2 Agent Metrics Management
- **Test 2.2.1**: Get agent metrics
  - Input: agent wallet address
  - Expected: Agent metrics returned
  - Verify: All metrics fields present

- **Test 2.2.2**: Update agent performance
  - Input: agent wallet, accuracy, successful flag
  - Expected: Metrics updated, tier recalculated if needed
  - Verify: Success rate calculated correctly

- **Test 2.2.3**: Calculate agent tier
  - Input: agent metrics with high performance
  - Expected: DIAMOND tier returned
  - Verify: Tier calculation formula correct

#### 2.3 Staking Pool Operations
- **Test 2.3.1**: Get staking pool
  - Input: agent wallet
  - Expected: Pool details returned
  - Verify: Pool statistics accurate

- **Test 2.3.2**: Update staking pool (add stake)
  - Input: agent wallet, staker address, amount
  - Expected: Pool total_staked increased
  - Verify: Staker added to active_stakers if new

- **Test 2.3.3**: Update staking pool (remove stake)
  - Input: agent wallet, staker address, amount
  - Expected: Pool total_staked decreased
  - Verify: Staker removed if no shares remaining

#### 2.4 Earnings Distribution
- **Test 2.4.1**: Distribute earnings
  - Input: agent wallet, total earnings
  - Expected: Earnings distributed proportionally to stakers
  - Verify: Platform fee deducted correctly

- **Test 2.4.2**: Get supported agents
  - Input: tier filter, pagination
  - Expected: Filtered list of agents returned
  - Verify: Current APY calculated for each agent

#### 2.5 Statistics and Reporting
- **Test 2.5.1**: Get staking stats (daily)
  - Input: period = "daily"
  - Expected: Statistics for last 24 hours
  - Verify: Total staked, active stakes, unique stakers accurate

- **Test 2.5.2**: Get staking stats (weekly)
  - Input: period = "weekly"
  - Expected: Statistics for last 7 days
  - Verify: Tier distribution calculated correctly

- **Test 2.5.3**: Get leaderboard (total_staked)
  - Input: period = "weekly", metric = "total_staked"
  - Expected: Agents ranked by total staked
  - Verify: Ranking order correct

- **Test 2.5.4**: Get leaderboard (total_rewards)
  - Input: period = "weekly", metric = "total_rewards"
  - Expected: Agents ranked by rewards distributed
  - Verify: Ranking order correct

- **Test 2.5.5**: Get user rewards
  - Input: user address, period
  - Expected: User's staking rewards summary
  - Verify: Total rewards and average APY calculated correctly

#### 2.6 Risk Assessment
- **Test 2.6.1**: Get risk assessment (low risk)
  - Input: high-performing agent
  - Expected: Low risk level
  - Verify: Risk factors calculated correctly

- **Test 2.6.2**: Get risk assessment (high risk)
  - Input: low-performing new agent
  - Expected: High risk level
  - Verify: Recommendations provided

### 3. Integration Tests (Contract + Service)

#### 3.1 End-to-End Staking Flow
- **Test 3.1.1**: Complete staking lifecycle
  - Steps:
    1. Register agent in contract
    2. Create stake via service
    3. Wait for lock period
    4. Initiate unbonding
    5. Complete unbonding
  - Expected: Full cycle completes successfully
  - Verify: Tokens returned with correct rewards

#### 3.2 Performance Tier Updates
- **Test 3.2.1**: Agent tier upgrade affects staking APY
  - Steps:
    1. Create stake on Bronze tier agent
    2. Update agent performance to DIAMOND tier
    3. Verify APY updated for active stakes
  - Expected: APY increased for all active stakes

#### 3.3 Reward Distribution Flow
- **Test 3.3.1**: Agent earnings distributed to stakers
  - Steps:
    1. Multiple users stake on agent
    2. Agent earns rewards
    3. Distribute earnings via contract
    4. Verify service reflects updated rewards
  - Expected: All stakers receive proportional rewards

### 4. Edge Cases and Error Handling

#### 4.1 Reentrancy Protection
- **Test 4.1.1**: Reentrancy attack on stake creation
  - Input: Malicious contract attempting reentrancy
  - Expected: Transaction reverts
  - Verify: ReentrancyGuard prevents attack

#### 4.2 Pause Functionality
- **Test 4.2.1**: Pause contract during emergency
  - Input: Call pause() as owner
  - Expected: All state-changing functions revert
  - Verify: Only owner can pause/unpause

#### 4.3 Integer Overflow/Underflow
- **Test 4.3.1**: Large stake amounts
  - Input: Maximum stake amount
  - Expected: No overflow, calculations correct
  - Verify: Solidity 0.8.19 has built-in overflow protection

#### 4.4 Database Transaction Rollback
- **Test 4.4.1**: Service operation failure triggers rollback
  - Input: Invalid data causing service error
  - Expected: Database transaction rolled back
  - Verify: No partial state changes

### 5. Test Execution Priority

#### High Priority (Critical Path)
1. Test 1.1.1: Create stake with valid parameters
2. Test 1.4.1: Initiate unbonding after lock period
3. Test 1.4.3: Complete unbonding after unbonding period
4. Test 2.1.1: Create stake via service
5. Test 3.1.1: Complete staking lifecycle

#### Medium Priority (Important Features)
6. Test 1.2.1-1.2.3: APY calculation
7. Test 1.5.1: Distribute earnings to stakers
8. Test 1.6.1: Update agent performance
9. Test 2.2.1-2.2.3: Agent metrics management
10. Test 2.4.1: Distribute earnings via service

#### Low Priority (Edge Cases)
11. Test 4.1-4.4: Security and edge cases
12. Test 2.5.1-2.5.5: Statistics and reporting
13. Test 2.6.1-2.6.2: Risk assessment

## Test Data Requirements

### Required Test Accounts
- Owner account (for configuration updates)
- Staker accounts (multiple for testing distribution)
- Agent wallets (for different performance tiers)
- Malicious account (for security tests)

### Required Test Data
- AITBC token balances (pre-funded)
- Agent performance data (accuracy, success rates)
- Staking pool data (initial state)
- Historical performance data

## Success Criteria
- All high priority tests pass
- At least 80% of medium priority tests pass
- No critical security vulnerabilities found
- Performance within acceptable limits
- Gas optimization verified for contract functions

## Test Deliverables
1. Test suite for AgentStaking contract (Solidity/Hardhat)
2. Test suite for staking_service (Python/pytest)
3. Integration test suite
4. Test execution report
5. Bug report with severity classification
6. Performance analysis report
