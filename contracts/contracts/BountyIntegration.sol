// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "./AgentBounty.sol";
import "./AgentStaking.sol";
import "./PerformanceVerifier.sol";
import "./AIToken.sol";

/**
 * @title Bounty Integration Layer
 * @dev Bridges PerformanceVerifier with bounty and staking contracts
 * @notice Handles automatic bounty completion detection and cross-contract event handling
 */
contract BountyIntegration is Ownable, ReentrancyGuard {
    
    // State variables
    AgentBounty public agentBounty;
    AgentStaking public agentStaking;
    PerformanceVerifier public performanceVerifier;
    AIToken public aitbcToken;
    
    uint256 public integrationCounter;
    uint256 public autoVerificationThreshold = 90; // 90% accuracy for auto-verification
    uint256 public batchProcessingLimit = 50;
    uint256 public gasOptimizationThreshold = 100000;
    
    // Integration status
    enum IntegrationStatus { PENDING, PROCESSING, COMPLETED, FAILED }
    
    // Performance to bounty mapping
    struct PerformanceMapping {
        uint256 mappingId;
        bytes32 performanceHash;
        uint256 bountyId;
        uint256 submissionId;
        IntegrationStatus status;
        uint256 createdAt;
        uint256 processedAt;
        string errorMessage;
    }
    
    // Batch processing
    struct BatchRequest {
        uint256 batchId;
        uint256[] bountyIds;
        uint256[] submissionIds;
        bytes32[] performanceHashes;
        uint256[] accuracies;
        uint256[] responseTimes;
        IntegrationStatus status;
        uint256 createdAt;
        uint256 processedAt;
        uint256 successCount;
        uint256 failureCount;
    }
    
    // Event handlers
    struct EventHandler {
        bytes32 eventType;
        address targetContract;
        bytes4 functionSelector;
        bool isActive;
        uint256 priority;
    }
    
    // Mappings
    mapping(uint256 => PerformanceMapping) public performanceMappings;
    mapping(bytes32 => uint256) public performanceHashToMapping;
    mapping(uint256 => BatchRequest) public batchRequests;
    mapping(bytes32 => EventHandler) public eventHandlers;
    mapping(address => bool) public authorizedIntegrators;
    
    // Arrays
    uint256[] public pendingMappings;
    bytes32[] public performanceHashes;
    address[] public authorizedIntegratorList;
    
    // Events
    event PerformanceMapped(
        uint256 indexed mappingId,
        bytes32 indexed performanceHash,
        uint256 indexed bountyId,
        uint256 submissionId
    );
    
    event BountyAutoCompleted(
        uint256 indexed bountyId,
        uint256 indexed submissionId,
        address indexed submitter,
        uint256 rewardAmount
    );
    
    event StakingRewardsTriggered(
        address indexed agentWallet,
        uint256 totalEarnings,
        uint256 stakerCount
    );
    
    event BatchProcessed(
        uint256 indexed batchId,
        uint256 successCount,
        uint256 failureCount,
        uint256 gasUsed
    );
    
    event IntegrationFailed(
        uint256 indexed mappingId,
        string errorMessage,
        bytes32 indexed performanceHash
    );
    
    event EventHandlerRegistered(
        bytes32 indexed eventType,
        address indexed targetContract,
        bytes4 functionSelector
    );
    
    // Modifiers
    modifier mappingExists(uint256 _mappingId) {
        require(_mappingId < integrationCounter, "Mapping does not exist");
        _;
    }
    
    modifier onlyAuthorizedIntegrator() {
        require(authorizedIntegrators[msg.sender], "Not authorized integrator");
        _;
    }
    
    modifier validPerformanceHash(bytes32 _performanceHash) {
        require(_performanceHash != bytes32(0), "Invalid performance hash");
        _;
    }
    
    constructor(
        address _agentBounty,
        address _agentStaking,
        address _performanceVerifier,
        address _aitbcToken
    ) {
        agentBounty = AgentBounty(_agentBounty);
        agentStaking = AgentStaking(_agentStaking);
        performanceVerifier = PerformanceVerifier(_performanceVerifier);
        aitbcToken = AIToken(_aitbcToken);
        
        // Register default event handlers
        _registerEventHandler(
            keccak256("BOUNTY_COMPLETED"),
            _agentStaking,
            AgentStaking.distributeAgentEarnings.selector
        );
        
        _registerEventHandler(
            keccak256("PERFORMANCE_VERIFIED"),
            _agentBounty,
            AgentBounty.verifySubmission.selector
        );
    }
    
    /**
     * @dev Maps performance verification to bounty completion
     * @param _performanceHash Hash of performance metrics
     * @param _bountyId Bounty ID
     * @param _submissionId Submission ID
     */
    function mapPerformanceToBounty(
        bytes32 _performanceHash,
        uint256 _bountyId,
        uint256 _submissionId
    ) external 
        onlyAuthorizedIntegrator
        validPerformanceHash(_performanceHash)
        nonReentrant 
        returns (uint256) 
    {
        require(performanceHashToMapping[_performanceHash] == 0, "Performance already mapped");
        
        uint256 mappingId = integrationCounter++;
        
        PerformanceMapping storage perfMap = performanceMappings[mappingId];
        perfMap.mappingId = mappingId;
        perfMap.performanceHash = _performanceHash;
        perfMap.bountyId = _bountyId;
        perfMap.submissionId = _submissionId;
        perfMap.status = IntegrationStatus.PENDING;
        perfMap.createdAt = block.timestamp;
        
        performanceHashToMapping[_performanceHash] = mappingId;
        pendingMappings.push(mappingId);
        performanceHashes.push(_performanceHash);
        
        emit PerformanceMapped(mappingId, _performanceHash, _bountyId, _submissionId);
        
        // Attempt auto-processing
        _processMapping(mappingId);
        
        return mappingId;
    }
    
    /**
     * @dev Processes a single performance mapping
     * @param _mappingId Mapping ID
     */
    function processMapping(uint256 _mappingId) external 
        onlyAuthorizedIntegrator
        mappingExists(_mappingId)
        nonReentrant 
    {
        _processMapping(_mappingId);
    }
    
    /**
     * @dev Processes multiple mappings in a batch
     * @param _mappingIds Array of mapping IDs
     */
    function processBatchMappings(uint256[] calldata _mappingIds) external 
        onlyAuthorizedIntegrator
        nonReentrant 
    {
        require(_mappingIds.length <= batchProcessingLimit, "Batch too large");
        
        uint256 batchId = integrationCounter++;
        BatchRequest storage batch = batchRequests[batchId];
        batch.batchId = batchId;
        batch.bountyIds = new uint256[](_mappingIds.length);
        batch.submissionIds = new uint256[](_mappingIds.length);
        batch.performanceHashes = new bytes32[](_mappingIds.length);
        batch.accuracies = new uint256[](_mappingIds.length);
        batch.responseTimes = new uint256[](_mappingIds.length);
        batch.status = IntegrationStatus.PROCESSING;
        batch.createdAt = block.timestamp;
        
        uint256 gasStart = gasleft();
        uint256 successCount = 0;
        uint256 failureCount = 0;
        
        for (uint256 i = 0; i < _mappingIds.length; i++) {
            try this._processMappingInternal(_mappingIds[i]) {
                successCount++;
            } catch {
                failureCount++;
            }
        }
        
        batch.successCount = successCount;
        batch.failureCount = failureCount;
        batch.processedAt = block.timestamp;
        batch.status = IntegrationStatus.COMPLETED;
        
        uint256 gasUsed = gasStart - gasleft();
        
        emit BatchProcessed(batchId, successCount, failureCount, gasUsed);
    }
    
    /**
     * @dev Auto-verifies bounty submissions based on performance metrics
     * @param _bountyId Bounty ID
     * @param _submissionId Submission ID
     * @param _accuracy Achieved accuracy
     * @param _responseTime Response time
     */
    function autoVerifyBountySubmission(
        uint256 _bountyId,
        uint256 _submissionId,
        uint256 _accuracy,
        uint256 _responseTime
    ) external 
        onlyAuthorizedIntegrator
        nonReentrant 
    {
        // Get bounty details
        (,,,,,, bytes32 performanceCriteria, uint256 minAccuracy,,,,,) = agentBounty.getBounty(_bountyId);
        
        // Check if auto-verification conditions are met
        if (_accuracy >= autoVerificationThreshold && _accuracy >= minAccuracy) {
            // Verify the submission
            agentBounty.verifySubmission(_bountyId, _submissionId, true, address(this));
            
            // Get submission details to calculate rewards
            (uint256 bountyId, address submitter, bytes32 performanceHash, uint256 accuracy, uint256 responseTime,,,) = agentBounty.getSubmission(_submissionId);
            
            // Trigger staking rewards if applicable
            _triggerStakingRewards(submitter, _accuracy);
            
            emit BountyAutoCompleted(_bountyId, _submissionId, submitter, 0); // Reward amount will be set by bounty contract
        }
    }
    
    /**
     * @dev Handles performance verification events
     * @param _verificationId Performance verification ID
     * @param _accuracy Accuracy achieved
     * @param _responseTime Response time
     * @param _performanceHash Hash of performance metrics
     */
    function handlePerformanceVerified(
        uint256 _verificationId,
        uint256 _accuracy,
        uint256 _responseTime,
        bytes32 _performanceHash
    ) external 
        onlyAuthorizedIntegrator
        nonReentrant 
    {
        // Check if this performance is mapped to any bounties
        uint256 mappingId = performanceHashToMapping[_performanceHash];
        if (mappingId > 0) {
            PerformanceMapping storage perfMap = performanceMappings[mappingId];
            
            // Update agent staking metrics
            (uint256 bountyId, address submitter, bytes32 performanceHash, uint256 accuracy, uint256 responseTime,,,) = agentBounty.getSubmission(perfMap.submissionId);
            agentStaking.updateAgentPerformance(submitter, _accuracy, _accuracy >= autoVerificationThreshold);
            
            // Auto-verify bounty if conditions are met
            _autoVerifyBounty(perfMap.bountyId, perfMap.submissionId, _accuracy, _responseTime);
        }
    }
    
    /**
     * @dev Registers an event handler for cross-contract communication
     * @param _eventType Event type identifier
     * @param _targetContract Target contract address
     * @param _functionSelector Function selector to call
     */
    function registerEventHandler(
        bytes32 _eventType,
        address _targetContract,
        bytes4 _functionSelector
    ) external onlyOwner {
        require(_targetContract != address(0), "Invalid target contract");
        require(_functionSelector != bytes4(0), "Invalid function selector");
        
        eventHandlers[_eventType] = EventHandler({
            eventType: _eventType,
            targetContract: _targetContract,
            functionSelector: _functionSelector,
            isActive: true,
            priority: 0
        });
        
        emit EventHandlerRegistered(_eventType, _targetContract, _functionSelector);
    }
    
    /**
     * @dev Authorizes an integrator address
     * @param _integrator Address to authorize
     */
    function authorizeIntegrator(address _integrator) external onlyOwner {
        require(_integrator != address(0), "Invalid integrator address");
        require(!authorizedIntegrators[_integrator], "Already authorized");
        
        authorizedIntegrators[_integrator] = true;
        authorizedIntegratorList.push(_integrator);
    }
    
    /**
     * @dev Revokes integrator authorization
     * @param _integrator Address to revoke
     */
    function revokeIntegrator(address _integrator) external onlyOwner {
        require(authorizedIntegrators[_integrator], "Not authorized");
        
        authorizedIntegrators[_integrator] = false;
        
        // Remove from list
        for (uint256 i = 0; i < authorizedIntegratorList.length; i++) {
            if (authorizedIntegratorList[i] == _integrator) {
                authorizedIntegratorList[i] = authorizedIntegratorList[authorizedIntegratorList.length - 1];
                authorizedIntegratorList.pop();
                break;
            }
        }
    }
    
    /**
     * @dev Updates configuration parameters
     * @param _autoVerificationThreshold New auto-verification threshold
     * @param _batchProcessingLimit New batch processing limit
     * @param _gasOptimizationThreshold New gas optimization threshold
     */
    function updateConfiguration(
        uint256 _autoVerificationThreshold,
        uint256 _batchProcessingLimit,
        uint256 _gasOptimizationThreshold
    ) external onlyOwner {
        require(_autoVerificationThreshold <= 100, "Invalid threshold");
        require(_batchProcessingLimit <= 100, "Batch limit too high");
        
        autoVerificationThreshold = _autoVerificationThreshold;
        batchProcessingLimit = _batchProcessingLimit;
        gasOptimizationThreshold = _gasOptimizationThreshold;
    }
    
    // View functions
    
    /**
     * @dev Gets performance mapping details
     * @param _mappingId Mapping ID
     */
    function getPerformanceMapping(uint256 _mappingId) external view mappingExists(_mappingId) returns (
        bytes32 performanceHash,
        uint256 bountyId,
        uint256 submissionId,
        IntegrationStatus status,
        uint256 createdAt,
        uint256 processedAt,
        string memory errorMessage
    ) {
        PerformanceMapping storage perfMap = performanceMappings[_mappingId];
        return (
            perfMap.performanceHash,
            perfMap.bountyId,
            perfMap.submissionId,
            perfMap.status,
            perfMap.createdAt,
            perfMap.processedAt,
            perfMap.errorMessage
        );
    }
    
    /**
     * @dev Gets batch request details
     * @param _batchId Batch ID
     */
    function getBatchRequest(uint256 _batchId) external view returns (
        uint256[] memory bountyIds,
        uint256[] memory submissionIds,
        IntegrationStatus status,
        uint256 createdAt,
        uint256 processedAt,
        uint256 successCount,
        uint256 failureCount
    ) {
        BatchRequest storage batch = batchRequests[_batchId];
        return (
            batch.bountyIds,
            batch.submissionIds,
            batch.status,
            batch.createdAt,
            batch.processedAt,
            batch.successCount,
            batch.failureCount
        );
    }
    
    /**
     * @dev Gets pending mappings
     */
    function getPendingMappings() external view returns (uint256[] memory) {
        return pendingMappings;
    }
    
    /**
     * @dev Gets all performance hashes
     */
    function getPerformanceHashes() external view returns (bytes32[] memory) {
        return performanceHashes;
    }
    
    /**
     * @dev Gets authorized integrators
     */
    function getAuthorizedIntegrators() external view returns (address[] memory) {
        return authorizedIntegratorList;
    }
    
    /**
     * @dev Checks if an address is authorized
     * @param _integrator Address to check
     */
    function isAuthorizedIntegrator(address _integrator) external view returns (bool) {
        return authorizedIntegrators[_integrator];
    }
    
    /**
     * @dev Gets integration statistics
     */
    function getIntegrationStats() external view returns (
        uint256 totalMappings,
        uint256 pendingCount,
        uint256 completedCount,
        uint256 failedCount,
        uint256 averageProcessingTime
    ) {
        uint256 completed = 0;
        uint256 failed = 0;
        uint256 totalTime = 0;
        uint256 processedCount = 0;
        
        for (uint256 i = 0; i < integrationCounter; i++) {
            PerformanceMapping storage perfMap = performanceMappings[i];
            if (perfMap.status == IntegrationStatus.COMPLETED) {
                completed++;
                totalTime += perfMap.processedAt - perfMap.createdAt;
                processedCount++;
            } else if (perfMap.status == IntegrationStatus.FAILED) {
                failed++;
            }
        }
        
        uint256 avgTime = processedCount > 0 ? totalTime / processedCount : 0;
        
        return (
            integrationCounter,
            pendingMappings.length,
            completed,
            failed,
            avgTime
        );
    }
    
    // Internal functions
    
    function _processMapping(uint256 _mappingId) internal {
        PerformanceMapping storage perfMap = performanceMappings[_mappingId];
        
        if (perfMap.status != IntegrationStatus.PENDING) {
            return;
        }
        
        try this._processMappingInternal(_mappingId) {
            perfMap.status = IntegrationStatus.COMPLETED;
            perfMap.processedAt = block.timestamp;
        } catch Error(string memory reason) {
            perfMap.status = IntegrationStatus.FAILED;
            perfMap.errorMessage = reason;
            perfMap.processedAt = block.timestamp;
            
            emit IntegrationFailed(_mappingId, reason, perfMap.performanceHash);
        } catch {
            perfMap.status = IntegrationStatus.FAILED;
            perfMap.errorMessage = "Unknown error";
            perfMap.processedAt = block.timestamp;
            
            emit IntegrationFailed(_mappingId, "Unknown error", perfMap.performanceHash);
        }
        
        // Remove from pending
        _removeFromPending(_mappingId);
    }
    
    function _processMappingInternal(uint256 _mappingId) external {
        PerformanceMapping storage perfMap = performanceMappings[_mappingId];
        
        // Get bounty details
        (,,,,,, bytes32 performanceCriteria, uint256 minAccuracy,,,,,) = agentBounty.getBounty(perfMap.bountyId);
        
        // Get submission details
        (uint256 bountyId, address submitter, bytes32 performanceHash, uint256 accuracy, uint256 responseTime,,,) = agentBounty.getSubmission(perfMap.submissionId);
        
        // Verify performance criteria match
        require(perfMap.performanceHash == performanceHash, "Performance hash mismatch");
        
        // Check if accuracy meets requirements
        require(accuracy >= minAccuracy, "Accuracy below minimum");
        
        // Auto-verify if conditions are met
        if (accuracy >= autoVerificationThreshold) {
            agentBounty.verifySubmission(perfMap.bountyId, perfMap.submissionId, true, address(this));
            
            // Update agent staking metrics
            agentStaking.updateAgentPerformance(submitter, accuracy, true);
            
            // Trigger staking rewards
            _triggerStakingRewards(submitter, accuracy);
        }
    }
    
    function _autoVerifyBounty(
        uint256 _bountyId,
        uint256 _submissionId,
        uint256 _accuracy,
        uint256 _responseTime
    ) internal {
        if (_accuracy >= autoVerificationThreshold) {
            agentBounty.verifySubmission(_bountyId, _submissionId, true, address(this));
        }
    }
    
    function _triggerStakingRewards(address _agentWallet, uint256 _accuracy) internal {
        // Calculate earnings based on accuracy
        uint256 baseEarnings = (_accuracy * 100) * 10**18; // Simplified calculation
        
        // Distribute to stakers
        try agentStaking.distributeAgentEarnings(_agentWallet, baseEarnings) {
            emit StakingRewardsTriggered(_agentWallet, baseEarnings, 0);
        } catch {
            // Handle staking distribution failure
        }
    }
    
    function _registerEventHandler(
        bytes32 _eventType,
        address _targetContract,
        bytes4 _functionSelector
    ) internal {
        eventHandlers[_eventType] = EventHandler({
            eventType: _eventType,
            targetContract: _targetContract,
            functionSelector: _functionSelector,
            isActive: true,
            priority: 0
        });
    }
    
    function _removeFromPending(uint256 _mappingId) internal {
        for (uint256 i = 0; i < pendingMappings.length; i++) {
            if (pendingMappings[i] == _mappingId) {
                pendingMappings[i] = pendingMappings[pendingMappings.length - 1];
                pendingMappings.pop();
                break;
            }
        }
    }
}
