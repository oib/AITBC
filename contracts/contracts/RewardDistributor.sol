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
 * @title RewardDistributor
 * @dev Multi-token reward distribution engine with automated claiming
 * @notice Integrates with AgentStaking, TreasuryManager, and PerformanceAggregator
 */
contract RewardDistributor is IRewardDistributor, Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    
    // State variables
    uint256 public version = 1;
    ContractRegistry public registry;
    address public performanceAggregator;
    address public stakingPoolFactory;
    
    // Reward pool
    struct RewardPool {
        uint256 poolId;
        address token;
        uint256 totalRewards;
        uint256 distributedRewards;
        uint256 claimedRewards;
        bool isActive;
        uint256 createdAt;
        address creator;
        string description;
    }
    
    // Reward claim
    struct RewardClaim {
        uint256 claimId;
        uint256 poolId;
        address recipient;
        uint256 amount;
        uint256 claimedAt;
        bool isClaimed;
        bytes32 merkleProof; // For batch claims
    }
    
    // Performance-based reward
    struct PerformanceReward {
        uint256 rewardId;
        address agent;
        uint256 baseAmount;
        uint256 performanceMultiplier; // In basis points (10000 = 1x)
        uint256 finalAmount;
        bool isDistributed;
        uint256 distributedAt;
    }
    
    // Mappings
    mapping(uint256 => RewardPool) public rewardPools;
    mapping(uint256 => RewardClaim) public rewardClaims;
    mapping(uint256 => PerformanceReward) public performanceRewards;
    mapping(address => uint256[]) public userClaims;
    mapping(address => uint256) public userTotalRewards;
    mapping(address => mapping(address => uint256)) public userTokenRewards; // user => token => amount
    mapping(uint256 => uint256[]) public poolClaims;
    mapping(address => uint256[]) public agentPerformanceRewards;
    
    // Counters
    uint256 public poolCounter;
    uint256 public claimCounter;
    uint256 public performanceRewardCounter;
    uint256[] public activePoolIds;
    
    // Constants
    uint256 public constant MIN_REWARD_AMOUNT = 1 * 10**18; // 1 token minimum
    uint256 public constant MAX_PERFORMANCE_MULTIPLIER = 50000; // 5x max multiplier
    uint256 public constant DEFAULT_PERFORMANCE_MULTIPLIER = 10000; // 1x default
    uint256 public constant CLAIM_FEE_PERCENTAGE = 10; // 0.1% claim fee
    uint256 public constant BASIS_POINTS = 10000;
    
    // Events
    event RewardPoolCreated(uint256 indexed poolId, address indexed token, uint256 totalRewards, string description);
    event RewardsDistributed(uint256 indexed poolId, uint256 recipientCount, uint256 totalAmount);
    event RewardClaimed(uint256 indexed claimId, address indexed recipient, uint256 amount);
    event PerformanceRewardCreated(uint256 indexed rewardId, address indexed agent, uint256 baseAmount);
    event PerformanceRewardDistributed(uint256 indexed rewardId, address indexed agent, uint256 finalAmount);
    event PoolDeactivated(uint256 indexed poolId);
    event TokensDeposited(address indexed token, address indexed depositor, uint256 amount);
    
    // Errors
    error InvalidAmount(uint256 amount);
    error PoolNotFound(uint256 poolId);
    error PoolNotActive(uint256 poolId);
    error InsufficientPoolBalance(uint256 poolId, uint256 requested, uint256 available);
    error ClaimNotFound(uint256 claimId);
    error ClaimAlreadyUsed(uint256 claimId);
    error InvalidRecipient(address recipient);
    error InvalidToken(address token);
    error PerformanceMultiplierTooHigh(uint256 multiplier);
    error RegistryNotSet();
    error NotAuthorized();
    
    modifier validAmount(uint256 amount) {
        if (amount < MIN_REWARD_AMOUNT) revert InvalidAmount(amount);
        _;
    }
    
    modifier validPool(uint256 poolId) {
        if (rewardPools[poolId].poolId == 0) revert PoolNotFound(poolId);
        if (!rewardPools[poolId].isActive) revert PoolNotActive(poolId);
        _;
    }
    
    modifier validRecipient(address recipient) {
        if (recipient == address(0)) revert InvalidRecipient(recipient);
        _;
    }
    
    modifier onlyAuthorized() {
        if (msg.sender != owner() && msg.sender != stakingPoolFactory && msg.sender != performanceAggregator) {
            revert NotAuthorized();
        }
        _;
    }
    
    modifier registrySet() {
        if (address(registry) == address(0)) revert RegistryNotSet();
        _;
    }
    
    constructor() {}
    
    /**
     * @dev Initialize the reward distributor (implements IModularContract)
     */
    function initialize(address _registry) external override {
        require(address(registry) == address(0), "Already initialized");
        registry = ContractRegistry(_registry);
        
        // Register this contract if not already registered
        bytes32 contractId = keccak256(abi.encodePacked("RewardDistributor"));
        try registry.getContract(contractId) returns (address) {
            // Already registered, skip
        } catch {
            // Not registered, register now
            registry.registerContract(contractId, address(this));
        }
        
        // Get integration addresses from registry
        try registry.getContract(keccak256(abi.encodePacked("PerformanceAggregator"))) returns (address perfAddress) {
            performanceAggregator = perfAddress;
        } catch {
            // PerformanceAggregator not found, keep as zero address
        }
        
        try registry.getContract(keccak256(abi.encodePacked("StakingPoolFactory"))) returns (address stakingAddress) {
            stakingPoolFactory = stakingAddress;
        } catch {
            // StakingPoolFactory not found, keep as zero address
        }
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
     * @dev Create a reward pool
     */
    function createRewardPool(address token, uint256 totalRewards) 
        external 
        override 
        onlyAuthorized 
        whenNotPaused 
        validAmount(totalRewards)
        nonReentrant 
        returns (uint256) 
    {
        if (token == address(0)) revert InvalidToken(token);
        
        uint256 poolId = ++poolCounter;
        rewardPools[poolId] = RewardPool({
            poolId: poolId,
            token: token,
            totalRewards: totalRewards,
            distributedRewards: 0,
            claimedRewards: 0,
            isActive: true,
            createdAt: block.timestamp,
            creator: msg.sender,
            description: ""
        });
        
        activePoolIds.push(poolId);
        
        emit RewardPoolCreated(poolId, token, totalRewards, "");
    }
    
    /**
     * @dev Create a reward pool with description
     */
    function createRewardPoolWithDescription(
        address token, 
        uint256 totalRewards, 
        string memory description
    ) 
        external 
        onlyAuthorized 
        whenNotPaused 
        validAmount(totalRewards)
        nonReentrant 
    {
        if (token == address(0)) revert InvalidToken(token);
        
        uint256 poolId = ++poolCounter;
        rewardPools[poolId] = RewardPool({
            poolId: poolId,
            token: token,
            totalRewards: totalRewards,
            distributedRewards: 0,
            claimedRewards: 0,
            isActive: true,
            createdAt: block.timestamp,
            creator: msg.sender,
            description: description
        });
        
        activePoolIds.push(poolId);
        
        emit RewardPoolCreated(poolId, token, totalRewards, description);
    }
    
    /**
     * @dev Distribute rewards to multiple recipients
     */
    function distributeRewards(uint256 poolId, address[] memory recipients, uint256[] memory amounts) 
        external 
        override 
        onlyAuthorized 
        whenNotPaused 
        validPool(poolId)
        nonReentrant 
    {
        require(recipients.length == amounts.length, "Array length mismatch");
        
        RewardPool storage pool = rewardPools[poolId];
        uint256 totalAmount = 0;
        
        // Calculate total amount and check pool balance
        for (uint256 i = 0; i < amounts.length; i++) {
            require(recipients[i] != address(0), "Invalid recipient");
            totalAmount += amounts[i];
        }
        
        uint256 availableBalance = pool.totalRewards - pool.distributedRewards;
        if (totalAmount > availableBalance) {
            revert InsufficientPoolBalance(poolId, totalAmount, availableBalance);
        }
        
        // Create claims and update user balances
        for (uint256 i = 0; i < recipients.length; i++) {
            if (amounts[i] > 0) {
                uint256 claimId = ++claimCounter;
                
                rewardClaims[claimId] = RewardClaim({
                    claimId: claimId,
                    poolId: poolId,
                    recipient: recipients[i],
                    amount: amounts[i],
                    claimedAt: 0,
                    isClaimed: false,
                    merkleProof: bytes32(0)
                });
                
                userClaims[recipients[i]].push(claimId);
                userTotalRewards[recipients[i]] += amounts[i];
                userTokenRewards[recipients[i]][pool.token] += amounts[i];
                poolClaims[poolId].push(claimId);
            }
        }
        
        // Update pool
        pool.distributedRewards += totalAmount;
        
        emit RewardsDistributed(poolId, recipients.length, totalAmount);
    }
    
    /**
     * @dev Claim a reward
     */
    function claimReward(uint256 claimId) 
        external 
        override 
        whenNotPaused 
        nonReentrant 
    {
        RewardClaim storage claim = rewardClaims[claimId];
        
        if (claim.claimId == 0) revert ClaimNotFound(claimId);
        if (claim.isClaimed) revert ClaimAlreadyUsed(claimId);
        if (msg.sender != claim.recipient) revert InvalidRecipient(msg.sender);
        
        // Mark as claimed
        claim.isClaimed = true;
        claim.claimedAt = block.timestamp;
        
        // Update pool
        RewardPool storage pool = rewardPools[claim.poolId];
        pool.claimedRewards += claim.amount;
        
        // Calculate claim fee
        uint256 fee = (claim.amount * CLAIM_FEE_PERCENTAGE) / BASIS_POINTS;
        uint256 netAmount = claim.amount - fee;
        
        // Transfer tokens
        IERC20(pool.token).safeTransfer(claim.recipient, netAmount);
        
        // Transfer fee to owner
        if (fee > 0) {
            IERC20(pool.token).safeTransfer(owner(), fee);
        }
        
        emit RewardClaimed(claimId, claim.recipient, netAmount);
    }
    
    /**
     * @dev Create performance-based reward
     */
    function createPerformanceReward(address agent, uint256 baseAmount) 
        external 
        onlyAuthorized 
        whenNotPaused 
        validAmount(baseAmount)
        nonReentrant 
    {
        if (agent == address(0)) revert InvalidRecipient(agent);
        
        uint256 rewardId = ++performanceRewardCounter;
        
        // Get performance multiplier from PerformanceAggregator
        uint256 performanceMultiplier = DEFAULT_PERFORMANCE_MULTIPLIER;
        if (performanceAggregator != address(0)) {
            try IPerformanceAggregator(performanceAggregator).getReputationScore(agent) returns (uint256 reputation) {
                performanceMultiplier = IPerformanceAggregator(performanceAggregator).calculateAPYMultiplier(reputation);
                if (performanceMultiplier > MAX_PERFORMANCE_MULTIPLIER) {
                    performanceMultiplier = MAX_PERFORMANCE_MULTIPLIER;
                }
            } catch {
                // Use default multiplier if call fails
                performanceMultiplier = DEFAULT_PERFORMANCE_MULTIPLIER;
            }
        }
        
        uint256 finalAmount = (baseAmount * performanceMultiplier) / BASIS_POINTS;
        
        performanceRewards[rewardId] = PerformanceReward({
            rewardId: rewardId,
            agent: agent,
            baseAmount: baseAmount,
            performanceMultiplier: performanceMultiplier,
            finalAmount: finalAmount,
            isDistributed: false,
            distributedAt: 0
        });
        
        agentPerformanceRewards[agent].push(rewardId);
        
        emit PerformanceRewardCreated(rewardId, agent, baseAmount);
    }
    
    /**
     * @dev Distribute performance reward
     */
    function distributePerformanceReward(uint256 rewardId) 
        external 
        onlyAuthorized 
        whenNotPaused 
        nonReentrant 
    {
        PerformanceReward storage reward = performanceRewards[rewardId];
        
        if (reward.rewardId == 0) revert ClaimNotFound(rewardId);
        if (reward.isDistributed) revert ClaimAlreadyUsed(rewardId);
        
        // Mark as distributed
        reward.isDistributed = true;
        reward.distributedAt = block.timestamp;
        
        // Update user rewards
        userTotalRewards[reward.agent] += reward.finalAmount;
        
        emit PerformanceRewardDistributed(rewardId, reward.agent, reward.finalAmount);
    }
    
    /**
     * @dev Get pool balance
     */
    function getPoolBalance(uint256 poolId) external view override returns (uint256) {
        RewardPool memory pool = rewardPools[poolId];
        return pool.totalRewards - pool.distributedRewards;
    }
    
    /**
     * @dev Get user rewards
     */
    function getUserRewards(address user) external view override returns (uint256) {
        return userTotalRewards[user];
    }
    
    /**
     * @dev Get user rewards for specific token
     */
    function getUserTokenRewards(address user, address token) external view returns (uint256) {
        return userTokenRewards[user][token];
    }
    
    /**
     * @dev Get user claim IDs
     */
    function getUserClaims(address user) external view returns (uint256[] memory) {
        return userClaims[user];
    }
    
    /**
     * @dev Get pool claim IDs
     */
    function getPoolClaims(uint256 poolId) external view returns (uint256[] memory) {
        return poolClaims[poolId];
    }
    
    /**
     * @dev Get agent performance reward IDs
     */
    function getAgentPerformanceRewards(address agent) external view returns (uint256[] memory) {
        return agentPerformanceRewards[agent];
    }
    
    /**
     * @dev Get active pool IDs
     */
    function getActivePoolIds() external view returns (uint256[] memory) {
        return activePoolIds;
    }
    
    /**
     * @dev Get pool details
     */
    function getPoolDetails(uint256 poolId) external view returns (
        address token,
        uint256 totalRewards,
        uint256 distributedRewards,
        uint256 claimedRewards,
        bool isActive,
        string memory description
    ) {
        RewardPool memory pool = rewardPools[poolId];
        return (
            pool.token,
            pool.totalRewards,
            pool.distributedRewards,
            pool.claimedRewards,
            pool.isActive,
            pool.description
        );
    }
    
    /**
     * @dev Get claim details
     */
    function getClaimDetails(uint256 claimId) external view returns (
        uint256 poolId,
        address recipient,
        uint256 amount,
        bool isClaimed,
        uint256 claimedAt
    ) {
        RewardClaim memory claim = rewardClaims[claimId];
        return (
            claim.poolId,
            claim.recipient,
            claim.amount,
            claim.isClaimed,
            claim.claimedAt
        );
    }
    
    /**
     * @dev Deactivate a reward pool
     */
    function deactivatePool(uint256 poolId) external onlyAuthorized validPool(poolId) {
        rewardPools[poolId].isActive = false;
        
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
     * @dev Deposit tokens for rewards
     */
    function depositTokens(address token, uint256 amount) external whenNotPaused validAmount(amount) {
        if (token == address(0)) revert InvalidToken(token);
        
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        
        emit TokensDeposited(token, msg.sender, amount);
    }
    
    /**
     * @dev Emergency withdraw tokens
     */
    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) revert InvalidToken(token);
        
        IERC20(token).safeTransfer(msg.sender, amount);
    }
    
    /**
     * @dev Get reward distributor statistics
     */
    function getRewardStats() external view returns (
        uint256 totalPools,
        uint256 activePools,
        uint256 totalClaims,
        uint256 totalDistributed,
        uint256 totalClaimed
    ) {
        uint256 _activePools = 0;
        uint256 _totalDistributed = 0;
        uint256 _totalClaimed = 0;
        
        for (uint256 i = 0; i < activePoolIds.length; i++) {
            RewardPool memory pool = rewardPools[activePoolIds[i]];
            if (pool.isActive) {
                _activePools++;
                _totalDistributed += pool.distributedRewards;
                _totalClaimed += pool.claimedRewards;
            }
        }
        
        return (
            poolCounter,
            _activePools,
            claimCounter,
            _totalDistributed,
            _totalClaimed
        );
    }
}
