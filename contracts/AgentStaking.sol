// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./PerformanceVerifier.sol";
import "./AIToken.sol";

/**
 * @title Agent Staking System
 * @dev Reputation-based yield farming for AI agents with dynamic APY calculation
 * @notice Allows users to stake AITBC tokens on agent wallets and earn rewards based on agent performance
 */
contract AgentStaking is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    IERC20 public aitbcToken;
    PerformanceVerifier public performanceVerifier;
    
    uint256 public stakeCounter;
    uint256 public baseAPY = 500; // 5% base APY in basis points
    uint256 public maxAPY = 2000; // 20% max APY in basis points
    uint256 public minStakeAmount = 100 * 10**18; // 100 AITBC minimum
    uint256 public maxStakeAmount = 100000 * 10**18; // 100k AITBC maximum
    uint256 public unbondingPeriod = 7 days;
    uint256 public rewardDistributionInterval = 1 days;
    uint256 public platformFeePercentage = 100; // 1% platform fee
    uint256 public earlyUnbondPenalty = 1000; // 10% penalty for early unbonding
    
    // Staking status
    enum StakeStatus { ACTIVE, UNBONDING, COMPLETED, SLASHED }
    
    // Agent performance tier
    enum PerformanceTier { BRONZE, SILVER, GOLD, PLATINUM, DIAMOND }
    
    // Structs
    struct Stake {
        uint256 stakeId;
        address staker;
        address agentWallet;
        uint256 amount;
        uint256 lockPeriod;
        uint256 startTime;
        uint256 endTime;
        StakeStatus status;
        uint256 accumulatedRewards;
        uint256 lastRewardTime;
        uint256 currentAPY;
        PerformanceTier agentTier;
        bool autoCompound;
    }
    
    struct AgentMetrics {
        address agentWallet;
        uint256 totalStaked;
        uint256 stakerCount;
        uint256 totalRewardsDistributed;
        uint256 averageAccuracy;
        uint256 totalSubmissions;
        uint256 successfulSubmissions;
        uint256 lastUpdateTime;
        PerformanceTier currentTier;
        uint256 tierScore;
    }
    
    struct StakingPool {
        address agentWallet;
        uint256 totalStaked;
        uint256 totalRewards;
        uint256 poolAPY;
        uint256 lastDistributionTime;
        mapping(address => uint256) stakerShares;
        address[] stakers;
    }
    
    struct RewardCalculation {
        uint256 baseRewards;
        uint256 performanceBonus;
        uint256 lockBonus;
        uint256 tierBonus;
        uint256 totalRewards;
        uint256 platformFee;
    }
    
    // Mappings
    mapping(uint256 => Stake) public stakes;
    mapping(address => uint256[]) public stakerStakes;
    mapping(address => uint256[]) public agentStakes;
    mapping(address => AgentMetrics) public agentMetrics;
    mapping(address => StakingPool) public stakingPools;
    mapping(PerformanceTier => uint256) public tierMultipliers;
    mapping(uint256 => uint256) public lockPeriodMultipliers;
    
    // Arrays
    address[] public supportedAgents;
    uint256[] public activeStakeIds;
    
    // Events
    event StakeCreated(
        uint256 indexed stakeId,
        address indexed staker,
        address indexed agentWallet,
        uint256 amount,
        uint256 lockPeriod,
        uint256 apy
    );
    
    event StakeUpdated(
        uint256 indexed stakeId,
        uint256 newAmount,
        uint256 newAPY
    );
    
    event RewardsDistributed(
        uint256 indexed stakeId,
        address indexed staker,
        uint256 rewardAmount,
        uint256 platformFee
    );
    
    event StakeUnbonded(
        uint256 indexed stakeId,
        address indexed staker,
        uint256 amount,
        uint256 penalty
    );
    
    event StakeCompleted(
        uint256 indexed stakeId,
        address indexed staker,
        uint256 totalAmount,
        uint256 totalRewards
    );
    
    event AgentTierUpdated(
        address indexed agentWallet,
        PerformanceTier oldTier,
        PerformanceTier newTier,
        uint256 tierScore
    );
    
    event PoolRewardsDistributed(
        address indexed agentWallet,
        uint256 totalRewards,
        uint256 stakerCount
    );
    
    event PlatformFeeCollected(
        uint256 indexed stakeId,
        uint256 feeAmount,
        address indexed collector
    );
    
    // Modifiers
    modifier stakeExists(uint256 _stakeId) {
        require(_stakeId < stakeCounter, "Stake does not exist");
        _;
    }
    
    modifier onlyStakeOwner(uint256 _stakeId) {
        require(stakes[_stakeId].staker == msg.sender, "Not stake owner");
        _;
    }
    
    modifier supportedAgent(address _agentWallet) {
        require(agentMetrics[_agentWallet].agentWallet != address(0) || _agentWallet == address(0), "Agent not supported");
        _;
    }
    
    modifier validStakeAmount(uint256 _amount) {
        require(_amount >= minStakeAmount && _amount <= maxStakeAmount, "Invalid stake amount");
        _;
    }
    
    modifier sufficientBalance(uint256 _amount) {
        require(aitbcToken.balanceOf(msg.sender) >= _amount, "Insufficient balance");
        _;
    }
    
    constructor(address _aitbcToken, address _performanceVerifier) {
        aitbcToken = IERC20(_aitbcToken);
        performanceVerifier = PerformanceVerifier(_performanceVerifier);
        
        // Set tier multipliers (in basis points)
        tierMultipliers[PerformanceTier.BRONZE] = 1000; // 1x
        tierMultipliers[PerformanceTier.SILVER] = 1200; // 1.2x
        tierMultipliers[PerformanceTier.GOLD] = 1500;   // 1.5x
        tierMultipliers[PerformanceTier.PLATINUM] = 2000; // 2x
        tierMultipliers[PerformanceTier.DIAMOND] = 3000; // 3x
        
        // Set lock period multipliers
        lockPeriodMultipliers[30 days] = 1100;   // 1.1x for 30 days
        lockPeriodMultipliers[90 days] = 1250;   // 1.25x for 90 days
        lockPeriodMultipliers[180 days] = 1500;  // 1.5x for 180 days
        lockPeriodMultipliers[365 days] = 2000;  // 2x for 365 days
    }
    
    /**
     * @dev Creates a new stake on an agent wallet
     * @param _agentWallet Address of the agent wallet
     * @param _amount Amount to stake
     * @param _lockPeriod Lock period in seconds
     * @param _autoCompound Whether to auto-compound rewards
     */
    function stakeOnAgent(
        address _agentWallet,
        uint256 _amount,
        uint256 _lockPeriod,
        bool _autoCompound
    ) external 
        supportedAgent(_agentWallet)
        validStakeAmount(_amount)
        sufficientBalance(_amount)
        nonReentrant 
        returns (uint256) 
    {
        require(_lockPeriod >= 1 days, "Lock period too short");
        require(_lockPeriod <= 365 days, "Lock period too long");
        
        uint256 stakeId = stakeCounter++;
        
        // Calculate initial APY
        PerformanceTier agentTier = _getAgentTier(_agentWallet);
        uint256 apy = _calculateAPY(_agentWallet, _lockPeriod, agentTier);
        
        Stake storage stake = stakes[stakeId];
        stake.stakeId = stakeId;
        stake.staker = msg.sender;
        stake.agentWallet = _agentWallet;
        stake.amount = _amount;
        stake.lockPeriod = _lockPeriod;
        stake.startTime = block.timestamp;
        stake.endTime = block.timestamp + _lockPeriod;
        stake.status = StakeStatus.ACTIVE;
        stake.accumulatedRewards = 0;
        stake.lastRewardTime = block.timestamp;
        stake.currentAPY = apy;
        stake.agentTier = agentTier;
        stake.autoCompound = _autoCompound;
        
        // Update agent metrics
        _updateAgentMetrics(_agentWallet, _amount, true);
        
        // Update staking pool
        _updateStakingPool(_agentWallet, msg.sender, _amount, true);
        
        // Update tracking arrays
        stakerStakes[msg.sender].push(stakeId);
        agentStakes[_agentWallet].push(stakeId);
        activeStakeIds.push(stakeId);
        
        // Transfer tokens to contract
        require(aitbcToken.transferFrom(msg.sender, address(this), _amount), "Transfer failed");
        
        emit StakeCreated(stakeId, msg.sender, _agentWallet, _amount, _lockPeriod, apy);
        
        return stakeId;
    }
    
    /**
     * @dev Adds more tokens to an existing stake
     * @param _stakeId Stake ID
     * @param _additionalAmount Additional amount to stake
     */
    function addToStake(
        uint256 _stakeId,
        uint256 _additionalAmount
    ) external 
        stakeExists(_stakeId)
        onlyStakeOwner(_stakeId)
        validStakeAmount(_additionalAmount)
        sufficientBalance(_additionalAmount)
        nonReentrant 
    {
        Stake storage stake = stakes[_stakeId];
        require(stake.status == StakeStatus.ACTIVE, "Stake not active");
        
        // Calculate new APY
        uint256 newTotalAmount = stake.amount + _additionalAmount;
        uint256 newAPY = _calculateAPY(stake.agentWallet, stake.lockPeriod, stake.agentTier);
        
        // Update stake
        stake.amount = newTotalAmount;
        stake.currentAPY = newAPY;
        
        // Update agent metrics
        _updateAgentMetrics(stake.agentWallet, _additionalAmount, true);
        
        // Update staking pool
        _updateStakingPool(stake.agentWallet, msg.sender, _additionalAmount, true);
        
        // Transfer additional tokens
        require(aitbcToken.transferFrom(msg.sender, address(this), _additionalAmount), "Transfer failed");
        
        emit StakeUpdated(_stakeId, newTotalAmount, newAPY);
    }
    
    /**
     * @dev Initiates unbonding for a stake
     * @param _stakeId Stake ID
     */
    function unbondStake(uint256 _stakeId) external 
        stakeExists(_stakeId)
        onlyStakeOwner(_stakeId)
        nonReentrant 
    {
        Stake storage stake = stakes[_stakeId];
        require(stake.status == StakeStatus.ACTIVE, "Stake not active");
        require(block.timestamp >= stake.endTime, "Lock period not ended");
        
        // Calculate final rewards
        _calculateRewards(_stakeId);
        
        stake.status = StakeStatus.UNBONDING;
        
        // Remove from active stakes
        _removeFromActiveStakes(_stakeId);
    }
    
    /**
     * @dev Completes unbonding and returns stake + rewards
     * @param _stakeId Stake ID
     */
    function completeUnbonding(uint256 _stakeId) external 
        stakeExists(_stakeId)
        onlyStakeOwner(_stakeId)
        nonReentrant 
    {
        Stake storage stake = stakes[_stakeId];
        require(stake.status == StakeStatus.UNBONDING, "Stake not unbonding");
        require(block.timestamp >= stake.endTime + unbondingPeriod, "Unbonding period not ended");
        
        uint256 totalAmount = stake.amount;
        uint256 totalRewards = stake.accumulatedRewards;
        
        // Apply early unbonding penalty if applicable
        uint256 penalty = 0;
        if (block.timestamp < stake.endTime + 30 days) {
            penalty = (totalAmount * earlyUnbondPenalty) / 10000;
            totalAmount -= penalty;
        }
        
        stake.status = StakeStatus.COMPLETED;
        
        // Update agent metrics
        _updateAgentMetrics(stake.agentWallet, stake.amount, false);
        
        // Update staking pool
        _updateStakingPool(stake.agentWallet, msg.sender, stake.amount, false);
        
        // Transfer tokens back to staker
        if (totalAmount > 0) {
            require(aitbcToken.transfer(msg.sender, totalAmount), "Stake transfer failed");
        }
        
        if (totalRewards > 0) {
            require(aitbcToken.transfer(msg.sender, totalRewards), "Rewards transfer failed");
        }
        
        emit StakeCompleted(_stakeId, msg.sender, totalAmount, totalRewards);
        emit StakeUnbonded(_stakeId, msg.sender, totalAmount, penalty);
    }
    
    /**
     * @dev Distributes agent earnings to stakers
     * @param _agentWallet Agent wallet address
     * @param _totalEarnings Total earnings to distribute
     */
    function distributeAgentEarnings(
        address _agentWallet,
        uint256 _totalEarnings
    ) external 
        supportedAgent(_agentWallet)
        nonReentrant 
    {
        require(_totalEarnings > 0, "No earnings to distribute");
        
        StakingPool storage pool = stakingPools[_agentWallet];
        require(pool.totalStaked > 0, "No stakers in pool");
        
        // Calculate platform fee
        uint256 platformFee = (_totalEarnings * platformFeePercentage) / 10000;
        uint256 distributableAmount = _totalEarnings - platformFee;
        
        // Transfer platform fee
        if (platformFee > 0) {
            require(aitbcToken.transferFrom(msg.sender, owner(), platformFee), "Platform fee transfer failed");
        }
        
        // Transfer distributable amount to contract
        require(aitbcToken.transferFrom(msg.sender, address(this), distributableAmount), "Earnings transfer failed");
        
        // Distribute to stakers proportionally
        uint256 totalDistributed = 0;
        for (uint256 i = 0; i < pool.stakers.length; i++) {
            address staker = pool.stakers[i];
            uint256 stakerShare = pool.stakerShares[staker];
            uint256 stakerReward = (distributableAmount * stakerShare) / pool.totalStaked;
            
            if (stakerReward > 0) {
                // Find and update all stakes for this staker on this agent
                uint256[] storage stakesForAgent = agentStakes[_agentWallet];
                for (uint256 j = 0; j < stakesForAgent.length; j++) {
                    uint256 stakeId = stakesForAgent[j];
                    Stake storage stake = stakes[stakeId];
                    if (stake.staker == staker && stake.status == StakeStatus.ACTIVE) {
                        stake.accumulatedRewards += stakerReward;
                        break;
                    }
                }
                totalDistributed += stakerReward;
            }
        }
        
        // Update agent metrics
        agentMetrics[_agentWallet].totalRewardsDistributed += totalDistributed;
        
        emit PoolRewardsDistributed(_agentWallet, totalDistributed, pool.stakers.length);
    }
    
    /**
     * @dev Updates agent performance metrics and tier
     * @param _agentWallet Agent wallet address
     * @param _accuracy Latest accuracy score
     * @param _successful Whether the submission was successful
     */
    function updateAgentPerformance(
        address _agentWallet,
        uint256 _accuracy,
        bool _successful
    ) external 
        supportedAgent(_agentWallet)
        nonReentrant 
    {
        AgentMetrics storage metrics = agentMetrics[_agentWallet];
        
        metrics.totalSubmissions++;
        if (_successful) {
            metrics.successfulSubmissions++;
        }
        
        // Update average accuracy (weighted average)
        uint256 totalAccuracy = metrics.averageAccuracy * (metrics.totalSubmissions - 1) + _accuracy;
        metrics.averageAccuracy = totalAccuracy / metrics.totalSubmissions;
        
        metrics.lastUpdateTime = block.timestamp;
        
        // Calculate new tier
        PerformanceTier newTier = _calculateAgentTier(_agentWallet);
        PerformanceTier oldTier = metrics.currentTier;
        
        if (newTier != oldTier) {
            metrics.currentTier = newTier;
            
            // Update APY for all active stakes on this agent
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
    
    /**
     * @dev Adds a supported agent
     * @param _agentWallet Agent wallet address
     * @param _initialTier Initial performance tier
     */
    function addSupportedAgent(
        address _agentWallet,
        PerformanceTier _initialTier
    ) external onlyOwner {
        require(_agentWallet != address(0), "Invalid agent address");
        require(agentMetrics[_agentWallet].agentWallet == address(0), "Agent already supported");
        
        agentMetrics[_agentWallet] = AgentMetrics({
            agentWallet: _agentWallet,
            totalStaked: 0,
            stakerCount: 0,
            totalRewardsDistributed: 0,
            averageAccuracy: 0,
            totalSubmissions: 0,
            successfulSubmissions: 0,
            lastUpdateTime: block.timestamp,
            currentTier: _initialTier,
            tierScore: _getTierScore(_initialTier)
        });
        
        // Initialize staking pool
        stakingPools[_agentWallet].agentWallet = _agentWallet;
        stakingPools[_agentWallet].totalStaked = 0;
        stakingPools[_agentWallet].totalRewards = 0;
        stakingPools[_agentWallet].poolAPY = baseAPY;
        stakingPools[_agentWallet].lastDistributionTime = block.timestamp;
        
        supportedAgents.push(_agentWallet);
    }
    
    /**
     * @dev Removes a supported agent
     * @param _agentWallet Agent wallet address
     */
    function removeSupportedAgent(address _agentWallet) external onlyOwner {
        require(agentMetrics[_agentWallet].agentWallet != address(0), "Agent not supported");
        require(agentMetrics[_agentWallet].totalStaked == 0, "Agent has active stakes");
        
        // Remove from supported agents
        for (uint256 i = 0; i < supportedAgents.length; i++) {
            if (supportedAgents[i] == _agentWallet) {
                supportedAgents[i] = supportedAgents[supportedAgents.length - 1];
                supportedAgents.pop();
                break;
            }
        }
        
        delete agentMetrics[_agentWallet];
        delete stakingPools[_agentWallet];
    }
    
    /**
     * @dev Updates configuration parameters
     * @param _baseAPY New base APY
     * @param _maxAPY New maximum APY
     * @param _platformFee New platform fee percentage
     */
    function updateConfiguration(
        uint256 _baseAPY,
        uint256 _maxAPY,
        uint256 _platformFee
    ) external onlyOwner {
        require(_baseAPY <= _maxAPY, "Base APY cannot exceed max APY");
        require(_maxAPY <= 5000, "Max APY too high"); // Max 50%
        require(_platformFee <= 500, "Platform fee too high"); // Max 5%
        
        baseAPY = _baseAPY;
        maxAPY = _maxAPY;
        platformFeePercentage = _platformFee;
    }
    
    // View functions
    
    /**
     * @dev Gets stake details
     * @param _stakeId Stake ID
     */
    function getStake(uint256 _stakeId) external view stakeExists(_stakeId) returns (
        address staker,
        address agentWallet,
        uint256 amount,
        uint256 lockPeriod,
        uint256 startTime,
        uint256 endTime,
        StakeStatus status,
        uint256 accumulatedRewards,
        uint256 currentAPY,
        PerformanceTier agentTier,
        bool autoCompound
    ) {
        Stake storage stake = stakes[_stakeId];
        return (
            stake.staker,
            stake.agentWallet,
            stake.amount,
            stake.lockPeriod,
            stake.startTime,
            stake.endTime,
            stake.status,
            stake.accumulatedRewards,
            stake.currentAPY,
            stake.agentTier,
            stake.autoCompound
        );
    }
    
    /**
     * @dev Gets agent metrics
     * @param _agentWallet Agent wallet address
     */
    function getAgentMetrics(address _agentWallet) external view returns (
        uint256 totalStaked,
        uint256 stakerCount,
        uint256 totalRewardsDistributed,
        uint256 averageAccuracy,
        uint256 totalSubmissions,
        uint256 successfulSubmissions,
        PerformanceTier currentTier,
        uint256 tierScore
    ) {
        AgentMetrics storage metrics = agentMetrics[_agentWallet];
        return (
            metrics.totalStaked,
            metrics.stakerCount,
            metrics.totalRewardsDistributed,
            metrics.averageAccuracy,
            metrics.totalSubmissions,
            metrics.successfulSubmissions,
            metrics.currentTier,
            metrics.tierScore
        );
    }
    
    /**
     * @dev Gets staking pool information
     * @param _agentWallet Agent wallet address
     */
    function getStakingPool(address _agentWallet) external view returns (
        uint256 totalStaked,
        uint256 totalRewards,
        uint256 poolAPY,
        uint256 stakerCount
    ) {
        StakingPool storage pool = stakingPools[_agentWallet];
        return (
            pool.totalStaked,
            pool.totalRewards,
            pool.poolAPY,
            pool.stakers.length
        );
    }
    
    /**
     * @dev Calculates current rewards for a stake
     * @param _stakeId Stake ID
     */
    function calculateRewards(uint256 _stakeId) external view stakeExists(_stakeId) returns (uint256) {
        Stake storage stake = stakes[_stakeId];
        if (stake.status != StakeStatus.ACTIVE) {
            return stake.accumulatedRewards;
        }
        
        uint256 timeElapsed = block.timestamp - stake.lastRewardTime;
        uint256 yearlyRewards = (stake.amount * stake.currentAPY) / 10000;
        uint256 currentRewards = (yearlyRewards * timeElapsed) / 365 days;
        
        return stake.accumulatedRewards + currentRewards;
    }
    
    /**
     * @dev Gets all stakes for a staker
     * @param _staker Staker address
     */
    function getStakerStakes(address _staker) external view returns (uint256[] memory) {
        return stakerStakes[_staker];
    }
    
    /**
     * @dev Gets all stakes for an agent
     * @param _agentWallet Agent wallet address
     */
    function getAgentStakes(address _agentWallet) external view returns (uint256[] memory) {
        return agentStakes[_agentWallet];
    }
    
    /**
     * @dev Gets all supported agents
     */
    function getSupportedAgents() external view returns (address[] memory) {
        return supportedAgents;
    }
    
    /**
     * @dev Gets all active stake IDs
     */
    function getActiveStakes() external view returns (uint256[] memory) {
        return activeStakeIds;
    }
    
    /**
     * @dev Calculates APY for a stake
     * @param _agentWallet Agent wallet address
     * @param _lockPeriod Lock period
     * @param _agentTier Agent performance tier
     */
    function calculateAPY(
        address _agentWallet,
        uint256 _lockPeriod,
        PerformanceTier _agentTier
    ) external view returns (uint256) {
        return _calculateAPY(_agentWallet, _lockPeriod, _agentTier);
    }
    
    // Internal functions
    
    function _calculateAPY(
        address _agentWallet,
        uint256 _lockPeriod,
        PerformanceTier _agentTier
    ) internal view returns (uint256) {
        uint256 tierMultiplier = tierMultipliers[_agentTier];
        uint256 lockMultiplier = lockPeriodMultipliers[_lockPeriod];
        
        uint256 apy = (baseAPY * tierMultiplier * lockMultiplier) / (10000 * 10000);
        
        // Cap at maximum APY
        return apy > maxAPY ? maxAPY : apy;
    }
    
    function _calculateRewards(uint256 _stakeId) internal {
        Stake storage stake = stakes[_stakeId];
        if (stake.status != StakeStatus.ACTIVE) {
            return;
        }
        
        uint256 timeElapsed = block.timestamp - stake.lastRewardTime;
        uint256 yearlyRewards = (stake.amount * stake.currentAPY) / 10000;
        uint256 currentRewards = (yearlyRewards * timeElapsed) / 365 days;
        
        stake.accumulatedRewards += currentRewards;
        stake.lastRewardTime = block.timestamp;
        
        // Auto-compound if enabled
        if (stake.autoCompound && currentRewards >= minStakeAmount) {
            stake.amount += currentRewards;
            stake.accumulatedRewards = 0;
        }
    }
    
    function _getAgentTier(address _agentWallet) internal view returns (PerformanceTier) {
        AgentMetrics storage metrics = agentMetrics[_agentWallet];
        return metrics.currentTier;
    }
    
    function _calculateAgentTier(address _agentWallet) internal view returns (PerformanceTier) {
        AgentMetrics storage metrics = agentMetrics[_agentWallet];
        
        uint256 successRate = metrics.totalSubmissions > 0 ? 
            (metrics.successfulSubmissions * 100) / metrics.totalSubmissions : 0;
        
        uint256 score = (metrics.averageAccuracy * 50) / 100 + (successRate * 50) / 100;
        
        if (score >= 95) return PerformanceTier.DIAMOND;
        if (score >= 90) return PerformanceTier.PLATINUM;
        if (score >= 80) return PerformanceTier.GOLD;
        if (score >= 70) return PerformanceTier.SILVER;
        return PerformanceTier.BRONZE;
    }
    
    function _getTierScore(PerformanceTier _tier) internal pure returns (uint256) {
        if (_tier == PerformanceTier.DIAMOND) return 95;
        if (_tier == PerformanceTier.PLATINUM) return 90;
        if (_tier == PerformanceTier.GOLD) return 80;
        if (_tier == PerformanceTier.SILVER) return 70;
        return 60;
    }
    
    function _updateAgentMetrics(address _agentWallet, uint256 _amount, bool _isStake) internal {
        AgentMetrics storage metrics = agentMetrics[_agentWallet];
        
        if (_isStake) {
            metrics.totalStaked += _amount;
            if (metrics.totalStaked == _amount) {
                metrics.stakerCount = 1;
            }
        } else {
            metrics.totalStaked -= _amount;
            if (metrics.totalStaked == 0) {
                metrics.stakerCount = 0;
            }
        }
        
        metrics.currentTier = _calculateAgentTier(_agentWallet);
        metrics.tierScore = _getTierScore(metrics.currentTier);
    }
    
    function _updateStakingPool(address _agentWallet, address _staker, uint256 _amount, bool _isStake) internal {
        StakingPool storage pool = stakingPools[_agentWallet];
        
        if (_isStake) {
            if (pool.stakerShares[_staker] == 0) {
                pool.stakers.push(_staker);
            }
            pool.stakerShares[_staker] += _amount;
            pool.totalStaked += _amount;
        } else {
            pool.stakerShares[_staker] -= _amount;
            pool.totalStaked -= _amount;
            
            // Remove staker from array if no shares left
            if (pool.stakerShares[_staker] == 0) {
                for (uint256 i = 0; i < pool.stakers.length; i++) {
                    if (pool.stakers[i] == _staker) {
                        pool.stakers[i] = pool.stakers[pool.stakers.length - 1];
                        pool.stakers.pop();
                        break;
                    }
                }
            }
        }
        
        // Update pool APY
        if (pool.totalStaked > 0) {
            pool.poolAPY = _calculateAPY(_agentWallet, 30 days, agentMetrics[_agentWallet].currentTier);
        }
    }
    
    function _removeFromActiveStakes(uint256 _stakeId) internal {
        for (uint256 i = 0; i < activeStakeIds.length; i++) {
            if (activeStakeIds[i] == _stakeId) {
                activeStakeIds[i] = activeStakeIds[activeStakeIds.length - 1];
                activeStakeIds.pop();
                break;
            }
        }
    }
    
    /**
     * @dev Emergency pause function
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @dev Unpause function
     */
    function unpause() external onlyOwner {
        _unpause();
    }
}
