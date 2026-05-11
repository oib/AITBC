---
description: Smart Contract Security Sprint Phase 1 - Implementation Plan for SC-H-01 and SC-H-02
---

# Smart Contract Security Sprint - Phase 1 Implementation Plan

**Date:** 2026-05-11  
**Status:** In Progress  
**Focus:** AgentStaking.sol security enhancements

## Findings to Implement

### SC-H-01: No Slashing Mechanism in AgentStaking.sol

**Current State:**
- Contract has `SLASHED` status enum (line 33)
- No actual slashing implementation
- Malicious agents can act without consequences

**Implementation Plan:**

**1. Add Slashing Conditions**
```solidity
// New state variables
struct SlashingCondition {
    uint256 minAccuracyThreshold; // e.g., 50% minimum accuracy
    uint256 maxMissedJobs; // e.g., 5 consecutive missed jobs
    uint256 slashingPercentage; // e.g., 10% slash amount
}

mapping(address => SlashingCondition) public slashingConditions;
uint256 public defaultMinAccuracy = 50; // 50%
uint256 public defaultMaxMissedJobs = 5;
uint256 public defaultSlashingPercentage = 10; // 10%
```

**2. Implement Slashing Function**
```solidity
function slashStake(
    uint256 _stakeId,
    uint256 _slashingAmount,
    string memory _reason
) external onlyOwner {
    Stake storage stake = stakes[_stakeId];
    require(stake.status == StakeStatus.ACTIVE, "Stake not active");
    require(_slashingAmount <= stake.amount, "Invalid slash amount");
    
    // Transfer slashed amount to treasury
    uint256 slashAmount = (stake.amount * _slashingAmount) / 100;
    stake.amount -= slashAmount;
    
    // Update status to SLASHED
    stake.status = StakeStatus.SLASHED;
    
    // Transfer slashed tokens to treasury
    aitbcToken.transfer(owner(), slashAmount);
    
    emit StakeSlashed(_stakeId, stake.staker, slashAmount, _reason);
}
```

**3. Add Automatic Slashing Based on Performance**
```solidity
function checkAndSlashAgent(
    address _agentWallet
) external onlyOwner {
    AgentMetrics storage metrics = agentMetrics[_agentWallet];
    
    // Check accuracy threshold
    if (metrics.averageAccuracy < defaultMinAccuracy) {
        _slashAllStakesForAgent(_agentWallet, defaultSlashingPercentage, "Low accuracy");
    }
    
    // Check missed jobs
    uint256 missedJobs = metrics.totalSubmissions - metrics.successfulSubmissions;
    if (missedJobs > defaultMaxMissedJobs) {
        _slashAllStakesForAgent(_agentWallet, defaultSlashingPercentage, "Too many missed jobs");
    }
}

function _slashAllStakesForAgent(
    address _agentWallet,
    uint256 _slashingPercentage,
    string memory _reason
) internal {
    uint256[] storage stakesForAgent = agentStakes[_agentWallet];
    for (uint256 i = 0; i < stakesForAgent.length; i++) {
        uint256 stakeId = stakesForAgent[i];
        Stake storage stake = stakes[stakeId];
        if (stake.status == StakeStatus.ACTIVE) {
            uint256 slashAmount = (stake.amount * _slashingPercentage) / 100;
            stake.amount -= slashAmount;
            stake.status = StakeStatus.SLASHED;
            aitbcToken.transfer(owner(), slashAmount);
            emit StakeSlashed(stakeId, stake.staker, slashAmount, _reason);
        }
    }
}
```

**4. Add Appeal Process**
```solidity
struct SlashAppeal {
    uint256 stakeId;
    address appellant;
    string memory reason;
    uint256 appealTime;
    bool resolved;
    bool approved;
}

mapping(uint256 => SlashAppeal) public slashAppeals;
uint256 public appealCooldown = 7 days;
uint256 public appealWindow = 3 days;

function appealSlashing(uint256 _stakeId, string memory _reason) external {
    Stake storage stake = stakes[_stakeId];
    require(stake.staker == msg.sender, "Not your stake");
    require(stake.status == StakeStatus.SLASHED, "Not slashed");
    require(block.timestamp - stake.lastRewardTime < appealWindow, "Appeal window expired");
    
    slashAppeals[_stakeId] = SlashAppeal({
        stakeId: _stakeId,
        appellant: msg.sender,
        reason: _reason,
        appealTime: block.timestamp,
        resolved: false,
        approved: false
    });
    
    emit SlashAppealFiled(_stakeId, msg.sender, _reason);
}

function resolveSlashAppeal(uint256 _stakeId, bool _approved) external onlyOwner {
    SlashAppeal storage appeal = slashAppeals[_stakeId];
    require(appeal.appellant != address(0), "No appeal found");
    require(!appeal.resolved, "Already resolved");
    
    appeal.resolved = true;
    appeal.approved = _approved;
    
    if (_approved) {
        Stake storage stake = stakes[_stakeId];
        stake.status = StakeStatus.ACTIVE;
        emit SlashAppealApproved(_stakeId);
    } else {
        emit SlashAppealRejected(_stakeId);
    }
}
```

**5. Add Slashing Rewards to Reporters**
```solidity
uint256 public slashReporterReward = 500; // 5% of slashed amount

function reportMaliciousAgent(
    address _agentWallet,
    string memory _evidence
) external {
    require(agentMetrics[_agentWallet].agentWallet != address(0), "Agent not found");
    
    // Check if agent should be slashed
    if (agentMetrics[_agentWallet].averageAccuracy < defaultMinAccuracy) {
        uint256 totalSlashed = _slashAllStakesForAgent(_agentWallet, defaultSlashingPercentage, "Reporter: " + _evidence);
        uint256 reward = (totalSlashed * slashReporterReward) / 10000;
        aitbcToken.transfer(msg.sender, reward);
        
        emit MaliciousAgentReported(_agentWallet, msg.sender, reward);
    }
}
```

### SC-H-02: Lack of Oracle Manipulation Protection in AgentStaking.sol

**Current State:**
- `updateAgentPerformance` function (line 429) lacks oracle authorization
- Any caller can update performance metrics
- No time delay for performance updates

**Implementation Plan:**

**1. Add Authorized Oracle List**
```solidity
mapping(address => bool) public authorizedOracles;
uint256 public oracleCount;
address[] public oracleList;

modifier onlyAuthorizedOracle() {
    require(authorizedOracles[msg.sender], "Not authorized oracle");
    _;
}

function addOracle(address _oracle) external onlyOwner {
    require(_oracle != address(0), "Invalid oracle address");
    require(!authorizedOracles[_oracle], "Oracle already authorized");
    
    authorizedOracles[_oracle] = true;
    oracleList.push(_oracle);
    oracleCount++;
    
    emit OracleAdded(_oracle);
}

function removeOracle(address _oracle) external onlyOwner {
    require(authorizedOracles[_oracle], "Oracle not authorized");
    
    authorizedOracles[_oracle] = false;
    oracleCount--;
    
    emit OracleRemoved(_oracle);
}
```

**2. Add Oracle Signature Verification**
```solidity
using ECDSA for bytes32;
using ECDSA for bytes;

struct PerformanceUpdate {
    address agentWallet;
    uint256 accuracy;
    bool successful;
    uint256 timestamp;
    uint256 nonce;
}

mapping(address => uint256) public oracleNonces;

function updateAgentPerformanceWithSignature(
    address _agentWallet,
    uint256 _accuracy,
    bool _successful,
    uint256 _timestamp,
    uint256 _nonce,
    bytes memory _signature
) external onlyAuthorizedOracle {
    require(block.timestamp <= _timestamp + 1 hours, "Signature expired");
    require(oracleNonces[msg.sender] == _nonce, "Invalid nonce");
    
    // Verify signature
    bytes32 messageHash = keccak256(abi.encodePacked(_agentWallet, _accuracy, _successful, _timestamp, _nonce));
    bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
    address signer = ethSignedMessageHash.recover(_signature);
    require(signer == msg.sender, "Invalid signature");
    
    // Update nonce
    oracleNonces[msg.sender]++;
    
    // Call original update function
    _updateAgentPerformanceInternal(_agentWallet, _accuracy, _successful);
}

function _updateAgentPerformanceInternal(
    address _agentWallet,
    uint256 _accuracy,
    bool _successful
) internal {
    AgentMetrics storage metrics = agentMetrics[_agentWallet];
    
    metrics.totalSubmissions++;
    if (_successful) {
        metrics.successfulSubmissions++;
    }
    
    uint256 totalAccuracy = metrics.averageAccuracy * (metrics.totalSubmissions - 1) + _accuracy;
    metrics.averageAccuracy = totalAccuracy / metrics.totalSubmissions;
    
    metrics.lastUpdateTime = block.timestamp;
    
    PerformanceTier newTier = _calculateAgentTier(_agentWallet);
    PerformanceTier oldTier = metrics.currentTier;
    
    if (newTier != oldTier) {
        metrics.currentTier = newTier;
        
        uint256[] storage stakesForAgent = agentStakes[_agentWallet];
        for (uint256 i = 0; i < stakesForAgent.length; i++) {
            uint256 stakeId = stakesForAgent[i];
            Stake storage stake = stakes[stakeId];
            if (stake.status == StakeStatus.ACTIVE) {
                stake.currentAPY = _calculateAPY(_agentWallet, stake.lockPeriod, newTier);
                stake.agentTier = newTier;
            }
        }
        
        emit AgentTierUpdated(_agentWallet, oldTier, newTier, metrics.tierScore);
    }
}
```

**3. Add Time Delay for Performance Updates**
```solidity
uint256 public performanceUpdateDelay = 1 hours;
mapping(address => uint256) public lastPerformanceUpdateTime;

function updateAgentPerformance(
    address _agentWallet,
    uint256 _accuracy,
    bool _successful
) external onlyAuthorizedOracle {
    require(block.timestamp >= lastPerformanceUpdateTime[_agentWallet] + performanceUpdateDelay, "Update too frequent");
    
    lastPerformanceUpdateTime[_agentWallet] = block.timestamp;
    _updateAgentPerformanceInternal(_agentWallet, _accuracy, _successful);
}
```

**4. Implement Oracle Rotation Mechanism**
```solidity
uint256 public oracleRotationPeriod = 30 days;
uint256 public lastOracleRotation;

function rotateOracle(address _oldOracle, address _newOracle) external onlyOwner {
    require(authorizedOracles[_oldOracle], "Old oracle not authorized");
    require(!authorizedOracles[_newOracle], "New oracle already authorized");
    require(block.timestamp >= lastOracleRotation + oracleRotationPeriod, "Rotation too soon");
    
    authorizedOracles[_oldOracle] = false;
    authorizedOracles[_newOracle] = true;
    lastOracleRotation = block.timestamp;
    
    emit OracleRotated(_oldOracle, _newOracle);
}
```

**5. Add Oracle Reputation Scoring**
```solidity
struct OracleReputation {
    uint256 totalUpdates;
    uint256 successfulUpdates;
    uint256 disputedUpdates;
    uint256 reputationScore; // 0-100
}

mapping(address => OracleReputation) public oracleReputations;

function updateOracleReputation(address _oracle, bool _successful) internal {
    OracleReputation storage rep = oracleReputations[_oracle];
    rep.totalUpdates++;
    
    if (_successful) {
        rep.successfulUpdates++;
        rep.reputationScore = (rep.successfulUpdates * 100) / rep.totalUpdates;
    } else {
        rep.disputedUpdates++;
        rep.reputationScore = (rep.successfulUpdates * 100) / rep.totalUpdates;
        
        // Remove oracle if reputation falls below threshold
        if (rep.reputationScore < 50) {
            authorizedOracles[_oracle] = false;
            emit OracleRemovedForLowReputation(_oracle, rep.reputationScore);
        }
    }
}
```

## Testing Strategy

### SC-H-01 Tests

1. **Slashing Condition Tests**
   - Test slashing when accuracy below threshold
   - Test slashing when missed jobs exceed limit
   - Test no slashing when conditions not met

2. **Slashing Execution Tests**
   - Test manual slashing by owner
   - Test automatic slashing based on performance
   - Test slashed stake status change
   - Test token transfer to treasury

3. **Appeal Process Tests**
   - Test appeal filing within window
   - Test appeal rejection after window
   - Test appeal approval by owner
   - Test appeal rejection by owner

4. **Reporter Reward Tests**
   - Test reward distribution for valid reports
   - Test no reward for invalid reports

### SC-H-02 Tests

1. **Oracle Authorization Tests**
   - Test only authorized oracles can update performance
   - Test unauthorized callers are rejected
   - Test oracle addition/removal by owner

2. **Signature Verification Tests**
   - Test valid signature acceptance
   - Test invalid signature rejection
   - Test nonce validation
   - Test timestamp validation

3. **Time Delay Tests**
   - Test update delay enforcement
   - Test immediate update rejection
   - Test update after delay acceptance

4. **Oracle Rotation Tests**
   - Test oracle rotation by owner
   - Test rotation period enforcement
   - Test old oracle removal
   - Test new oracle authorization

5. **Reputation Tests**
   - Test reputation score calculation
   - Test low reputation removal
   - Test reputation update on performance update

## Implementation Order

1. **SC-H-01: Slashing Mechanism**
   - Add slashing condition structs and state variables
   - Implement manual slashing function
   - Implement automatic slashing based on performance
   - Add appeal process
   - Add reporter rewards
   - Write unit tests

2. **SC-H-02: Oracle Protection**
   - Add authorized oracle list
   - Implement oracle signature verification
   - Add time delay for performance updates
   - Implement oracle rotation
   - Add oracle reputation scoring
   - Write unit tests

## Dependencies

- OpenZeppelin contracts (already imported)
- ECDSA library for signature verification
- No external dependencies required

## Risk Assessment

**High Risks:**
- Slashing mechanism could be abused if not properly tested
- Oracle manipulation could still occur if oracle list is compromised

**Mitigation:**
- Comprehensive unit and integration testing
- Governance controls for oracle management
- Reputation system to remove bad oracles
- Appeal process for unfair slashing

## Success Criteria

- Slashing mechanism implemented and tested
- Oracle protection implemented and tested
- Unit tests passing for both findings
- Integration tests passing
- Gas optimization reviewed
- Documentation updated
