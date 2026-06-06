// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/math/SafeMath.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/**
 * @title GPUStaking
 * @dev GPU resource staking and reward distribution for AITBC agents
 * @notice Enables providers to stake GPU resources and earn rewards
 */
contract GPUStaking is Ownable, ReentrancyGuard {
    using SafeMath for uint256;

    // GPU resource structure
    struct GPUResource {
        address provider;
        uint256 gpuPower;        // Computational power units
        uint256 lockPeriod;      // Lock period in seconds
        uint256 stakeAmount;     // AITBC tokens staked
        uint256 rewardRate;      // Reward rate per second
        uint256 reputation;      // Provider reputation score
        uint256 startTime;       // When staking started
        uint256 lastRewardTime;  // Last reward calculation time
        bool isActive;           // Whether resource is active
        string gpuSpecs;         // GPU specifications (JSON)
    }

    // Staking pool structure
    struct StakingPool {
        uint256 totalGPUPower;
        uint256 totalStaked;
        uint256 rewardPool;
        uint256 rewardRate;
        uint256 utilizationRate; // Current utilization (0-10000 = 0-100%)
        bool isActive;
        mapping(address => uint256) providerContributions;
    }

    // Reward calculation structure
    struct RewardInfo {
        uint256 totalRewards;
        uint256 pendingRewards;
        uint256 lastClaimTime;
        uint256 rewardHistory;
    }

    // State variables
    IERC20 public stakingToken;
    mapping(address => GPUResource) public gpuResources;
    mapping(uint256 => StakingPool) public stakingPools;
    mapping(address => RewardInfo) public rewards;
    
    uint256 public poolCounter;
    uint256 public constant MAX_UTILIZATION = 10000; // 100%
    uint256 public constant SECONDS_PER_DAY = 86400;
    
    // Governance parameters
    uint256 public minStakeAmount = 100e18; // 100 AITBC
    uint256 public minLockPeriod = 7 days;
    uint256 public maxLockPeriod = 365 days;
    uint256 public baseRewardRate = 1e15; // 0.001 AITBC per GPU unit per second
    
    // Events
    event GPUStaked(
        address indexed provider,
        uint256 indexed poolId,
        uint256 gpuPower,
        uint256 stakeAmount,
        uint256 lockPeriod
    );
    
    event GPUUnstaked(
        address indexed provider,
        uint256 indexed poolId,
        uint256 gpuPower,
        uint256 stakeAmount
    );
    
    event RewardsClaimed(
        address indexed provider,
        uint256 rewardAmount
    );
    
    event PoolCreated(
        uint256 indexed poolId,
        string name,
        uint256 rewardRate
    );
    
    event RewardPoolUpdated(
        uint256 indexed poolId,
        uint256 newAmount
    );

    modifier validPool(uint256 poolId) {
        require(stakingPools[poolId].isActive, "Invalid pool");
        _;
    }

    modifier onlyProvider(address provider) {
        require(gpuResources[provider].isActive, "Not a provider");
        _;
    }

    constructor(address _stakingToken) {
        stakingToken = IERC20(_stakingToken);
        
        // Create default staking pool
        _createPool("Default GPU Pool", baseRewardRate);
    }

    /**
     * @dev Stake GPU resources
     * @param poolId ID of the staking pool
     * @param gpuPower Computational power units
     * @param stakeAmount Amount of AITBC tokens to stake
     * @param lockPeriod Lock period in seconds
     * @param gpuSpecs GPU specifications (JSON string)
     */
    function stakeGPU(
        uint256 poolId,
        uint256 gpuPower,
        uint256 stakeAmount,
        uint256 lockPeriod,
        string calldata gpuSpecs
    ) external nonReentrant validPool(poolId) {
        require(gpuPower > 0, "Invalid GPU power");
        require(stakeAmount >= minStakeAmount, "Below minimum stake");
        require(lockPeriod >= minLockPeriod && lockPeriod <= maxLockPeriod, "Invalid lock period");
        
        // Transfer staking tokens
        require(
            stakingToken.transferFrom(msg.sender, address(this), stakeAmount),
            "Transfer failed"
        );
        
        // Create or update GPU resource
        GPUResource storage resource = gpuResources[msg.sender];
        if (!resource.isActive) {
            resource.provider = msg.sender;
            resource.reputation = 100; // Start with base reputation
            resource.isActive = true;
        }
        
        resource.gpuPower = resource.gpuPower.add(gpuPower);
        resource.stakeAmount = resource.stakeAmount.add(stakeAmount);
        resource.lockPeriod = lockPeriod;
        resource.startTime = block.timestamp;
        resource.lastRewardTime = block.timestamp;
        resource.gpuSpecs = gpuSpecs;
        
        // Update staking pool
        StakingPool storage pool = stakingPools[poolId];
        pool.totalGPUPower = pool.totalGPUPower.add(gpuPower);
        pool.totalStaked = pool.totalStaked.add(stakeAmount);
        pool.providerContributions[msg.sender] = pool.providerContributions[msg.sender].add(gpuPower);
        
        // Calculate reward rate based on reputation and utilization
        resource.rewardRate = _calculateRewardRate(msg.sender, poolId);
        
        emit GPUStaked(msg.sender, poolId, gpuPower, stakeAmount, lockPeriod);
    }

    /**
     * @dev Unstake GPU resources
     * @param poolId ID of the staking pool
     * @param gpuPower Amount of GPU power to unstake
     */
    function unstakeGPU(
        uint256 poolId,
        uint256 gpuPower
    ) external nonReentrant validPool(poolId) onlyProvider(msg.sender) {
        GPUResource storage resource = gpuResources[msg.sender];
        require(resource.gpuPower >= gpuPower, "Insufficient GPU power");
        
        // Check lock period
        require(
            block.timestamp >= resource.startTime.add(resource.lockPeriod),
            "Still locked"
        );
        
        // Calculate proportional stake amount to return
        uint256 stakeToReturn = (gpuPower.mul(resource.stakeAmount)).div(resource.gpuPower);
        
        // Update resource
        resource.gpuPower = resource.gpuPower.sub(gpuPower);
        resource.stakeAmount = resource.stakeAmount.sub(stakeToReturn);
        
        if (resource.gpuPower == 0) {
            resource.isActive = false;
        }
        
        // Update pool
        StakingPool storage pool = stakingPools[poolId];
        pool.totalGPUPower = pool.totalGPUPower.sub(gpuPower);
        pool.totalStaked = pool.totalStaked.sub(stakeToReturn);
        pool.providerContributions[msg.sender] = pool.providerContributions[msg.sender].sub(gpuPower);
        
        // Return staked tokens
        require(stakingToken.transfer(msg.sender, stakeToReturn), "Transfer failed");
        
        emit GPUUnstaked(msg.sender, poolId, gpuPower, stakeToReturn);
    }

    /**
     * @dev Claim pending rewards
     * @param poolId ID of the staking pool
     */
    function claimRewards(uint256 poolId) external nonReentrant validPool(poolId) onlyProvider(msg.sender) {
        uint256 rewardAmount = _calculatePendingRewards(msg.sender, poolId);
        
        require(rewardAmount > 0, "No rewards to claim");
        
        // Update reward info
        RewardInfo storage rewardInfo = rewards[msg.sender];
        rewardInfo.totalRewards = rewardInfo.totalRewards.add(rewardAmount);
        rewardInfo.pendingRewards = 0;
        rewardInfo.lastClaimTime = block.timestamp;
        
        // Transfer rewards
        require(stakingToken.transfer(msg.sender, rewardAmount), "Transfer failed");
        
        emit RewardsClaimed(msg.sender, rewardAmount);
    }

    /**
     * @dev Create new staking pool
     * @param name Pool name
     * @param rewardRate Base reward rate
     */
    function createPool(
        string calldata name,
        uint256 rewardRate
    ) external onlyOwner {
        _createPool(name, rewardRate);
    }

    /**
     * @dev Update reward pool
     * @param poolId ID of the pool
     * @param amount Amount to add to reward pool
     */
    function updateRewardPool(
        uint256 poolId,
        uint256 amount
    ) external onlyOwner validPool(poolId) {
        require(stakingToken.transferFrom(msg.sender, address(this), amount), "Transfer failed");
        
        StakingPool storage pool = stakingPools[poolId];
        pool.rewardPool = pool.rewardPool.add(amount);
        
        emit RewardPoolUpdated(poolId, amount);
    }

    /**
     * @dev Update pool utilization rate
     * @param poolId ID of the pool
     * @param utilizationRate Utilization rate (0-10000 = 0-100%)
     */
    function updateUtilizationRate(
        uint256 poolId,
        uint256 utilizationRate
    ) external onlyOwner validPool(poolId) {
        require(utilizationRate <= MAX_UTILIZATION, "Invalid utilization");
        
        StakingPool storage pool = stakingPools[poolId];
        pool.utilizationRate = utilizationRate;
    }

    /**
     * @dev Update provider reputation
     * @param provider Provider address
     * @param reputation New reputation score
     */
    function updateProviderReputation(
        address provider,
        uint256 reputation
    ) external onlyOwner {
        require(gpuResources[provider].isActive, "Provider not active");
        
        gpuResources[provider].reputation = reputation;
        
        // Recalculate reward rates for all pools
        for (uint256 i = 1; i <= poolCounter; i++) {
            if (stakingPools[i].isActive) {
                gpuResources[provider].rewardRate = _calculateRewardRate(provider, i);
            }
        }
    }

    /**
     * @dev Get pending rewards
     * @param provider Provider address
     * @param poolId ID of the pool
     * @return rewardAmount Pending reward amount
     */
    function getPendingRewards(
        address provider,
        uint256 poolId
    ) external view returns (uint256) {
        return _calculatePendingRewards(provider, poolId);
    }

    /**
     * @dev Get provider info
     * @param provider Provider address
     * @return gpuPower Total GPU power
     * @return stakeAmount Total stake amount
     * @return reputation Reputation score
     * @return rewardRate Current reward rate
     */
    function getProviderInfo(
        address provider
    ) external view returns (
        uint256 gpuPower,
        uint256 stakeAmount,
        uint256 reputation,
        uint256 rewardRate
    ) {
        GPUResource storage resource = gpuResources[provider];
        return (
            resource.gpuPower,
            resource.stakeAmount,
            resource.reputation,
            resource.rewardRate
        );
    }

    /**
     * @dev Get pool statistics
     * @param poolId ID of the pool
     * @return totalGPUPower Total GPU power in pool
     * @return totalStaked Total amount staked
     * @return utilizationRate Current utilization rate
     * @return activeProviders Number of active providers
     */
    function getPoolStats(
        uint256 poolId
    ) external view returns (
        uint256 totalGPUPower,
        uint256 totalStaked,
        uint256 utilizationRate,
        uint256 activeProviders
    ) {
        StakingPool storage pool = stakingPools[poolId];
        return (
            pool.totalGPUPower,
            pool.totalStaked,
            pool.utilizationRate,
            _countActiveProviders(poolId)
        );
    }

    /**
     * @dev Calculate pending rewards for provider
     * @param provider Provider address
     * @param poolId ID of the pool
     * @return rewardAmount Pending reward amount
     */
    function _calculatePendingRewards(
        address provider,
        uint256 poolId
    ) internal view returns (uint256) {
        GPUResource storage resource = gpuResources[provider];
        StakingPool storage pool = stakingPools[poolId];
        
        if (!resource.isActive || pool.totalGPUPower == 0) {
            return 0;
        }
        
        uint256 timePassed = block.timestamp.sub(resource.lastRewardTime);
        uint256 providerShare = (resource.gpuPower.mul(1e18)).div(pool.totalGPUPower);
        
        // Base rewards * utilization * provider share * time
        uint256 baseRewards = pool.rewardRate.mul(timePassed);
        uint256 utilizationMultiplier = pool.utilizationRate.mul(1e4).div(MAX_UTILIZATION);
        uint256 rewards = baseRewards.mul(utilizationMultiplier).mul(providerShare).div(1e22);
        
        return rewards;
    }

    /**
     * @dev Calculate reward rate for provider
     * @param provider Provider address
     * @param poolId ID of the pool
     * @return rewardRate Calculated reward rate
     */
    function _calculateRewardRate(
        address provider,
        uint256 poolId
    ) internal view returns (uint256) {
        GPUResource storage resource = gpuResources[provider];
        StakingPool storage pool = stakingPools[poolId];
        
        // Base rate * reputation bonus * utilization bonus
        uint256 reputationBonus = resource.reputation.add(100); // 1x + reputation/100
        uint256 utilizationBonus = pool.utilizationRate.add(MAX_UTILIZATION).div(2); // Average with 100%
        
        return pool.rewardRate.mul(reputationBonus).mul(utilizationBonus).div(1e4);
    }

    /**
     * @dev Create new staking pool (internal)
     * @param name Pool name
     * @param rewardRate Base reward rate
     */
    function _createPool(
        string memory name,
        uint256 rewardRate
    ) internal {
        uint256 poolId = ++poolCounter;
        
        StakingPool storage pool = stakingPools[poolId];
        pool.rewardRate = rewardRate;
        pool.isActive = true;
        
        emit PoolCreated(poolId, name, rewardRate);
    }

    /**
     * @dev Count active providers in pool
     * @param poolId ID of the pool
     * @return count Number of active providers
     */
    function _countActiveProviders(uint256 poolId) internal view returns (uint256) {
        // This is simplified - in production, maintain a separate mapping
        return 0;
    }

    /**
     * @dev Emergency functions
     */
    function emergencyPause() external onlyOwner {
        // Pause all staking operations
        for (uint256 i = 1; i <= poolCounter; i++) {
            stakingPools[i].isActive = false;
        }
    }

    function emergencyUnpause() external onlyOwner {
        // Unpause all staking operations
        for (uint256 i = 1; i <= poolCounter; i++) {
            stakingPools[i].isActive = true;
        }
    }
}
