// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title IModularContract
 * @dev Standard interface for all modular puzzle pieces
 * @notice Provides common functionality for initialization, upgrades, and pausing
 */
interface IModularContract {
    function initialize(address registry) external;
    function upgrade(address newImplementation) external;
    function pause() external;
    function unpause() external;
    function getVersion() external view returns (uint256);
}

/**
 * @title ITreasuryManager
 * @dev Interface for automated treasury management
 * @notice Handles budget categories, fund allocation, and vesting
 */
interface ITreasuryManager is IModularContract {
    function createBudgetCategory(string memory category, uint256 budget) external;
    function allocateFunds(string memory category, address recipient, uint256 amount) external;
    function releaseVestedFunds(uint256 allocationId) external;
    function getBudgetBalance(string memory category) external view returns (uint256);
    function getAllocation(uint256 allocationId) external view returns (address, uint256, uint256);
}

/**
 * @title IRewardDistributor
 * @dev Interface for multi-token reward distribution
 * @notice Handles reward pools, distribution, and claiming
 */
interface IRewardDistributor is IModularContract {
    function createRewardPool(address token, uint256 totalRewards) external returns (uint256);
    function distributeRewards(uint256 poolId, address[] memory recipients, uint256[] memory amounts) external;
    function claimReward(uint256 claimId) external;
    function getPoolBalance(uint256 poolId) external view returns (uint256);
    function getUserRewards(address user) external view returns (uint256);
}

/**
 * @title IStakingPoolFactory
 * @dev Interface for dynamic staking pool creation
 * @notice Handles pool creation, APY management, and performance tracking
 */
interface IStakingPoolFactory is IModularContract {
    function createPool(string memory poolName, uint256 baseAPY, uint256 lockPeriod) external returns (uint256);
    function updatePoolAPY(uint256 poolId, uint256 newAPY) external;
    function getPoolPerformance(uint256 poolId) external view returns (uint256);
    function stakeInPool(uint256 poolId, uint256 amount) external;
    function unstakeFromPool(uint256 poolId, uint256 amount) external;
}

/**
 * @title ICrossChainGovernance
 * @dev Interface for cross-chain proposal coordination
 * @notice Handles cross-chain proposals and vote validation
 */
interface ICrossChainGovernance is IModularContract {
    function submitCrossChainProposal(uint256 sourceChainId, bytes32 proposalHash) external;
    function validateCrossChainVote(uint256 proposalId, bytes32 voteProof) external;
    function executeCrossChainProposal(uint256 proposalId) external;
    function getCrossChainProposal(uint256 proposalId) external view returns (bytes32, uint256, bool);
}

/**
 * @title IPerformanceAggregator
 * @dev Interface for performance data aggregation
 * @notice Handles performance updates and reputation scoring
 */
interface IPerformanceAggregator is IModularContract {
    function updateAgentPerformance(address agent, uint256 score) external;
    function getReputationScore(address agent) external view returns (uint256);
    function calculateAPYMultiplier(uint256 reputation) external view returns (uint256);
    function getPerformanceHistory(address agent) external view returns (uint256[] memory);
}

/**
 * @title IContractRegistry
 * @dev Interface for contract registry
 * @notice Handles contract registration and lookup
 */
interface IContractRegistry is IModularContract {
    function registerContract(bytes32 contractId, address contractAddress) external;
    function getContract(bytes32 contractId) external view returns (address);
    function updateContract(bytes32 contractId, address newAddress) external;
    function listContracts() external view returns (bytes32[] memory, address[] memory);
}

/**
 * @title ISecurityManager
 * @dev Interface for centralized security management
 * @notice Handles pausing, emergency controls, and multi-signature operations
 */
interface ISecurityManager is IModularContract {
    function pauseContract(address contractAddress) external;
    function unpauseContract(address contractAddress) external;
    function emergencyWithdraw(address token, uint256 amount) external;
    function isPaused(address contractAddress) external view returns (bool);
    function getEmergencyStatus() external view returns (bool);
}

/**
 * @title IGasOptimizer
 * @dev Interface for gas optimization utilities
 * @notice Handles batch operations and gas estimation
 */
interface IGasOptimizer is IModularContract {
    function batchOperations(address[] memory targets, bytes[] memory calldatas) external;
    function estimateGasSavings(address contractAddress) external view returns (uint256);
    function optimizeCall(address target, bytes calldata data) external;
    function getOptimizationTips() external view returns (string[] memory);
}
