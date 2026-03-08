// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "./ZKReceiptVerifier.sol";
import "./Groth16Verifier.sol";

/**
 * @title AI Power Rental Contract
 * @dev Smart contract for AI compute power rental agreements with performance verification
 * @notice Manages rental agreements between AI compute providers and consumers
 */
contract AIPowerRental is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    IERC20 public aitbcToken;
    ZKReceiptVerifier public zkVerifier;
    Groth16Verifier public groth16Verifier;
    
    uint256 public agreementCounter;
    uint256 public platformFeePercentage = 250; // 2.5% in basis points
    uint256 public minRentalDuration = 3600; // 1 hour minimum
    uint256 public maxRentalDuration = 86400 * 30; // 30 days maximum
    
    // Structs
    struct RentalAgreement {
        uint256 agreementId;
        address provider;
        address consumer;
        uint256 duration;
        uint256 price;
        uint256 startTime;
        uint256 endTime;
        uint256 platformFee;
        RentalStatus status;
        PerformanceMetrics performance;
        string gpuModel;
        uint256 computeUnits;
        bytes32 performanceProof;
    }
    
    struct PerformanceMetrics {
        uint256 responseTime;
        uint256 accuracy;
        uint256 availability;
        uint256 computePower;
        bool withinSLA;
        uint256 lastUpdateTime;
    }
    
    struct DisputeInfo {
        bool exists;
        address initiator;
        string reason;
        uint256 disputeTime;
        bool resolved;
        uint256 resolutionAmount;
    }
    
    // Enums
    enum RentalStatus {
        Created,
        Active,
        Completed,
        Disputed,
        Cancelled,
        Expired
    }
    
    // Mappings
    mapping(uint256 => RentalAgreement) public rentalAgreements;
    mapping(uint256 => DisputeInfo) public disputes;
    mapping(address => uint256[]) public providerAgreements;
    mapping(address => uint256[]) public consumerAgreements;
    mapping(address => bool) public authorizedProviders;
    mapping(address => bool) public authorizedConsumers;
    
    // Events
    event AgreementCreated(
        uint256 indexed agreementId,
        address indexed provider,
        address indexed consumer,
        uint256 duration,
        uint256 price,
        string gpuModel,
        uint256 computeUnits
    );
    
    event AgreementStarted(
        uint256 indexed agreementId,
        uint256 startTime,
        uint256 endTime
    );
    
    event AgreementCompleted(
        uint256 indexed agreementId,
        uint256 completionTime,
        bool withinSLA
    );
    
    event PaymentProcessed(
        uint256 indexed agreementId,
        address indexed provider,
        uint256 amount,
        uint256 platformFee
    );
    
    event PerformanceSubmitted(
        uint256 indexed agreementId,
        uint256 responseTime,
        uint256 accuracy,
        uint256 availability,
        bool withinSLA
    );
    
    event DisputeFiled(
        uint256 indexed agreementId,
        address indexed initiator,
        string reason
    );
    
    event DisputeResolved(
        uint256 indexed agreementId,
        uint256 resolutionAmount,
        bool resolvedInFavorOfProvider
    );
    
    event ProviderAuthorized(address indexed provider);
    event ProviderRevoked(address indexed provider);
    event ConsumerAuthorized(address indexed consumer);
    event ConsumerRevoked(address indexed consumer);
    
    // Modifiers
    modifier onlyAuthorizedProvider() {
        require(authorizedProviders[msg.sender], "Not authorized provider");
        _;
    }
    
    modifier onlyAuthorizedConsumer() {
        require(authorizedConsumers[msg.sender], "Not authorized consumer");
        _;
    }
    
    modifier onlyParticipant(uint256 _agreementId) {
        require(
            rentalAgreements[_agreementId].provider == msg.sender ||
            rentalAgreements[_agreementId].consumer == msg.sender,
            "Not agreement participant"
        );
        _;
    }
    
    modifier agreementExists(uint256 _agreementId) {
        require(_agreementId < agreementCounter, "Agreement does not exist");
        _;
    }
    
    modifier validStatus(uint256 _agreementId, RentalStatus _requiredStatus) {
        require(rentalAgreements[_agreementId].status == _requiredStatus, "Invalid agreement status");
        _;
    }
    
    // Constructor
    constructor(
        address _aitbcToken,
        address _zkVerifier,
        address _groth16Verifier
    ) {
        aitbcToken = IERC20(_aitbcToken);
        zkVerifier = ZKReceiptVerifier(_zkVerifier);
        groth16Verifier = Groth16Verifier(_groth16Verifier);
        agreementCounter = 0;
    }
    
    /**
     * @dev Creates a new rental agreement
     * @param _provider Address of the compute provider
     * @param _consumer Address of the compute consumer
     * @param _duration Duration in seconds
     * @param _price Total price in AITBC tokens
     * @param _gpuModel GPU model being rented
     * @param _computeUnits Amount of compute units
     */
    function createRental(
        address _provider,
        address _consumer,
        uint256 _duration,
        uint256 _price,
        string memory _gpuModel,
        uint256 _computeUnits
    ) external onlyAuthorizedConsumer nonReentrant whenNotPaused returns (uint256) {
        require(_duration >= minRentalDuration, "Duration too short");
        require(_duration <= maxRentalDuration, "Duration too long");
        require(_price > 0, "Price must be positive");
        require(authorizedProviders[_provider], "Provider not authorized");
        
        uint256 agreementId = agreementCounter++;
        uint256 platformFee = (_price * platformFeePercentage) / 10000;
        
        rentalAgreements[agreementId] = RentalAgreement({
            agreementId: agreementId,
            provider: _provider,
            consumer: _consumer,
            duration: _duration,
            price: _price,
            startTime: 0,
            endTime: 0,
            platformFee: platformFee,
            status: RentalStatus.Created,
            performance: PerformanceMetrics({
                responseTime: 0,
                accuracy: 0,
                availability: 0,
                computePower: 0,
                withinSLA: false,
                lastUpdateTime: 0
            }),
            gpuModel: _gpuModel,
            computeUnits: _computeUnits,
            performanceProof: bytes32(0)
        });
        
        providerAgreements[_provider].push(agreementId);
        consumerAgreements[_consumer].push(agreementId);
        
        emit AgreementCreated(
            agreementId,
            _provider,
            _consumer,
            _duration,
            _price,
            _gpuModel,
            _computeUnits
        );
        
        return agreementId;
    }
    
    /**
     * @dev Starts a rental agreement and locks payment
     * @param _agreementId ID of the agreement to start
     */
    function startRental(uint256 _agreementId) 
        external 
        agreementExists(_agreementId)
        validStatus(_agreementId, RentalStatus.Created)
        nonReentrant 
    {
        RentalAgreement storage agreement = rentalAgreements[_agreementId];
        
        require(msg.sender == agreement.consumer, "Only consumer can start");
        
        uint256 totalAmount = agreement.price + agreement.platformFee;
        
        // Transfer tokens from consumer to contract
        require(
            aitbcToken.transferFrom(msg.sender, address(this), totalAmount),
            "Payment transfer failed"
        );
        
        agreement.startTime = block.timestamp;
        agreement.endTime = block.timestamp + agreement.duration;
        agreement.status = RentalStatus.Active;
        
        emit AgreementStarted(_agreementId, agreement.startTime, agreement.endTime);
    }
    
    /**
     * @dev Completes a rental agreement and processes payment
     * @param _agreementId ID of the agreement to complete
     */
    function completeRental(uint256 _agreementId) 
        external 
        agreementExists(_agreementId)
        validStatus(_agreementId, RentalStatus.Active)
        onlyParticipant(_agreementId)
        nonReentrant 
    {
        RentalAgreement storage agreement = rentalAgreements[_agreementId];
        
        require(block.timestamp >= agreement.endTime, "Rental period not ended");
        
        agreement.status = RentalStatus.Completed;
        
        // Process payment to provider
        uint256 providerAmount = agreement.price;
        uint256 platformFeeAmount = agreement.platformFee;
        
        if (providerAmount > 0) {
            require(
                aitbcToken.transfer(agreement.provider, providerAmount),
                "Provider payment failed"
            );
        }
        
        if (platformFeeAmount > 0) {
            require(
                aitbcToken.transfer(owner(), platformFeeAmount),
                "Platform fee transfer failed"
            );
        }
        
        emit PaymentProcessed(_agreementId, agreement.provider, providerAmount, platformFeeAmount);
        emit AgreementCompleted(_agreementId, block.timestamp, agreement.performance.withinSLA);
    }
    
    /**
     * @dev Files a dispute for a rental agreement
     * @param _agreementId ID of the agreement
     * @param _reason Reason for the dispute
     */
    function disputeRental(uint256 _agreementId, string memory _reason) 
        external 
        agreementExists(_agreementId)
        onlyParticipant(_agreementId)
        nonReentrant 
    {
        RentalAgreement storage agreement = rentalAgreements[_agreementId];
        
        require(
            agreement.status == RentalStatus.Active || 
            agreement.status == RentalStatus.Completed,
            "Cannot dispute this agreement"
        );
        
        require(!disputes[_agreementId].exists, "Dispute already exists");
        
        disputes[_agreementId] = DisputeInfo({
            exists: true,
            initiator: msg.sender,
            reason: _reason,
            disputeTime: block.timestamp,
            resolved: false,
            resolutionAmount: 0
        });
        
        agreement.status = RentalStatus.Disputed;
        
        emit DisputeFiled(_agreementId, msg.sender, _reason);
    }
    
    /**
     * @dev Submits performance metrics for a rental agreement
     * @param _agreementId ID of the agreement
     * @param _responseTime Response time in milliseconds
     * @param _accuracy Accuracy percentage (0-100)
     * @param _availability Availability percentage (0-100)
     * @param _computePower Compute power utilized
     * @param _zkProof Zero-knowledge proof for performance verification
     */
    function submitPerformance(
        uint256 _agreementId,
        uint256 _responseTime,
        uint256 _accuracy,
        uint256 _availability,
        uint256 _computePower,
        bytes memory _zkProof
    ) external agreementExists(_agreementId) onlyAuthorizedProvider {
        RentalAgreement storage agreement = rentalAgreements[_agreementId];
        
        require(agreement.status == RentalStatus.Active, "Agreement not active");
        
        // Verify ZK proof
        bool proofValid = zkVerifier.verifyPerformanceProof(
            _agreementId,
            _responseTime,
            _accuracy,
            _availability,
            _computePower,
            _zkProof
        );
        
        require(proofValid, "Invalid performance proof");
        
        agreement.performance = PerformanceMetrics({
            responseTime: _responseTime,
            accuracy: _accuracy,
            availability: _availability,
            computePower: _computePower,
            withinSLA: _calculateSLA(_responseTime, _accuracy, _availability),
            lastUpdateTime: block.timestamp
        });
        
        agreement.performanceProof = keccak256(_zkProof);
        
        emit PerformanceSubmitted(
            _agreementId,
            _responseTime,
            _accuracy,
            _availability,
            agreement.performance.withinSLA
        );
    }
    
    /**
     * @dev Authorizes a provider to offer compute services
     * @param _provider Address of the provider
     */
    function authorizeProvider(address _provider) external onlyOwner {
        authorizedProviders[_provider] = true;
        emit ProviderAuthorized(_provider);
    }
    
    /**
     * @dev Revokes provider authorization
     * @param _provider Address of the provider
     */
    function revokeProvider(address _provider) external onlyOwner {
        authorizedProviders[_provider] = false;
        emit ProviderRevoked(_provider);
    }
    
    /**
     * @dev Authorizes a consumer to rent compute services
     * @param _consumer Address of the consumer
     */
    function authorizeConsumer(address _consumer) external onlyOwner {
        authorizedConsumers[_consumer] = true;
        emit ConsumerAuthorized(_consumer);
    }
    
    /**
     * @dev Revokes consumer authorization
     * @param _consumer Address of the consumer
     */
    function revokeConsumer(address _consumer) external onlyOwner {
        authorizedConsumers[_consumer] = false;
        emit ConsumerRevoked(_consumer);
    }
    
    /**
     * @dev Resolves a dispute
     * @param _agreementId ID of the disputed agreement
     * @param _resolutionAmount Amount to award to the winner
     * @param _resolveInFavorOfProvider True if resolving in favor of provider
     */
    function resolveDispute(
        uint256 _agreementId,
        uint256 _resolutionAmount,
        bool _resolveInFavorOfProvider
    ) external onlyOwner agreementExists(_agreementId) {
        require(disputes[_agreementId].exists, "No dispute exists");
        require(!disputes[_agreementId].resolved, "Dispute already resolved");
        
        RentalAgreement storage agreement = rentalAgreements[_agreementId];
        disputes[_agreementId].resolved = true;
        disputes[_agreementId].resolutionAmount = _resolutionAmount;
        
        address winner = _resolveInFavorOfProvider ? agreement.provider : agreement.consumer;
        
        if (_resolutionAmount > 0) {
            require(
                aitbcToken.transfer(winner, _resolutionAmount),
                "Resolution payment failed"
            );
        }
        
        emit DisputeResolved(_agreementId, _resolutionAmount, _resolveInFavorOfProvider);
    }
    
    /**
     * @dev Cancels a rental agreement (only before it starts)
     * @param _agreementId ID of the agreement to cancel
     */
    function cancelRental(uint256 _agreementId) 
        external 
        agreementExists(_agreementId)
        validStatus(_agreementId, RentalStatus.Created)
        onlyParticipant(_agreementId)
        nonReentrant 
    {
        RentalAgreement storage agreement = rentalAgreements[_agreementId];
        agreement.status = RentalStatus.Cancelled;
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
    
    /**
     * @dev Updates platform fee percentage
     * @param _newFee New fee percentage in basis points
     */
    function updatePlatformFee(uint256 _newFee) external onlyOwner {
        require(_newFee <= 1000, "Fee too high"); // Max 10%
        platformFeePercentage = _newFee;
    }
    
    // View functions
    
    /**
     * @dev Gets rental agreement details
     * @param _agreementId ID of the agreement
     */
    function getRentalAgreement(uint256 _agreementId) 
        external 
        view 
        agreementExists(_agreementId) 
        returns (RentalAgreement memory) 
    {
        return rentalAgreements[_agreementId];
    }
    
    /**
     * @dev Gets dispute information
     * @param _agreementId ID of the agreement
     */
    function getDisputeInfo(uint256 _agreementId) 
        external 
        view 
        agreementExists(_agreementId) 
        returns (DisputeInfo memory) 
    {
        return disputes[_agreementId];
    }
    
    /**
     * @dev Gets all agreements for a provider
     * @param _provider Address of the provider
     */
    function getProviderAgreements(address _provider) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return providerAgreements[_provider];
    }
    
    /**
     * @dev Gets all agreements for a consumer
     * @param _consumer Address of the consumer
     */
    function getConsumerAgreements(address _consumer) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return consumerAgreements[_consumer];
    }
    
    /**
     * @dev Calculates if performance meets SLA requirements
     */
    function _calculateSLA(
        uint256 _responseTime,
        uint256 _accuracy,
        uint256 _availability
    ) internal pure returns (bool) {
        return _responseTime <= 5000 && // <= 5 seconds
               _accuracy >= 95 && // >= 95% accuracy
               _availability >= 99; // >= 99% availability
    }
}
