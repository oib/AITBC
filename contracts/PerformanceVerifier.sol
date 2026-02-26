// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "./ZKReceiptVerifier.sol";
import "./Groth16Verifier.sol";
import "./AIPowerRental.sol";

/**
 * @title Performance Verifier
 * @dev Advanced performance verification contract with ZK proofs and oracle integration
 * @notice Verifies AI service performance metrics and enforces SLA compliance
 */
contract PerformanceVerifier is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    ZKReceiptVerifier public zkVerifier;
    Groth16Verifier public groth16Verifier;
    AIPowerRental public aiPowerRental;
    
    uint256 public verificationCounter;
    uint256 public minResponseTime = 100; // 100ms minimum
    uint256 public maxResponseTime = 5000; // 5 seconds maximum
    uint256 public minAccuracy = 90; // 90% minimum accuracy
    uint256 public minAvailability = 95; // 95% minimum availability
    uint256 public verificationWindow = 3600; // 1 hour verification window
    uint256 public penaltyPercentage = 500; // 5% penalty in basis points
    uint256 public rewardPercentage = 200; // 2% reward in basis points

    // Optimistic Rollup / Dispute variables
    uint256 public disputeWindow = 3600; // 1 hour dispute window before execution is final
    mapping(uint256 => uint256) public verificationFinalizedAt;

    
    // Structs
    struct PerformanceMetrics {
        uint256 verificationId;
        uint256 agreementId;
        address provider;
        uint256 responseTime;
        uint256 accuracy;
        uint256 availability;
        uint256 computePower;
        uint256 throughput;
        uint256 memoryUsage;
        uint256 energyEfficiency;
        bool withinSLA;
        uint256 timestamp;
        bytes32 zkProof;
        bytes32 groth16Proof;
        VerificationStatus status;
        uint256 penaltyAmount;
        uint256 rewardAmount;
    }
    
    struct SLAParameters {
        uint256 maxResponseTime;
        uint256 minAccuracy;
        uint256 minAvailability;
        uint256 minComputePower;
        uint256 maxMemoryUsage;
        uint256 minEnergyEfficiency;
        bool isActive;
        uint256 lastUpdated;
    }
    
    struct OracleData {
        address oracleAddress;
        uint256 lastUpdateTime;
        bool isAuthorized;
        uint256 reputationScore;
        uint256 totalReports;
        uint256 accurateReports;
    }
    
    struct PerformanceHistory {
        uint256 totalVerifications;
        uint256 successfulVerifications;
        uint256 averageResponseTime;
        uint256 averageAccuracy;
        uint256 averageAvailability;
        uint256 lastVerificationTime;
        uint256 currentStreak;
        uint256 bestStreak;
    }
    
    // Enums
    enum VerificationStatus {
        Submitted,
        Pending,
        Verified,
        Rejected,
        Expired,
        Disputed
    }
    
    enum MetricType {
        ResponseTime,
        Accuracy,
        Availability,
        ComputePower,
        Throughput,
        MemoryUsage,
        EnergyEfficiency
    }
    
    // Mappings
    mapping(uint256 => PerformanceMetrics) public performanceMetrics;
    mapping(uint256 => SLAParameters) public slaParameters;
    mapping(address => OracleData) public oracles;
    mapping(address => PerformanceHistory) public providerHistory;
    mapping(uint256 => uint256[]) public agreementVerifications;
    mapping(address => uint256[]) public providerVerifications;
    mapping(bytes32 => uint256) public proofToVerification;
    
    // Arrays for authorized oracles
    address[] public authorizedOracles;
    
    // Events
    event PerformanceSubmitted(
        uint256 indexed verificationId,
        uint256 indexed agreementId,
        address indexed provider,
        uint256 responseTime,
        uint256 accuracy,
        uint256 availability
    );
    
    event PerformanceVerified(
        uint256 indexed verificationId,
        bool withinSLA,
        uint256 penaltyAmount,
        uint256 rewardAmount
    );
    
    event PerformanceRejected(
        uint256 indexed verificationId,
        string reason,
        bytes32 invalidProof
    );
    
    event SLAParametersUpdated(
        uint256 indexed agreementId,
        uint256 maxResponseTime,
        uint256 minAccuracy,
        uint256 minAvailability
    );
    
    event OracleAuthorized(
        address indexed oracle,
        uint256 reputationScore
    );
    
    event OracleRevoked(
        address indexed oracle,
        string reason
    );
    
    event OracleReportSubmitted(
        address indexed oracle,
        uint256 indexed verificationId,
        bool accurate
    );
    
    event PenaltyApplied(
        uint256 indexed agreementId,
        address indexed provider,
        uint256 penaltyAmount
    );
    
    event RewardIssued(
        uint256 indexed agreementId,
        address indexed provider,
        uint256 rewardAmount
    );
    
    event PerformanceThresholdUpdated(
        MetricType indexed metricType,
        uint256 oldValue,
        uint256 newValue
    );
    
    // Modifiers
    modifier onlyAuthorizedOracle() {
        require(oracles[msg.sender].isAuthorized, "Not authorized oracle");
        _;
    }
    
    modifier verificationExists(uint256 _verificationId) {
        require(_verificationId < verificationCounter, "Verification does not exist");
        _;
    }
    
    modifier validStatus(uint256 _verificationId, VerificationStatus _requiredStatus) {
        require(performanceMetrics[_verificationId].status == _requiredStatus, "Invalid verification status");
        _;
    }
    
    modifier withinVerificationWindow(uint256 _timestamp) {
        require(block.timestamp - _timestamp <= verificationWindow, "Verification window expired");
        _;
    }
    
    // Constructor
    constructor(
        address _zkVerifier,
        address _groth16Verifier,
        address _aiPowerRental
    ) {
        zkVerifier = ZKReceiptVerifier(_zkVerifier);
        groth16Verifier = Groth16Verifier(_groth16Verifier);
        aiPowerRental = AIPowerRental(_aiPowerRental);
        verificationCounter = 0;
    }
    
    /**
     * @dev Submits performance metrics for verification
     * @param _agreementId ID of the rental agreement
     * @param _responseTime Response time in milliseconds
     * @param _accuracy Accuracy percentage (0-100)
     * @param _availability Availability percentage (0-100)
     * @param _computePower Compute power utilized
     * @param _throughput Throughput in requests per second
     * @param _memoryUsage Memory usage in MB
     * @param _energyEfficiency Energy efficiency score
     * @param _zkProof Zero-knowledge proof for performance verification
     * @param _groth16Proof Groth16 proof for additional verification
     */
    function submitPerformance(
        uint256 _agreementId,
        uint256 _responseTime,
        uint256 _accuracy,
        uint256 _availability,
        uint256 _computePower,
        uint256 _throughput,
        uint256 _memoryUsage,
        uint256 _energyEfficiency,
        bytes memory _zkProof,
        bytes memory _groth16Proof
    ) external nonReentrant whenNotPaused returns (uint256) {
        require(_responseTime >= minResponseTime && _responseTime <= maxResponseTime, "Invalid response time");
        require(_accuracy <= 100, "Invalid accuracy");
        require(_availability <= 100, "Invalid availability");
        
        // Get agreement details
        (, address provider, , , , , , , , ) = aiPowerRental.getRentalAgreement(_agreementId);
        require(provider != address(0), "Invalid agreement");
        
        uint256 verificationId = verificationCounter++;
        
        performanceMetrics[verificationId] = PerformanceMetrics({
            verificationId: verificationId,
            agreementId: _agreementId,
            provider: provider,
            responseTime: _responseTime,
            accuracy: _accuracy,
            availability: _availability,
            computePower: _computePower,
            throughput: _throughput,
            memoryUsage: _memoryUsage,
            energyEfficiency: _energyEfficiency,
            withinSLA: false,
            timestamp: block.timestamp,
            zkProof: keccak256(_zkProof),
            groth16Proof: keccak256(_groth16Proof),
            status: VerificationStatus.Submitted,
            penaltyAmount: 0,
            rewardAmount: 0
        });
        
        agreementVerifications[_agreementId].push(verificationId);
        providerVerifications[provider].push(verificationId);
        proofToVerification[keccak256(_zkProof)] = verificationId;
        
        emit PerformanceSubmitted(
            verificationId,
            _agreementId,
            provider,
            _responseTime,
            _accuracy,
            _availability
        );
        
        // Auto-verify if proofs are valid
        if (_verifyProofs(_zkProof, _groth16Proof, verificationId)) {
            _verifyPerformance(verificationId);
        } else {
            performanceMetrics[verificationId].status = VerificationStatus.Pending;
        }
        
        return verificationId;
    }
    
    /**
     * @dev Verifies performance metrics (oracle verification)
     * @param _verificationId ID of the verification
     * @param _accurate Whether the metrics are accurate
     * @param _additionalData Additional verification data
     */
    function verifyPerformance(
        uint256 _verificationId,
        bool _accurate,
        string memory _additionalData
    ) external onlyAuthorizedOracle verificationExists(_verificationId) validStatus(_verificationId, VerificationStatus.Pending) {
        PerformanceMetrics storage metrics = performanceMetrics[_verificationId];
        
        require(block.timestamp - metrics.timestamp <= verificationWindow, "Verification window expired");
        
        // Update oracle statistics
        OracleData storage oracle = oracles[msg.sender];
        oracle.totalReports++;
        if (_accurate) {
            oracle.accurateReports++;
        }
        oracle.lastUpdateTime = block.timestamp;
        
        if (_accurate) {
            _verifyPerformance(_verificationId);
        } else {
            metrics.status = VerificationStatus.Rejected;
            emit PerformanceRejected(_verificationId, _additionalData, metrics.zkProof);
        }
        
        emit OracleReportSubmitted(msg.sender, _verificationId, _accurate);
    }
    
    /**
     * @dev Sets SLA parameters for an agreement
     * @param _agreementId ID of the agreement
     * @param _maxResponseTime Maximum allowed response time
     * @param _minAccuracy Minimum required accuracy
     * @param _minAvailability Minimum required availability
     * @param _minComputePower Minimum required compute power
     * @param _maxMemoryUsage Maximum allowed memory usage
     * @param _minEnergyEfficiency Minimum energy efficiency
     */
    function setSLAParameters(
        uint256 _agreementId,
        uint256 _maxResponseTime,
        uint256 _minAccuracy,
        uint256 _minAvailability,
        uint256 _minComputePower,
        uint256 _maxMemoryUsage,
        uint256 _minEnergyEfficiency
    ) external onlyOwner {
        slaParameters[_agreementId] = SLAParameters({
            maxResponseTime: _maxResponseTime,
            minAccuracy: _minAccuracy,
            minAvailability: _minAvailability,
            minComputePower: _minComputePower,
            maxMemoryUsage: _maxMemoryUsage,
            minEnergyEfficiency: _minEnergyEfficiency,
            isActive: true,
            lastUpdated: block.timestamp
        });
        
        emit SLAParametersUpdated(
            _agreementId,
            _maxResponseTime,
            _minAccuracy,
            _minAvailability
        );
    }
    
    /**
     * @dev Authorizes an oracle
     * @param _oracle Address of the oracle
     * @param _reputationScore Initial reputation score
     */
    function authorizeOracle(address _oracle, uint256 _reputationScore) external onlyOwner {
        require(_oracle != address(0), "Invalid oracle address");
        require(!oracles[_oracle].isAuthorized, "Oracle already authorized");
        
        oracles[_oracle] = OracleData({
            oracleAddress: _oracle,
            lastUpdateTime: block.timestamp,
            isAuthorized: true,
            reputationScore: _reputationScore,
            totalReports: 0,
            accurateReports: 0
        });
        
        authorizedOracles.push(_oracle);
        
        emit OracleAuthorized(_oracle, _reputationScore);
    }
    
    /**
     * @dev Revokes oracle authorization
     * @param _oracle Address of the oracle
     * @param _reason Reason for revocation
     */
    function revokeOracle(address _oracle, string memory _reason) external onlyOwner {
        require(oracles[_oracle].isAuthorized, "Oracle not authorized");
        
        oracles[_oracle].isAuthorized = false;
        
        emit OracleRevoked(_oracle, _reason);
    }
    
    /**
     * @dev Updates performance thresholds
     * @param _metricType Type of metric
     * @param _newValue New threshold value
     */
    function updatePerformanceThreshold(MetricType _metricType, uint256 _newValue) external onlyOwner {
        uint256 oldValue;
        
        if (_metricType == MetricType.ResponseTime) {
            oldValue = maxResponseTime;
            maxResponseTime = _newValue;
        } else if (_metricType == MetricType.Accuracy) {
            oldValue = minAccuracy;
            minAccuracy = _newValue;
        } else if (_metricType == MetricType.Availability) {
            oldValue = minAvailability;
            minAvailability = _newValue;
        } else if (_metricType == MetricType.ComputePower) {
            oldValue = minComputePower;
            minComputePower = _newValue;
        } else {
            revert("Invalid metric type");
        }
        
        emit PerformanceThresholdUpdated(_metricType, oldValue, _newValue);
    }
    
    /**
     * @dev Calculates penalty for SLA violation
     * @param _verificationId ID of the verification
     */
    function calculatePenalty(uint256 _verificationId) 
        external 
        view 
        verificationExists(_verificationId) 
        returns (uint256) 
    {
        PerformanceMetrics memory metrics = performanceMetrics[_verificationId];
        
        if (metrics.withinSLA) {
            return 0;
        }
        
        // Get agreement details to calculate penalty amount
        (, address provider, , uint256 duration, uint256 price, , , , , ) = aiPowerRental.getRentalAgreement(metrics.agreementId);
        
        // Penalty based on severity of violation
        uint256 penaltyAmount = (price * penaltyPercentage) / 10000;
        
        // Additional penalties for severe violations
        if (metrics.responseTime > maxResponseTime * 2) {
            penaltyAmount += (price * 1000) / 10000; // Additional 10%
        }
        
        if (metrics.accuracy < minAccuracy - 10) {
            penaltyAmount += (price * 1000) / 10000; // Additional 10%
        }
        
        return penaltyAmount;
    }
    
    /**
     * @dev Calculates reward for exceeding SLA
     * @param _verificationId ID of the verification
     */
    function calculateReward(uint256 _verificationId) 
        external 
        view 
        verificationExists(_verificationId) 
        returns (uint256) 
    {
        PerformanceMetrics memory metrics = performanceMetrics[_verificationId];
        
        if (!metrics.withinSLA) {
            return 0;
        }
        
        // Get agreement details
        (, address provider, , uint256 duration, uint256 price, , , , , ) = aiPowerRental.getRentalAgreement(metrics.agreementId);
        
        // Reward based on performance quality
        uint256 rewardAmount = (price * rewardPercentage) / 10000;
        
        // Additional rewards for exceptional performance
        if (metrics.responseTime < maxResponseTime / 2) {
            rewardAmount += (price * 500) / 10000; // Additional 5%
        }
        
        if (metrics.accuracy > minAccuracy + 5) {
            rewardAmount += (price * 500) / 10000; // Additional 5%
        }
        
        return rewardAmount;
    }
    
    /**
     * @dev Gets performance history for a provider
     * @param _provider Address of the provider
     */
    function getProviderHistory(address _provider) 
        external 
        view 
        returns (PerformanceHistory memory) 
    {
        return providerHistory[_provider];
    }
    
    /**
     * @dev Gets all verifications for an agreement
     * @param _agreementId ID of the agreement
     */
    function getAgreementVerifications(uint256 _agreementId) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return agreementVerifications[_agreementId];
    }
    
    /**
     * @dev Gets all verifications for a provider
     * @param _provider Address of the provider
     */
    function getProviderVerifications(address _provider) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return providerVerifications[_provider];
    }
    
    /**
     * @dev Gets oracle information
     * @param _oracle Address of the oracle
     */
    function getOracleInfo(address _oracle) 
        external 
        view 
        returns (OracleData memory) 
    {
        return oracles[_oracle];
    }
    
    /**
     * @dev Gets all authorized oracles
     */
    function getAuthorizedOracles() 
        external 
        view 
        returns (address[] memory) 
    {
        address[] memory activeOracles = new address[](authorizedOracles.length);
        uint256 activeCount = 0;
        
        for (uint256 i = 0; i < authorizedOracles.length; i++) {
            if (oracles[authorizedOracles[i]].isAuthorized) {
                activeOracles[activeCount] = authorizedOracles[i];
                activeCount++;
            }
        }
        
        // Resize array to active count
        assembly {
            mstore(activeOracles, activeCount)
        }
        
        return activeOracles;
    }
    
    // Internal functions
    
    function _verifyProofs(
        bytes memory _zkProof,
        bytes memory _groth16Proof,
        uint256 _verificationId
    ) internal view returns (bool) {
        PerformanceMetrics memory metrics = performanceMetrics[_verificationId];
        
        // Verify ZK proof
        bool zkValid = zkVerifier.verifyPerformanceProof(
            metrics.agreementId,
            metrics.responseTime,
            metrics.accuracy,
            metrics.availability,
            metrics.computePower,
            _zkProof
        );
        
        // Verify Groth16 proof
        bool groth16Valid = groth16Verifier.verifyProof(_groth16Proof);
        
        return zkValid && groth16Valid;
    }
    
function _verifyPerformance(uint256 _verificationId) internal {
        PerformanceMetrics storage metrics = performanceMetrics[_verificationId];
        
        // Setup optimistic rollup finalization time
        verificationFinalizedAt[_verificationId] = block.timestamp + disputeWindow;
        metrics.status = VerificationStatus.Verified;
        
        emit PerformanceVerified(_verificationId, metrics.score, metrics.zkProof);
    }
    
    /**
     * @dev Finalizes an optimistic verification after the dispute window has passed
     * @param _verificationId ID of the verification
     */
    function finalizeOptimisticVerification(uint256 _verificationId) external verificationExists(_verificationId) {
        PerformanceMetrics storage metrics = performanceMetrics[_verificationId];
        require(metrics.status == VerificationStatus.Verified, "Verification not in verified status");
        require(block.timestamp >= verificationFinalizedAt[_verificationId], "Dispute window still open");
        
        metrics.status = VerificationStatus.Completed;
        
        // Execute SLA logic (distribute rewards/penalties)
        if (metrics.score >= minAccuracy) {
            _rewardProvider(metrics.provider, metrics.agreementId);
        } else {
            _penalizeProvider(metrics.provider, metrics.agreementId);
        }
    }
    
    /**
     * @dev Challenge an optimistic verification within the dispute window
     * @param _verificationId ID of the verification
     * @param _challengeData Evidence of invalid performance
     */
    function challengeVerification(uint256 _verificationId, string memory _challengeData) external verificationExists(_verificationId) {
        PerformanceMetrics storage metrics = performanceMetrics[_verificationId];
        require(metrics.status == VerificationStatus.Verified, "Verification not in verified status");
        require(block.timestamp < verificationFinalizedAt[_verificationId], "Dispute window closed");
        
        // A watcher node challenges the verification
        // Switch to manual review or on-chain full ZK validation
        metrics.status = VerificationStatus.Challenged;
        emit VerificationChallenged(_verificationId, msg.sender, _challengeData);
    }
    
    function _updateProviderHistory(address _provider, bool _withinSLA) internal {
        PerformanceHistory storage history = providerHistory[_provider];
        
        history.totalVerifications++;
        if (_withinSLA) {
            history.successfulVerifications++;
            history.currentStreak++;
            if (history.currentStreak > history.bestStreak) {
                history.bestStreak = history.currentStreak;
            }
        } else {
            history.currentStreak = 0;
        }
        
        history.lastVerificationTime = block.timestamp;
        
        // Update averages (simplified calculation)
        // In a real implementation, you'd want to maintain running averages
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
