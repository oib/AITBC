// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "./ZKReceiptVerifier.sol";
import "./Groth16Verifier.sol";
import "./IEnergyPricing.sol";

/**
 * @title AI Power Rental Contract
 * @dev Smart contract for AI compute power rental agreements with performance verification
 * @notice Manages rental agreements between AI compute providers and consumers
 */
contract AIPowerRental is Ownable, ReentrancyGuard, Pausable {

    // State variables
    IERC20 public paymentToken;
    ZKReceiptVerifier public zkVerifier;
    Groth16Verifier public groth16Verifier;
    IEnergyPricing public energyPricing;

    uint256 public agreementCounter;
    uint256 public platformFeePercentage = 250; // 2.5% in basis points
    uint256 public minRentalDuration = 3600; // 1 hour minimum
    uint256 public maxRentalDuration = 86400 * 30; // 30 days maximum
    /// @dev When true, new legacy (unprotected) rentals are blocked so that
    /// callers cannot bypass the energy floor by using createRental instead of
    /// createProtectedRental. Existing unprotected rentals are unaffected.
    bool public requireProtectedRentals;

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

    struct RentalEnergyTerms {
        string resourceId;
        string modelId;
        uint256 gpuCount;
        uint256 settlementUnitScale;
        uint256 tdpWatts;
        uint256 eurPerKwh;
        uint256 aitPerEur;
        uint256 rateVersion;
        uint256 rateObservedAt;
        uint256 rateSubmittedAt;
        string rateSourceKind;
        uint256 profileRevision;
        uint256 netEnergyFloor;
        uint256 buyerMaxTotal;
        bool isProtected;
        uint256 createdAt;
        uint256 fundedAt;
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
    mapping(uint256 => RentalEnergyTerms) public rentalEnergyTerms;
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

    event ProtectedAgreementCreated(
        uint256 indexed agreementId,
        address indexed provider,
        address indexed consumer,
        string resourceId,
        string modelId,
        uint256 gpuCount,
        uint256 duration,
        uint256 price,
        uint256 platformFee,
        uint256 netEnergyFloor
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
        address _paymentToken,
        address _zkVerifier,
        address _groth16Verifier
    ) {
        // Immutable contract: a zero address from a deploy-script typo cannot be corrected
        // afterwards. A zero verifier is the worse case -- proof checks would revert
        // rather than pass, but the contract is permanently unusable either way.
        require(_paymentToken != address(0), "payment token cannot be zero address");
        require(_zkVerifier != address(0), "ZK verifier cannot be zero address");
        require(_groth16Verifier != address(0), "groth16 verifier cannot be zero address");
        paymentToken = IERC20(_paymentToken);
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
        // Block new legacy rentals when the operator has enabled protected-only
        // mode. Existing unprotected rentals are not affected.
        require(!requireProtectedRentals, "Legacy rentals disabled; use createProtectedRental");

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
     * @dev Creates a protected fixed-duration GPU rental with an energy-cost floor.
     * @param _provider Address of the compute provider
     * @param _consumer Address of the compute consumer
     * @param _resourceId Registered resource identifier
     * @param _modelId GPU model as registered for the resource
     * @param _gpuCount Number of GPUs of this resource
     * @param _duration Duration in seconds
     * @param _price Provider principal in AITBC tokens (must cover the floor)
     * @param _buyerMaxTotal Maximum total the buyer authorizes (principal + platform fee)
     * @param _settlementUnitScale Atomic units per settlement token (e.g. 1e18 for 18-decimal AITBC)
     */
    function createProtectedRental(
        address _provider,
        address _consumer,
        string memory _resourceId,
        string memory _modelId,
        uint256 _gpuCount,
        uint256 _duration,
        uint256 _price,
        uint256 _buyerMaxTotal,
        uint256 _settlementUnitScale
    ) external onlyAuthorizedConsumer nonReentrant whenNotPaused returns (uint256) {
        require(_duration >= minRentalDuration, "Duration too short");
        require(_duration <= maxRentalDuration, "Duration too long");
        require(_price > 0, "Price must be positive");
        require(_consumer == msg.sender, "Consumer must be caller");
        require(authorizedProviders[_provider], "Provider not authorized");
        require(address(energyPricing) != address(0), "Energy pricing not configured");

        IEnergyPricing.EnergyProfile memory profile = energyPricing.getEnergyProfile(_resourceId);
        require(profile.enabled, "Energy profile disabled");
        require(_provider == profile.provider, "Provider does not match registered resource");
        require(
            keccak256(bytes(_modelId)) == keccak256(bytes(profile.modelId)),
            "Model does not match registered resource"
        );

        (uint256 netFloor, bool valid, ) = energyPricing.getEnergyFloor(
            _resourceId,
            _gpuCount,
            _duration,
            _settlementUnitScale
        );
        require(valid, "Energy floor is not valid");
        require(_price >= netFloor, "Price below energy floor");

        uint256 platformFee = (_price * platformFeePercentage) / 10000;
        uint256 totalAmount = _price + platformFee;
        require(totalAmount <= _buyerMaxTotal, "Buyer cap exceeded");

        IEnergyPricing.EnergyRate memory rate = energyPricing.getEnergyRate();
        require(rate.enabled, "Energy rate disabled");

        uint256 agreementId = agreementCounter++;

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
            gpuModel: _modelId,
            computeUnits: 0,
            performanceProof: bytes32(0)
        });

        rentalEnergyTerms[agreementId] = RentalEnergyTerms({
            resourceId: _resourceId,
            modelId: _modelId,
            gpuCount: _gpuCount,
            settlementUnitScale: _settlementUnitScale,
            tdpWatts: profile.tdpWatts,
            eurPerKwh: profile.eurPerKwh,
            aitPerEur: rate.aitPerEur,
            rateVersion: rate.version,
            rateObservedAt: rate.observedAt,
            rateSubmittedAt: rate.submittedAt,
            rateSourceKind: rate.sourceKind,
            profileRevision: profile.revision,
            netEnergyFloor: netFloor,
            buyerMaxTotal: _buyerMaxTotal,
            isProtected: true,
            createdAt: block.timestamp,
            fundedAt: 0
        });

        providerAgreements[_provider].push(agreementId);
        consumerAgreements[_consumer].push(agreementId);

        emit AgreementCreated(
            agreementId,
            _provider,
            _consumer,
            _duration,
            _price,
            _modelId,
            0
        );
        emit ProtectedAgreementCreated(
            agreementId,
            _provider,
            _consumer,
            _resourceId,
            _modelId,
            _gpuCount,
            _duration,
            _price,
            platformFee,
            netFloor
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
        whenNotPaused
    {
        RentalAgreement storage agreement = rentalAgreements[_agreementId];

        require(msg.sender == agreement.consumer, "Only consumer can start");

        uint256 totalAmount = agreement.price + agreement.platformFee;

        RentalEnergyTerms storage terms = rentalEnergyTerms[_agreementId];
        if (terms.isProtected) {
            require(address(energyPricing) != address(0), "Energy pricing not configured");

            // §5.1: the floor was pinned at createProtectedRental time and
            // frozen in terms.netEnergyFloor. Re-computing from the live oracle
            // here would re-price the quote: if the rate moved up, a valid
            // quote would be rejected; if it moved down, a below-floor quote
            // could be accepted. Use the pinned floor for the price check.
            require(agreement.price >= terms.netEnergyFloor, "Price below pinned energy floor");
            require(totalAmount <= terms.buyerMaxTotal, "Buyer cap exceeded at funding");

            // Verify the profile is still enabled and the provider/model still
            // match, but do not re-price.
            IEnergyPricing.EnergyProfile memory profile = energyPricing.getEnergyProfile(terms.resourceId);
            require(profile.enabled, "Energy profile disabled");
            require(
                agreement.provider == profile.provider,
                "Provider does not match registered resource"
            );
            require(
                keccak256(bytes(agreement.gpuModel)) == keccak256(bytes(profile.modelId)),
                "Model does not match registered resource"
            );

            // Check rate validity (enabled, not stale) via getEnergyFloor's
            // `valid` return, but discard the recomputed floor and use the
            // pinned value for the price comparison.
            (, bool valid, ) = energyPricing.getEnergyFloor(
                terms.resourceId,
                terms.gpuCount,
                agreement.duration,
                terms.settlementUnitScale
            );
            require(valid, "Energy rate stale or invalid at funding");

            IEnergyPricing.EnergyRate memory rate = energyPricing.getEnergyRate();
            require(rate.enabled, "Energy rate disabled at funding");

            // Snapshot the funding-time energy terms. The price and platform fee
            // were frozen at creation and are not changed here.
            terms.tdpWatts = profile.tdpWatts;
            terms.eurPerKwh = profile.eurPerKwh;
            terms.aitPerEur = rate.aitPerEur;
            terms.rateVersion = rate.version;
            terms.rateObservedAt = rate.observedAt;
            terms.rateSubmittedAt = rate.submittedAt;
            terms.rateSourceKind = rate.sourceKind;
            terms.profileRevision = profile.revision;
            terms.fundedAt = block.timestamp;
        }

        // §5.4: explicit balance and allowance checks before transferFrom so
        // the failure is diagnosable rather than a generic "Payment transfer
        // failed" that could mean anything.
        require(
            paymentToken.balanceOf(msg.sender) >= totalAmount,
            "Insufficient token balance"
        );
        require(
            paymentToken.allowance(msg.sender, address(this)) >= totalAmount,
            "Insufficient token allowance"
        );

        // Transfer tokens from consumer to contract
        require(
            paymentToken.transferFrom(msg.sender, address(this), totalAmount),
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
                paymentToken.transfer(agreement.provider, providerAmount),
                "Provider payment failed"
            );
        }

        if (platformFeeAmount > 0) {
            require(
                paymentToken.transfer(owner(), platformFeeAmount),
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
                paymentToken.transfer(winner, _resolutionAmount),
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
     * @dev Sets the energy pricing contract used for protected rentals
     * @param _energyPricing Address of the IEnergyPricing implementation
     */
    function setEnergyPricing(address _energyPricing) external onlyOwner {
        require(_energyPricing != address(0), "Energy pricing cannot be zero address");
        energyPricing = IEnergyPricing(_energyPricing);
    }

    /**
     * @dev Updates platform fee percentage
     * @param _newFee New fee percentage in basis points
     */
    function updatePlatformFee(uint256 _newFee) external onlyOwner {
        require(_newFee <= 1000, "Fee too high"); // Max 10%
        platformFeePercentage = _newFee;
    }

    /**
     * @dev When set to true, new legacy (unprotected) rentals are blocked.
     * Existing unprotected rentals are not affected.
     */
    function setRequireProtectedRentals(bool _required) external onlyOwner {
        requireProtectedRentals = _required;
    }

    // View functions

    /**
     * @dev Gets rental agreement details (core fields).
     * @param _agreementId ID of the agreement
     *
     * §5.6: the full RentalAgreement struct has 13 fields including a nested
     * PerformanceMetrics struct (6 fields), totalling 17+ when ABI-encoded.
     * This exceeds the EVM stack depth in coverage mode (no via_ir). Split
     * the view into core fields and performance metrics to stay under the
     * limit.
     */
    function getRentalAgreement(uint256 _agreementId)
        external
        view
        agreementExists(_agreementId)
        returns (
            uint256 agreementId,
            address provider,
            address consumer,
            uint256 duration,
            uint256 price,
            uint256 startTime,
            uint256 endTime,
            uint256 platformFee,
            RentalStatus status,
            string memory gpuModel,
            uint256 computeUnits,
            bytes32 performanceProof
        )
    {
        RentalAgreement storage a = rentalAgreements[_agreementId];
        return (
            a.agreementId,
            a.provider,
            a.consumer,
            a.duration,
            a.price,
            a.startTime,
            a.endTime,
            a.platformFee,
            a.status,
            a.gpuModel,
            a.computeUnits,
            a.performanceProof
        );
    }

    /**
     * @dev Gets the performance metrics for a rental agreement.
     * @param _agreementId ID of the agreement
     */
    function getRentalPerformance(uint256 _agreementId)
        external
        view
        agreementExists(_agreementId)
        returns (
            uint256 responseTime,
            uint256 accuracy,
            uint256 availability,
            uint256 computePower,
            bool withinSLA,
            uint256 lastUpdateTime
        )
    {
        PerformanceMetrics memory p = rentalAgreements[_agreementId].performance;
        return (
            p.responseTime,
            p.accuracy,
            p.availability,
            p.computePower,
            p.withinSLA,
            p.lastUpdateTime
        );
    }

    /**
     * @dev Gets the frozen energy terms for a rental agreement.
     * @param _agreementId ID of the agreement
     */
    function getRentalEnergyTerms(uint256 _agreementId)
        external
        view
        agreementExists(_agreementId)
        returns (RentalEnergyTerms memory)
    {
        return rentalEnergyTerms[_agreementId];
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
