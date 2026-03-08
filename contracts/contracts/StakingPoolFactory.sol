// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../interfaces/IModularContracts.sol";
import "./ContractRegistry.sol";

/**
 * @title StakingPoolFactory
 * @dev Dynamic staking pool creation with performance-based APY
 * @notice Integrates with AgentStaking, PerformanceAggregator, and RewardDistributor
 */
contract StakingPoolFactory is IStakingPoolFactory, Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    
    // State variables
    uint256 public version = 1;
    IERC20 public stakingToken;
    ContractRegistry public registry;
    IPerformanceAggregator public performanceAggregator;
    IRewardDistributor public rewardDistributor;
    
    // Staking pool
    struct StakingPool {
        uint256 poolId;
        string poolName;
        uint256 baseAPY; // In basis points (10000 = 100%)
        uint256 currentAPY;
        uint256 totalStaked;
        uint256 lockPeriod;
        uint256 minStakeAmount;
        uint256 maxStakeAmount;
        uint256 totalStakers;
        uint256 createdRewards;
        uint256 distributedRewards;
        bool isActive;
        uint256 createdAt;
        address creator;
        string description;
    }
    
    // Staking position
    struct StakingPosition {
        uint256 positionId;
        uint256 poolId;
        address staker;
        uint256 amount;
        uint256 lockStart;
        uint256 lockEnd;
        uint256 apyAtStake;
        uint256 accumulatedRewards;
        uint256 lastRewardTime;
        bool isActive;
        bool isWithdrawn;
    }
    
    // Pool performance metrics
    struct PoolPerformance {
        uint256 totalRewardsGenerated;
        uint256 averageStakingDuration;
        uint256 retentionRate; // In basis points
        uint256 utilizationRate; // In basis points
        uint256 distributedRewards;
        uint256 lastUpdated;
    }
    
    // Mappings
    mapping(uint256 => StakingPool) public stakingPools;
    mapping(uint256 => StakingPosition) public stakingPositions;
    mapping(uint256 => uint256[]) public poolStakers;
    mapping(address => uint256[]) public stakerPositions;
    mapping(uint256 => PoolPerformance) public poolPerformance;
    mapping(string => uint256) public poolNameToId;
    
    // Counters
    uint256 public poolCounter;
    uint256 public positionCounter;
    uint256[] public activePoolIds;
    
    // Constants
    uint256 public constant MIN_BASE_APY = 100; // 1% minimum
    uint256 public constant MAX_BASE_APY = 5000; // 50% maximum
    uint256 public constant DEFAULT_LOCK_PERIOD = 30 days;
    uint256 public constant MAX_LOCK_PERIOD = 365 days;
    uint256 public constant DEFAULT_MIN_STAKE = 100 * 10**18; // 100 tokens
    uint256 public constant DEFAULT_MAX_STAKE = 1000000 * 10**18; // 1M tokens
    uint256 public constant PERFORMANCE_UPDATE_INTERVAL = 1 days;
    uint256 public constant BASIS_POINTS = 10000;
    
    // Events
    event PoolCreated(uint256 indexed poolId, string poolName, uint256 baseAPY, uint256 lockPeriod);
    event PoolUpdated(uint256 indexed poolId, uint256 newAPY);
    event Staked(uint256 indexed positionId, uint256 indexed poolId, address indexed staker, uint256 amount);
    event Unstaked(uint256 indexed positionId, address indexed staker, uint256 amount, uint256 rewards);
    event RewardsDistributed(uint256 indexed poolId, uint256 totalAmount);
    event PoolDeactivated(uint256 indexed poolId);
    event PerformanceUpdated(uint256 indexed poolId, uint256 newAPY);
    
    // Errors
    error InvalidAmount(uint256 amount);
    error PoolNotFound(uint256 poolId);
    error PoolNotActive(uint256 poolId);
    error PositionNotFound(uint256 positionId);
    error PositionNotActive(uint256 positionId);
    error InvalidLockPeriod(uint256 period);
    error InvalidAPY(uint256 apy);
    error InsufficientBalance(uint256 requested, uint256 available);
    error LockPeriodNotEnded(uint256 positionId);
    error MaxStakeReached(uint256 poolId);
    error RegistryNotSet();
    error NotAuthorized();
    
    modifier validAmount(uint256 amount) {
        if (amount == 0) revert InvalidAmount(amount);
        _;
    }
    
    modifier validPool(uint256 poolId) {
        if (stakingPools[poolId].poolId == 0) revert PoolNotFound(poolId);
        if (!stakingPools[poolId].isActive) revert PoolNotActive(poolId);
        _;
    }
    
    modifier validPosition(uint256 positionId) {
        if (stakingPositions[positionId].positionId == 0) revert PositionNotFound(positionId);
        if (!stakingPositions[positionId].isActive) revert PositionNotActive(positionId);
        _;
    }
    
    modifier validLockPeriod(uint256 period) {
        if (period < DEFAULT_LOCK_PERIOD || period > MAX_LOCK_PERIOD) {
            revert InvalidLockPeriod(period);
        }
        _;
    }
    
    modifier validAPY(uint256 apy) {
        if (apy < MIN_BASE_APY || apy > MAX_BASE_APY) revert InvalidAPY(apy);
        _;
    }
    
    modifier onlyAuthorized() {
        if (msg.sender != owner() && msg.sender != address(rewardDistributor)) {
            revert NotAuthorized();
        }
        _;
    }
    
    modifier registrySet() {
        if (address(registry) == address(0)) revert RegistryNotSet();
        _;
    }
    
    constructor(address _stakingToken) {
        stakingToken = IERC20(_stakingToken);
    }
    
    /**
     * @dev Initialize the staking pool factory (implements IModularContract)
     */
    function initialize(address _registry) external override {
        require(address(registry) == address(0), "Already initialized");
        registry = ContractRegistry(_registry);
        
        // Register this contract
        bytes32 contractId = keccak256(abi.encodePacked("StakingPoolFactory"));
        registry.registerContract(contractId, address(this));
        
        // Get integration addresses from registry
        performanceAggregator = IPerformanceAggregator(registry.getContract(keccak256(abi.encodePacked("PerformanceAggregator"))));
        rewardDistributor = IRewardDistributor(registry.getContract(keccak256(abi.encodePacked("RewardDistributor"))));
    }
    
    /**
     * @dev Upgrade the contract
     */
    function upgrade(address newImplementation) external override onlyOwner {
        version++;
        // Implementation upgrade logic would go here
    }
    
    /**
     * @dev Pause the contract
     */
    function pause() external override onlyOwner {
        _pause();
    }
    
    /**
     * @dev Unpause the contract
     */
    function unpause() external override onlyOwner {
        _unpause();
    }
    
    /**
     * @dev Get current version
     */
    function getVersion() external view override returns (uint256) {
        return version;
    }
    
    /**
     * @dev Create a new staking pool
     */
    function createPool(string memory poolName, uint256 baseAPY, uint256 lockPeriod) 
        external 
        override 
        onlyAuthorized 
        whenNotPaused 
        validAPY(baseAPY)
        validLockPeriod(lockPeriod)
        nonReentrant 
        returns (uint256) 
    {
        require(bytes(poolName).length > 0, "Empty pool name");
        require(poolNameToId[poolName] == 0, "Pool name already exists");
        
        uint256 poolId = ++poolCounter;
        stakingPools[poolId] = StakingPool({
            poolId: poolId,
            poolName: poolName,
            baseAPY: baseAPY,
            currentAPY: baseAPY,
            totalStaked: 0,
            lockPeriod: lockPeriod,
            minStakeAmount: DEFAULT_MIN_STAKE,
            maxStakeAmount: DEFAULT_MAX_STAKE,
            totalStakers: 0,
            createdRewards: 0,
            distributedRewards: 0,
            isActive: true,
            createdAt: block.timestamp,
            creator: msg.sender,
            description: ""
        });
        
        poolNameToId[poolName] = poolId;
        activePoolIds.push(poolId);
        
        // Initialize performance tracking
        poolPerformance[poolId] = PoolPerformance({
            totalRewardsGenerated: 0,
            averageStakingDuration: 0,
            retentionRate: 10000, // 100% initial
            utilizationRate: 0,
            distributedRewards: 0,
            lastUpdated: block.timestamp
        });
        
        emit PoolCreated(poolId, poolName, baseAPY, lockPeriod);
    }
    
    /**
     * @dev Create a staking pool with custom parameters
     */
    function createPoolWithParameters(
        string memory poolName,
        uint256 baseAPY,
        uint256 lockPeriod,
        uint256 minStakeAmount,
        uint256 maxStakeAmount,
        string memory description
    ) 
        external 
        onlyAuthorized 
        whenNotPaused 
        validAPY(baseAPY)
        validLockPeriod(lockPeriod)
        nonReentrant 
    {
        require(bytes(poolName).length > 0, "Empty pool name");
        require(poolNameToId[poolName] == 0, "Pool name already exists");
        require(minStakeAmount > 0 && minStakeAmount <= maxStakeAmount, "Invalid stake amounts");
        
        uint256 poolId = ++poolCounter;
        stakingPools[poolId] = StakingPool({
            poolId: poolId,
            poolName: poolName,
            baseAPY: baseAPY,
            currentAPY: baseAPY,
            totalStaked: 0,
            lockPeriod: lockPeriod,
            minStakeAmount: minStakeAmount,
            maxStakeAmount: maxStakeAmount,
            totalStakers: 0,
            createdRewards: 0,
            distributedRewards: 0,
            isActive: true,
            createdAt: block.timestamp,
            creator: msg.sender,
            description: description
        });
        
        poolNameToId[poolName] = poolId;
        activePoolIds.push(poolId);
        
        // Initialize performance tracking
        poolPerformance[poolId] = PoolPerformance({
            totalRewardsGenerated: 0,
            averageStakingDuration: 0,
            retentionRate: 10000,
            utilizationRate: 0,
            distributedRewards: 0,
            lastUpdated: block.timestamp
        });
        
        emit PoolCreated(poolId, poolName, baseAPY, lockPeriod);
    }
    
    /**
     * @dev Update pool APY
     */
    function updatePoolAPY(uint256 poolId, uint256 newAPY) 
        external 
        override 
        onlyAuthorized 
        whenNotPaused 
        validPool(poolId)
        validAPY(newAPY)
        nonReentrant 
    {
        StakingPool storage pool = stakingPools[poolId];
        pool.currentAPY = newAPY;
        
        emit PoolUpdated(poolId, newAPY);
    }
    
    /**
     * @dev Stake in a pool
     */
    function stakeInPool(uint256 poolId, uint256 amount) 
        external 
        override 
        whenNotPaused 
        validPool(poolId)
        validAmount(amount)
        nonReentrant 
    {
        StakingPool storage pool = stakingPools[poolId];
        
        // Check stake limits
        if (amount < pool.minStakeAmount) {
            revert InvalidAmount(amount);
        }
        
        if (pool.totalStaked + amount > pool.maxStakeAmount) {
            revert MaxStakeReached(poolId);
        }
        
        // Check user balance
        uint256 userBalance = stakingToken.balanceOf(msg.sender);
        if (amount > userBalance) {
            revert InsufficientBalance(amount, userBalance);
        }
        
        // Create staking position
        uint256 positionId = ++positionCounter;
        stakingPositions[positionId] = StakingPosition({
            positionId: positionId,
            poolId: poolId,
            staker: msg.sender,
            amount: amount,
            lockStart: block.timestamp,
            lockEnd: block.timestamp + pool.lockPeriod,
            apyAtStake: pool.currentAPY,
            accumulatedRewards: 0,
            lastRewardTime: block.timestamp,
            isActive: true,
            isWithdrawn: false
        });
        
        // Update pool
        pool.totalStaked += amount;
        pool.totalStakers++;
        poolStakers[poolId].push(positionId);
        stakerPositions[msg.sender].push(positionId);
        
        // Update performance metrics
        _updatePoolPerformance(poolId);
        
        // Transfer tokens
        stakingToken.safeTransferFrom(msg.sender, address(this), amount);
        
        emit Staked(positionId, poolId, msg.sender, amount);
    }
    
    /**
     * @dev Unstake from a pool
     */
    function unstakeFromPool(uint256 poolId, uint256 amount) 
        external 
        override 
        whenNotPaused 
        validPool(poolId)
        validAmount(amount)
        nonReentrant 
    {
        // Find user's position in the pool
        uint256[] memory userPositions = stakerPositions[msg.sender];
        uint256 positionId = 0;
        bool found = false;
        
        for (uint256 i = 0; i < userPositions.length; i++) {
            if (stakingPositions[userPositions[i]].poolId == poolId && 
                stakingPositions[userPositions[i]].isActive &&
                !stakingPositions[userPositions[i]].isWithdrawn) {
                positionId = userPositions[i];
                found = true;
                break;
            }
        }
        
        if (!found) {
            revert PositionNotFound(positionId);
        }
        
        StakingPosition storage position = stakingPositions[positionId];
        
        // Check lock period
        if (block.timestamp < position.lockEnd) {
            revert LockPeriodNotEnded(positionId);
        }
        
        // Check amount
        if (amount > position.amount) {
            revert InvalidAmount(amount);
        }
        
        // Calculate rewards
        uint256 rewards = _calculateRewards(position);
        position.accumulatedRewards += rewards;
        
        // Update position
        position.amount -= amount;
        if (position.amount == 0) {
            position.isActive = false;
            position.isWithdrawn = true;
        }
        
        // Update pool
        StakingPool storage pool = stakingPools[poolId];
        pool.totalStaked -= amount;
        if (position.amount == 0) {
            pool.totalStakers--;
        }
        
        // Update performance metrics
        _updatePoolPerformance(poolId);
        
        // Transfer tokens and rewards
        stakingToken.safeTransfer(msg.sender, amount);
        
        if (rewards > 0 && address(rewardDistributor) != address(0)) {
            // Create reward claim
            uint256 rewardPoolId = 1; // Assuming first pool, or get it dynamically
            rewardDistributor.createRewardPool(address(stakingToken), rewards);
            rewardDistributor.distributeRewards(
                rewardPoolId,
                new address[](1),
                new uint256[](1)
            );
        }
        
        emit Unstaked(positionId, msg.sender, amount, rewards);
    }
    
    /**
     * @dev Get pool performance
     */
    function getPoolPerformance(uint256 poolId) external view override returns (uint256) {
        StakingPool memory pool = stakingPools[poolId];
        PoolPerformance memory performance = poolPerformance[poolId];
        
        // Calculate performance score based on multiple factors
        uint256 utilizationScore = pool.totalStaked > 0 ? 
            (pool.totalStaked * 10000) / pool.maxStakeAmount : 0;
        
        uint256 retentionScore = performance.retentionRate;
        
        uint256 rewardEfficiency = performance.totalRewardsGenerated > 0 ? 
            (performance.distributedRewards * 10000) / performance.totalRewardsGenerated : 10000;
        
        // Weighted average performance score
        uint256 performanceScore = (utilizationScore * 40 + retentionScore * 30 + rewardEfficiency * 30) / 100;
        
        return performanceScore;
    }
    
    /**
     * @dev Calculate rewards for a position
     */
    function _calculateRewards(StakingPosition memory position) internal view returns (uint256) {
        uint256 timeElapsed = block.timestamp - position.lastRewardTime;
        uint256 stakingDuration = block.timestamp - position.lockStart;
        
        // Base rewards calculation
        uint256 baseRewards = (position.amount * position.apyAtStake * timeElapsed) / (BASIS_POINTS * 365 days);
        
        // Performance bonus
        uint256 performanceBonus = 0;
        if (address(performanceAggregator) != address(0)) {
            uint256 reputationScore = performanceAggregator.getReputationScore(position.staker);
            uint256 multiplier = performanceAggregator.calculateAPYMultiplier(reputationScore);
            performanceBonus = (baseRewards * (multiplier - BASIS_POINTS)) / BASIS_POINTS;
        }
        
        return baseRewards + performanceBonus;
    }
    
    /**
     * @dev Update pool performance metrics
     */
    function _updatePoolPerformance(uint256 poolId) internal {
        PoolPerformance storage performance = poolPerformance[poolId];
        StakingPool storage pool = stakingPools[poolId];
        
        // Update utilization rate
        performance.utilizationRate = pool.totalStaked > 0 ? 
            (pool.totalStaked * 10000) / pool.maxStakeAmount : 0;
        
        // Update retention rate (simplified calculation)
        if (pool.totalStakers > 0) {
            uint256 activePositions = 0;
            uint256[] memory positions = poolStakers[poolId];
            for (uint256 i = 0; i < positions.length; i++) {
                if (stakingPositions[positions[i]].isActive) {
                    activePositions++;
                }
            }
            performance.retentionRate = (activePositions * 10000) / pool.totalStakers;
        }
        
        // Update distributed rewards (simplified)
        performance.distributedRewards = performance.totalRewardsGenerated; // Simplified for now
        
        performance.lastUpdated = block.timestamp;
    }
    
    /**
     * @dev Get pool details
     */
    function getPoolDetails(uint256 poolId) external view returns (
        string memory poolName,
        uint256 baseAPY,
        uint256 currentAPY,
        uint256 totalStaked,
        uint256 lockPeriod,
        uint256 totalStakers,
        bool isActive,
        string memory description
    ) {
        StakingPool memory pool = stakingPools[poolId];
        return (
            pool.poolName,
            pool.baseAPY,
            pool.currentAPY,
            pool.totalStaked,
            pool.lockPeriod,
            pool.totalStakers,
            pool.isActive,
            pool.description
        );
    }
    
    /**
     * @dev Get position details
     */
    function getPositionDetails(uint256 positionId) external view returns (
        uint256 poolId,
        address staker,
        uint256 amount,
        uint256 lockStart,
        uint256 lockEnd,
        uint256 apyAtStake,
        uint256 accumulatedRewards,
        bool isActive,
        bool isWithdrawn
    ) {
        StakingPosition memory position = stakingPositions[positionId];
        return (
            position.poolId,
            position.staker,
            position.amount,
            position.lockStart,
            position.lockEnd,
            position.apyAtStake,
            position.accumulatedRewards,
            position.isActive,
            position.isWithdrawn
        );
    }
    
    /**
     * @dev Get user positions
     */
    function getUserPositions(address user) external view returns (uint256[] memory) {
        return stakerPositions[user];
    }
    
    /**
     * @dev Get pool stakers
     */
    function getPoolStakers(uint256 poolId) external view returns (uint256[] memory) {
        return poolStakers[poolId];
    }
    
    /**
     * @dev Get active pool IDs
     */
    function getActivePoolIds() external view returns (uint256[] memory) {
        return activePoolIds;
    }
    
    /**
     * @dev Get pool by name
     */
    function getPoolByName(string memory poolName) external view returns (uint256) {
        return poolNameToId[poolName];
    }
    
    /**
     * @dev Deactivate a pool
     */
    function deactivatePool(uint256 poolId) external onlyAuthorized validPool(poolId) {
        stakingPools[poolId].isActive = false;
        
        // Remove from active pools
        for (uint256 i = 0; i < activePoolIds.length; i++) {
            if (activePoolIds[i] == poolId) {
                activePoolIds[i] = activePoolIds[activePoolIds.length - 1];
                activePoolIds.pop();
                break;
            }
        }
        
        emit PoolDeactivated(poolId);
    }
    
    /**
     * @dev Emergency withdraw
     */
    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(stakingToken)) {
            stakingToken.safeTransfer(msg.sender, amount);
        } else {
            IERC20(token).safeTransfer(msg.sender, amount);
        }
    }
    
    /**
     * @dev Get factory statistics
     */
    function getFactoryStats() external view returns (
        uint256 totalPools,
        uint256 activePools,
        uint256 totalStaked,
        uint256 totalStakers,
        uint256 totalPositions
    ) {
        uint256 _totalStaked = 0;
        uint256 _totalStakers = 0;
        
        for (uint256 i = 0; i < activePoolIds.length; i++) {
            StakingPool memory pool = stakingPools[activePoolIds[i]];
            _totalStaked += pool.totalStaked;
            _totalStakers += pool.totalStakers;
        }
        
        return (
            poolCounter,
            activePoolIds.length,
            _totalStaked,
            _totalStakers,
            positionCounter
        );
    }
}
