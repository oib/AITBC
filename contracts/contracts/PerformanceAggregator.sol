// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "../interfaces/IModularContracts.sol";
import "./ContractRegistry.sol";

/**
 * @title PerformanceAggregator
 * @dev Cross-contract performance data aggregation with reputation scoring
 * @notice Integrates with AgentStaking, AgentBounty, and PerformanceVerifier
 */
contract PerformanceAggregator is IPerformanceAggregator, Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    uint256 public version = 1;
    ContractRegistry public registry;
    address public performanceVerifier;
    address public agentBounty;
    address public agentStaking;
    
    // Performance metrics
    struct PerformanceMetrics {
        uint256 totalTasks;
        uint256 completedTasks;
        uint256 failedTasks;
        uint256 averageAccuracy;
        uint256 totalEarnings;
        uint256 lastUpdated;
        uint256 reputationScore;
        uint256 performanceTier; // 0-5 performance tiers
    }
    
    // Performance history
    struct PerformanceRecord {
        uint256 recordId;
        address agent;
        uint256 score;
        uint256 accuracy;
        uint256 earnings;
        uint256 timestamp;
        string taskType;
        bool isPositive;
    }
    
    // Performance tier thresholds
    struct PerformanceTier {
        uint256 minScore;
        uint256 maxScore;
        uint256 apyMultiplier; // In basis points (10000 = 1x)
        string name;
    }
    
    // Mappings
    mapping(address => PerformanceMetrics) public agentMetrics;
    mapping(uint256 => PerformanceRecord) public performanceRecords;
    mapping(address => uint256[]) public agentRecords;
    mapping(uint256 => address) public recordToAgent;
    mapping(uint256 => PerformanceTier) public performanceTiers;
    
    // Counters
    uint256 public recordCounter;
    uint256 public tierCounter;
    uint256[] public recordIds;
    
    // Constants
    uint256 public constant INITIAL_REPUTATION = 5000; // 50% initial reputation
    uint256 public constant MAX_REPUTATION = 10000; // 100% max reputation
    uint256 public constant MIN_REPUTATION = 0; // 0% min reputation
    uint256 public constant REPUTATION_DECAY_RATE = 100; // 1% decay per day
    uint256 public constant DECAY_INTERVAL = 1 days;
    uint256 public constant MAX_HISTORY_RECORDS = 1000; // Max records per agent
    
    // Events
    event PerformanceUpdated(address indexed agent, uint256 score, uint256 reputation);
    event ReputationCalculated(address indexed agent, uint256 reputation, uint256 tier);
    event PerformanceRecordAdded(uint256 indexed recordId, address indexed agent, uint256 score);
    event PerformanceTierUpdated(uint256 indexed tier, uint256 minScore, uint256 maxScore, uint256 multiplier);
    event AgentTierChanged(address indexed agent, uint256 oldTier, uint256 newTier);
    event BatchPerformanceUpdated(address[] agents, uint256[] scores);
    
    // Errors
    error InvalidScore(uint256 score);
    error InvalidAgent(address agent);
    error InvalidAccuracy(uint256 accuracy);
    error RecordNotFound(uint256 recordId);
    error MaxHistoryReached(address agent);
    error RegistryNotSet();
    error NotAuthorized();
    
    modifier validScore(uint256 score) {
        if (score > MAX_REPUTATION) revert InvalidScore(score);
        _;
    }
    
    modifier validAgent(address agent) {
        if (agent == address(0)) revert InvalidAgent(agent);
        _;
    }
    
    modifier validAccuracy(uint256 accuracy) {
        if (accuracy > 10000) revert InvalidAccuracy(accuracy); // Accuracy in basis points
        _;
    }
    
    modifier onlyAuthorized() {
        if (msg.sender != owner() && msg.sender != performanceVerifier && msg.sender != agentBounty && msg.sender != agentStaking) {
            revert NotAuthorized();
        }
        _;
    }
    
    modifier registrySet() {
        if (address(registry) == address(0)) revert RegistryNotSet();
        _;
    }
    
    constructor() {
        // Initialize default performance tiers
        _initializeDefaultTiers();
    }
    
    /**
     * @dev Initialize the performance aggregator (implements IModularContract)
     */
    function initialize(address _registry) external override {
        require(address(registry) == address(0), "Already initialized");
        registry = ContractRegistry(_registry);
        
        // Register this contract
        bytes32 contractId = keccak256(abi.encodePacked("PerformanceAggregator"));
        registry.registerContract(contractId, address(this));
        
        // Get integration addresses from registry
        performanceVerifier = registry.getContract(keccak256(abi.encodePacked("PerformanceVerifier")));
        agentBounty = registry.getContract(keccak256(abi.encodePacked("AgentBounty")));
        agentStaking = registry.getContract(keccak256(abi.encodePacked("AgentStaking")));
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
     * @dev Update agent performance
     */
    function updateAgentPerformance(address agent, uint256 score) 
        external 
        override 
        onlyAuthorized 
        whenNotPaused 
        validAgent(agent)
        validScore(score)
        nonReentrant 
    {
        _updatePerformance(agent, score, 0, 0, "general", true);
    }
    
    /**
     * @dev Update agent performance with detailed metrics
     */
    function updateAgentPerformanceDetailed(
        address agent,
        uint256 score,
        uint256 accuracy,
        uint256 earnings,
        string memory taskType,
        bool isPositive
    ) 
        external 
        onlyAuthorized 
        whenNotPaused 
        validAgent(agent)
        validScore(score)
        validAccuracy(accuracy)
        nonReentrant 
    {
        _updatePerformance(agent, score, accuracy, earnings, taskType, isPositive);
    }
    
    /**
     * @dev Batch update agent performance
     */
    function batchUpdatePerformance(address[] memory agents, uint256[] memory scores) 
        external 
        onlyAuthorized 
        whenNotPaused 
        nonReentrant 
    {
        require(agents.length == scores.length, "Array length mismatch");
        
        for (uint256 i = 0; i < agents.length; i++) {
            if (agents[i] != address(0) && scores[i] <= MAX_REPUTATION) {
                _updatePerformance(agents[i], scores[i], 0, 0, "batch", true);
            }
        }
        
        emit BatchPerformanceUpdated(agents, scores);
    }
    
    /**
     * @dev Internal performance update logic
     */
    function _updatePerformance(
        address agent,
        uint256 score,
        uint256 accuracy,
        uint256 earnings,
        string memory taskType,
        bool isPositive
    ) internal {
        PerformanceMetrics storage metrics = agentMetrics[agent];
        
        // Initialize if new agent
        if (metrics.lastUpdated == 0) {
            metrics.totalTasks = 0;
            metrics.completedTasks = 0;
            metrics.failedTasks = 0;
            metrics.averageAccuracy = 0;
            metrics.totalEarnings = 0;
            metrics.reputationScore = INITIAL_REPUTATION;
            metrics.performanceTier = 0;
        }
        
        // Update metrics
        metrics.totalTasks++;
        if (isPositive) {
            metrics.completedTasks++;
        } else {
            metrics.failedTasks++;
        }
        
        // Update average accuracy
        if (accuracy > 0) {
            metrics.averageAccuracy = (metrics.averageAccuracy * (metrics.totalTasks - 1) + accuracy) / metrics.totalTasks;
        }
        
        // Update earnings
        if (earnings > 0) {
            metrics.totalEarnings += earnings;
        }
        
        // Calculate new reputation score
        uint256 newReputation = _calculateReputation(metrics, score);
        uint256 oldTier = metrics.performanceTier;
        uint256 newTier = _getPerformanceTier(newReputation);
        
        // Update reputation and tier
        metrics.reputationScore = newReputation;
        metrics.performanceTier = newTier;
        metrics.lastUpdated = block.timestamp;
        
        // Add performance record
        uint256 recordId = ++recordCounter;
        performanceRecords[recordId] = PerformanceRecord({
            recordId: recordId,
            agent: agent,
            score: score,
            accuracy: accuracy,
            earnings: earnings,
            timestamp: block.timestamp,
            taskType: taskType,
            isPositive: isPositive
        });
        
        agentRecords[agent].push(recordId);
        recordToAgent[recordId] = agent;
        recordIds.push(recordId);
        
        // Limit history size
        if (agentRecords[agent].length > MAX_HISTORY_RECORDS) {
            uint256 oldRecordId = agentRecords[agent][0];
            delete performanceRecords[oldRecordId];
            delete recordToAgent[oldRecordId];
            
            // Shift array
            for (uint256 i = 0; i < agentRecords[agent].length - 1; i++) {
                agentRecords[agent][i] = agentRecords[agent][i + 1];
            }
            agentRecords[agent].pop();
        }
        
        emit PerformanceUpdated(agent, score, newReputation);
        emit ReputationCalculated(agent, newReputation, newTier);
        emit PerformanceRecordAdded(recordId, agent, score);
        
        if (oldTier != newTier) {
            emit AgentTierChanged(agent, oldTier, newTier);
        }
    }
    
    /**
     * @dev Calculate reputation score based on metrics
     */
    function _calculateReputation(PerformanceMetrics memory metrics, uint256 currentScore) internal view returns (uint256) {
        // Base score from current performance
        uint256 baseScore = currentScore;
        
        // Adjust based on task completion rate
        uint256 completionRate = metrics.totalTasks > 0 ? 
            (metrics.completedTasks * 10000) / metrics.totalTasks : 0;
        
        // Adjust based on average accuracy
        uint256 accuracyBonus = metrics.averageAccuracy > 0 ? 
            (metrics.averageAccuracy * 2000) / 10000 : 0; // Max 20% bonus
        
        // Adjust based on earnings (logarithmic scaling)
        uint256 earningsBonus = 0;
        if (metrics.totalEarnings > 0) {
            // Logarithmic scaling: every 10x increase in earnings adds 10% bonus
            earningsBonus = (1000 * log10(metrics.totalEarnings)) / 10000;
        }
        
        // Apply time decay
        uint256 timeSinceLastUpdate = block.timestamp - metrics.lastUpdated;
        uint256 decayAmount = (timeSinceLastUpdate * REPUTATION_DECAY_RATE) / DECAY_INTERVAL;
        
        // Calculate final reputation
        uint256 finalScore = baseScore + completionRate + accuracyBonus + earningsBonus - decayAmount;
        
        // Clamp to valid range
        if (finalScore > MAX_REPUTATION) {
            finalScore = MAX_REPUTATION;
        } else if (finalScore < MIN_REPUTATION) {
            finalScore = MIN_REPUTATION;
        }
        
        return finalScore;
    }
    
    /**
     * @dev Simple logarithm approximation for earnings bonus
     */
    function log10(uint256 value) internal pure returns (uint256) {
        if (value == 0) return 0;
        if (value < 10) return 0;
        if (value < 100) return 1;
        if (value < 1000) return 2;
        if (value < 10000) return 3;
        if (value < 100000) return 4;
        if (value < 1000000) return 5;
        if (value < 10000000) return 6;
        if (value < 100000000) return 7;
        if (value < 1000000000) return 8;
        if (value < 10000000000) return 9;
        return 10;
    }
    
    /**
     * @dev Get performance tier for reputation score
     */
    function _getPerformanceTier(uint256 reputation) internal view returns (uint256) {
        for (uint256 i = tierCounter; i > 0; i--) {
            PerformanceTier memory tier = performanceTiers[i];
            if (reputation >= tier.minScore && reputation <= tier.maxScore) {
                return i;
            }
        }
        return 0; // Default tier
    }
    
    /**
     * @dev Get reputation score for agent
     */
    function getReputationScore(address agent) external view override returns (uint256) {
        return agentMetrics[agent].reputationScore;
    }
    
    /**
     * @dev Calculate APY multiplier for reputation
     */
    function calculateAPYMultiplier(uint256 reputation) external view override returns (uint256) {
        uint256 tier = _getPerformanceTier(reputation);
        if (tier > 0) {
            return performanceTiers[tier].apyMultiplier;
        }
        return 10000; // 1x default multiplier
    }
    
    /**
     * @dev Get performance history for agent
     */
    function getPerformanceHistory(address agent) external view override returns (uint256[] memory) {
        return agentRecords[agent];
    }
    
    /**
     * @dev Get detailed performance metrics for agent
     */
    function getAgentMetrics(address agent) external view returns (
        uint256 totalTasks,
        uint256 completedTasks,
        uint256 failedTasks,
        uint256 averageAccuracy,
        uint256 totalEarnings,
        uint256 reputationScore,
        uint256 performanceTier,
        uint256 lastUpdated
    ) {
        PerformanceMetrics memory metrics = agentMetrics[agent];
        return (
            metrics.totalTasks,
            metrics.completedTasks,
            metrics.failedTasks,
            metrics.averageAccuracy,
            metrics.totalEarnings,
            metrics.reputationScore,
            metrics.performanceTier,
            metrics.lastUpdated
        );
    }
    
    /**
     * @dev Get performance record details
     */
    function getPerformanceRecord(uint256 recordId) external view returns (
        address agent,
        uint256 score,
        uint256 accuracy,
        uint256 earnings,
        uint256 timestamp,
        string memory taskType,
        bool isPositive
    ) {
        PerformanceRecord memory record = performanceRecords[recordId];
        return (
            record.agent,
            record.score,
            record.accuracy,
            record.earnings,
            record.timestamp,
            record.taskType,
            record.isPositive
        );
    }
    
    /**
     * @dev Get performance tier details
     */
    function getPerformanceTier(uint256 tierId) external view returns (
        uint256 minScore,
        uint256 maxScore,
        uint256 apyMultiplier,
        string memory name
    ) {
        PerformanceTier memory tier = performanceTiers[tierId];
        return (
            tier.minScore,
            tier.maxScore,
            tier.apyMultiplier,
            tier.name
        );
    }
    
    /**
     * @dev Get all performance tiers
     */
    function getAllPerformanceTiers() external view returns (uint256[] memory) {
        uint256[] memory tierIds = new uint256[](tierCounter);
        for (uint256 i = 1; i <= tierCounter; i++) {
            tierIds[i - 1] = i;
        }
        return tierIds;
    }
    
    /**
     * @dev Update performance tier
     */
    function updatePerformanceTier(
        uint256 tierId,
        uint256 minScore,
        uint256 maxScore,
        uint256 apyMultiplier,
        string memory name
    ) external onlyOwner {
        require(tierId > 0 && tierId <= tierCounter, "Invalid tier ID");
        
        performanceTiers[tierId] = PerformanceTier({
            minScore: minScore,
            maxScore: maxScore,
            apyMultiplier: apyMultiplier,
            name: name
        });
        
        emit PerformanceTierUpdated(tierId, minScore, maxScore, apyMultiplier);
    }
    
    /**
     * @dev Add new performance tier
     */
    function addPerformanceTier(
        uint256 minScore,
        uint256 maxScore,
        uint256 apyMultiplier,
        string memory name
    ) external onlyOwner {
        require(minScore <= maxScore, "Invalid score range");
        require(apyMultiplier <= 50000, "Multiplier too high"); // Max 5x
        
        tierCounter++;
        performanceTiers[tierCounter] = PerformanceTier({
            minScore: minScore,
            maxScore: maxScore,
            apyMultiplier: apyMultiplier,
            name: name
        });
        
        emit PerformanceTierUpdated(tierCounter, minScore, maxScore, apyMultiplier);
    }
    
    /**
     * @dev Initialize default performance tiers
     */
    function _initializeDefaultTiers() internal {
        tierCounter++;
        performanceTiers[tierCounter] = PerformanceTier({
            minScore: 0,
            maxScore: 2000,
            apyMultiplier: 8000, // 0.8x
            name: "Bronze"
        });
        
        tierCounter++;
        performanceTiers[tierCounter] = PerformanceTier({
            minScore: 2001,
            maxScore: 4000,
            apyMultiplier: 10000, // 1x
            name: "Silver"
        });
        
        tierCounter++;
        performanceTiers[tierCounter] = PerformanceTier({
            minScore: 4001,
            maxScore: 6000,
            apyMultiplier: 12000, // 1.2x
            name: "Gold"
        });
        
        tierCounter++;
        performanceTiers[tierCounter] = PerformanceTier({
            minScore: 6001,
            maxScore: 8000,
            apyMultiplier: 15000, // 1.5x
            name: "Platinum"
        });
        
        tierCounter++;
        performanceTiers[tierCounter] = PerformanceTier({
            minScore: 8001,
            maxScore: 10000,
            apyMultiplier: 20000, // 2x
            name: "Diamond"
        });
    }
    
    /**
     * @dev Get aggregator statistics
     */
    function getAggregatorStats() external view returns (
        uint256 totalAgents,
        uint256 totalRecords,
        uint256 averageReputation,
        uint256 activeAgents
    ) {
        uint256 _totalAgents = 0;
        uint256 _totalReputation = 0;
        uint256 _activeAgents = 0;
        
        // This would require iterating through all agents, which is gas-intensive
        // For production, consider using a different approach or off-chain calculation
        
        return (
            _totalAgents,
            recordCounter,
            _totalReputation,
            _activeAgents
        );
    }
}
