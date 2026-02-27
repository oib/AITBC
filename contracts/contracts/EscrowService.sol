// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./AIPowerRental.sol";
import "./AITBCPaymentProcessor.sol";

/**
 * @title Escrow Service
 * @dev Advanced escrow service with multi-signature, time-locks, and conditional releases
 * @notice Secure payment holding with automated release conditions and dispute protection
 */
contract EscrowService is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    IERC20 public aitbcToken;
    AIPowerRental public aiPowerRental;
    AITBCPaymentProcessor public paymentProcessor;
    
    uint256 public escrowCounter;
    uint256 public minEscrowAmount = 1e15; // 0.001 AITBC minimum
    uint256 public maxEscrowAmount = 1e22; // 10,000 AITBC maximum
    uint256 public minTimeLock = 300; // 5 minutes minimum
    uint256 public maxTimeLock = 86400 * 30; // 30 days maximum
    uint256 public defaultReleaseDelay = 3600; // 1 hour default
    uint256 public emergencyReleaseDelay = 86400; // 24 hours for emergency
    uint256 public platformFeePercentage = 50; // 0.5% in basis points
    
    // Structs
    struct EscrowAccount {
        uint256 escrowId;
        address depositor;
        address beneficiary;
        address arbiter;
        uint256 amount;
        uint256 platformFee;
        uint256 releaseTime;
        uint256 creationTime;
        bool isReleased;
        bool isRefunded;
        bool isFrozen;
        EscrowType escrowType;
        ReleaseCondition releaseCondition;
        bytes32 conditionHash;
        uint256 requiredSignatures;
        uint256 currentSignatures;
        mapping(address => bool) hasSigned;
    }
    
    struct ConditionalRelease {
        uint256 escrowId;
        bytes32 condition;
        bool conditionMet;
        address oracle;
        uint256 verificationTime;
        string conditionData;
        uint256 confidence;
    }
    
    struct MultiSigRelease {
        uint256 escrowId;
        address[] requiredSigners;
        uint256 signaturesRequired;
        mapping(address => bool) hasSigned;
        uint256 currentSignatures;
        uint256 deadline;
        bool isExecuted;
    }
    
    struct TimeLockRelease {
        uint256 escrowId;
        uint256 lockStartTime;
        uint256 lockDuration;
        uint256 releaseWindow;
        bool canEarlyRelease;
        uint256 earlyReleaseFee;
        bool isReleased;
    }
    
    struct EmergencyRelease {
        uint256 escrowId;
        address initiator;
        string reason;
        uint256 requestTime;
        uint256 votingDeadline;
        mapping(address => bool) hasVoted;
        uint256 votesFor;
        uint256 votesAgainst;
        uint256 totalVotes;
        bool isApproved;
        bool isExecuted;
    }
    
    // Enums
    enum EscrowType {
        Standard,
        MultiSignature,
        TimeLocked,
        Conditional,
        PerformanceBased,
        MilestoneBased,
        Emergency
    }
    
    enum ReleaseCondition {
        Manual,
        Automatic,
        OracleVerified,
        PerformanceMet,
        TimeBased,
        MultiSignature,
        Emergency
    }
    
    enum EscrowStatus {
        Created,
        Funded,
        Locked,
        ConditionPending,
        Approved,
        Released,
        Refunded,
        Disputed,
        Frozen,
        Expired
    }
    
    // Mappings
    mapping(uint256 => EscrowAccount) public escrowAccounts;
    mapping(uint256 => ConditionalRelease) public conditionalReleases;
    mapping(uint256 => MultiSigRelease) public multiSigReleases;
    mapping(uint256 => TimeLockRelease) public timeLockReleases;
    mapping(uint256 => EmergencyRelease) public emergencyReleases;
    mapping(address => uint256[]) public depositorEscrows;
    mapping(address => uint256[]) public beneficiaryEscrows;
    mapping(bytes32 => uint256) public conditionEscrows;
    mapping(address => bool) public authorizedOracles;
    mapping(address => bool) public authorizedArbiters;
    
    // Arrays for tracking
    uint256[] public activeEscrows;
    uint256[] public pendingReleases;
    
    // Events
    event EscrowCreated(
        uint256 indexed escrowId,
        address indexed depositor,
        address indexed beneficiary,
        uint256 amount,
        EscrowType escrowType,
        ReleaseCondition releaseCondition
    );
    
    event EscrowFunded(
        uint256 indexed escrowId,
        uint256 amount,
        uint256 platformFee
    );
    
    event EscrowReleased(
        uint256 indexed escrowId,
        address indexed beneficiary,
        uint256 amount,
        string reason
    );
    
    event EscrowRefunded(
        uint256 indexed escrowId,
        address indexed depositor,
        uint256 amount,
        string reason
    );
    
    event ConditionSet(
        uint256 indexed escrowId,
        bytes32 indexed condition,
        address indexed oracle,
        string conditionDescription
    );
    
    event ConditionMet(
        uint256 indexed escrowId,
        bytes32 indexed condition,
        bool conditionMet,
        uint256 verificationTime
    );
    
    event MultiSignatureRequired(
        uint256 indexed escrowId,
        address[] requiredSigners,
        uint256 signaturesRequired
    );
    
    event SignatureSubmitted(
        uint256 indexed escrowId,
        address indexed signer,
        uint256 currentSignatures,
        uint256 requiredSignatures
    );
    
    event TimeLockSet(
        uint256 indexed escrowId,
        uint256 lockDuration,
        uint256 releaseWindow,
        bool canEarlyRelease
    );
    
    event EmergencyReleaseRequested(
        uint256 indexed escrowId,
        address indexed initiator,
        string reason,
        uint256 votingDeadline
    );
    
    event EmergencyReleaseApproved(
        uint256 indexed escrowId,
        uint256 votesFor,
        uint256 votesAgainst,
        bool approved
    );
    
    event EscrowFrozen(
        uint256 indexed escrowId,
        address indexed freezer,
        string reason
    );
    
    event EscrowUnfrozen(
        uint256 indexed escrowId,
        address indexed unfreezer,
        string reason
    );
    
    event PlatformFeeCollected(
        uint256 indexed escrowId,
        uint256 feeAmount,
        address indexed collector
    );
    
    // Modifiers
    modifier onlyAuthorizedOracle() {
        require(authorizedOracles[msg.sender], "Not authorized oracle");
        _;
    }
    
    modifier onlyAuthorizedArbiter() {
        require(authorizedArbiters[msg.sender], "Not authorized arbiter");
        _;
    }
    
    modifier escrowExists(uint256 _escrowId) {
        require(_escrowId < escrowCounter, "Escrow does not exist");
        _;
    }
    
    modifier onlyParticipant(uint256 _escrowId) {
        require(
            msg.sender == escrowAccounts[_escrowId].depositor ||
            msg.sender == escrowAccounts[_escrowId].beneficiary ||
            msg.sender == escrowAccounts[_escrowId].arbiter,
            "Not escrow participant"
        );
        _;
    }
    
    modifier sufficientBalance(address _user, uint256 _amount) {
        require(aitbcToken.balanceOf(_user) >= _amount, "Insufficient balance");
        _;
    }
    
    modifier sufficientAllowance(address _user, uint256 _amount) {
        require(aitbcToken.allowance(_user, address(this)) >= _amount, "Insufficient allowance");
        _;
    }
    
    modifier escrowNotFrozen(uint256 _escrowId) {
        require(!escrowAccounts[_escrowId].isFrozen, "Escrow is frozen");
        _;
    }
    
    modifier escrowNotReleased(uint256 _escrowId) {
        require(!escrowAccounts[_escrowId].isReleased, "Escrow already released");
        _;
    }
    
    modifier escrowNotRefunded(uint256 _escrowId) {
        require(!escrowAccounts[_escrowId].isRefunded, "Escrow already refunded");
        _;
    }
    
    // Constructor
    constructor(
        address _aitbcToken,
        address _aiPowerRental,
        address _paymentProcessor
    ) {
        aitbcToken = IERC20(_aitbcToken);
        aiPowerRental = AIPowerRental(_aiPowerRental);
        paymentProcessor = AITBCPaymentProcessor(_paymentProcessor);
        escrowCounter = 0;
    }
    
    /**
     * @dev Creates a new escrow account
     * @param _beneficiary Beneficiary address
     * @param _arbiter Arbiter address (can be zero address for no arbiter)
     * @param _amount Amount to lock in escrow
     * @param _escrowType Type of escrow
     * @param _releaseCondition Release condition
     * @param _releaseTime Release time (0 for no time limit)
     * @param _conditionDescription Description of release conditions
     */
    function createEscrow(
        address _beneficiary,
        address _arbiter,
        uint256 _amount,
        EscrowType _escrowType,
        ReleaseCondition _releaseCondition,
        uint256 _releaseTime,
        string memory _conditionDescription
    ) external sufficientBalance(msg.sender, _amount) sufficientAllowance(msg.sender, _amount) nonReentrant whenNotPaused returns (uint256) {
        require(_beneficiary != address(0), "Invalid beneficiary");
        require(_beneficiary != msg.sender, "Cannot be own beneficiary");
        require(_amount >= minEscrowAmount && _amount <= maxEscrowAmount, "Invalid amount");
        require(_releaseTime == 0 || _releaseTime > block.timestamp, "Invalid release time");
        
        uint256 escrowId = escrowCounter++;
        
        // Initialize escrow account
        _initializeEscrowAccount(escrowId, _beneficiary, _arbiter, _amount, _escrowType, _releaseCondition, _conditionDescription);
        
        // Update tracking arrays
        _updateEscrowTracking(escrowId, _beneficiary);
        
        // Transfer tokens to contract
        _transferTokensForEscrow(_amount);
        
        emit EscrowCreated(escrowId, msg.sender, _beneficiary, _amount, _escrowType, _releaseCondition);
        emit EscrowFunded(escrowId, _amount, (_amount * platformFeePercentage) / 10000);
        
        // Setup specific escrow type configurations
        if (_escrowType == EscrowType.TimeLocked) {
            _setupTimeLock(escrowId, _releaseTime - block.timestamp);
        } else if (_escrowType == EscrowType.MultiSignature) {
            _setupMultiSignature(escrowId);
        }
        
        return escrowId;
    }
    
    function _initializeEscrowAccount(
        uint256 _escrowId,
        address _beneficiary,
        address _arbiter,
        uint256 _amount,
        EscrowType _escrowType,
        ReleaseCondition _releaseCondition,
        string memory _conditionDescription
    ) internal {
        uint256 platformFee = (_amount * platformFeePercentage) / 10000;
        
        escrowAccounts[_escrowId].escrowId = _escrowId;
        escrowAccounts[_escrowId].depositor = msg.sender;
        escrowAccounts[_escrowId].beneficiary = _beneficiary;
        escrowAccounts[_escrowId].arbiter = _arbiter;
        escrowAccounts[_escrowId].amount = _amount;
        escrowAccounts[_escrowId].platformFee = platformFee;
        escrowAccounts[_escrowId].creationTime = block.timestamp;
        escrowAccounts[_escrowId].escrowType = _escrowType;
        escrowAccounts[_escrowId].releaseCondition = _releaseCondition;
    }
    
    function _updateEscrowTracking(uint256 _escrowId, address _beneficiary) internal {
        depositorEscrows[msg.sender].push(_escrowId);
        beneficiaryEscrows[_beneficiary].push(_escrowId);
        activeEscrows.push(_escrowId);
    }
    
    function _transferTokensForEscrow(uint256 _amount) internal {
        uint256 platformFee = (_amount * platformFeePercentage) / 10000;
        uint256 totalAmount = _amount + platformFee;
        
        require(
            aitbcToken.transferFrom(msg.sender, address(this), totalAmount),
            "Escrow funding failed"
        );
    }
    
    /**
     * @dev Sets release condition for escrow
     * @param _escrowId ID of the escrow
     * @param _condition Condition hash
     * @param _oracle Oracle address for verification
     * @param _conditionData Condition data
     */
    function setReleaseCondition(
        uint256 _escrowId,
        bytes32 _condition,
        address _oracle,
        string memory _conditionData
    ) external escrowExists(_escrowId) onlyParticipant(_escrowId) escrowNotFrozen(_escrowId) escrowNotReleased(_escrowId) {
        require(authorizedOracles[_oracle] || _oracle == address(0), "Invalid oracle");
        
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        escrow.conditionHash = _condition;
        
        conditionalReleases[_escrowId] = ConditionalRelease({
            escrowId: _escrowId,
            condition: _condition,
            conditionMet: false,
            oracle: _oracle,
            verificationTime: 0,
            conditionData: _conditionData,
            confidence: 0
        });
        
        conditionEscrows[_condition] = _escrowId;
        
        emit ConditionSet(_escrowId, _condition, _oracle, _conditionData);
    }
    
    /**
     * @dev Verifies and meets release condition
     * @param _escrowId ID of the escrow
     * @param _conditionMet Whether condition is met
     * @param _confidence Confidence level (0-100)
     */
    function verifyCondition(
        uint256 _escrowId,
        bool _conditionMet,
        uint256 _confidence
    ) external onlyAuthorizedOracle escrowExists(_escrowId) escrowNotFrozen(_escrowId) escrowNotReleased(_escrowId) {
        ConditionalRelease storage condRelease = conditionalReleases[_escrowId];
        require(condRelease.oracle == msg.sender, "Not assigned oracle");
        
        condRelease.conditionMet = _conditionMet;
        condRelease.verificationTime = block.timestamp;
        condRelease.confidence = _confidence;
        
        emit ConditionMet(_escrowId, condRelease.condition, _conditionMet, block.timestamp);
        
        if (_conditionMet) {
            _releaseEscrow(_escrowId, "Condition verified and met");
        }
    }
    
    /**
     * @dev Submits signature for multi-signature release
     * @param _escrowId ID of the escrow
     */
    function submitSignature(uint256 _escrowId) 
        external 
        escrowExists(_escrowId) 
        onlyParticipant(_escrowId) 
        escrowNotFrozen(_escrowId) 
        escrowNotReleased(_escrowId) 
    {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        MultiSigRelease storage multiSig = multiSigReleases[_escrowId];
        
        require(!escrow.hasSigned[msg.sender], "Already signed");
        require(escrow.requiredSignatures > 0, "Multi-signature not setup");
        
        escrow.hasSigned[msg.sender] = true;
        escrow.currentSignatures++;
        
        emit SignatureSubmitted(_escrowId, msg.sender, escrow.currentSignatures, escrow.requiredSignatures);
        
        if (escrow.currentSignatures >= escrow.requiredSignatures) {
            _releaseEscrow(_escrowId, "Multi-signature requirement met");
        }
    }
    
    /**
     * @dev Releases escrow to beneficiary
     * @param _escrowId ID of the escrow
     * @param _reason Reason for release
     */
    function releaseEscrow(uint256 _escrowId, string memory _reason) 
        external 
        escrowExists(_escrowId) 
        escrowNotFrozen(_escrowId) 
        escrowNotReleased(_escrowId) 
        escrowNotRefunded(_escrowId) 
        nonReentrant 
    {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        
        require(
            msg.sender == escrow.depositor ||
            msg.sender == escrow.beneficiary ||
            msg.sender == escrow.arbiter ||
            msg.sender == owner(),
            "Not authorized to release"
        );
        
        // Check release conditions
        if (escrow.releaseCondition == ReleaseCondition.Manual) {
            require(msg.sender == escrow.depositor || msg.sender == escrow.arbiter, "Manual release requires depositor or arbiter");
        } else if (escrow.releaseCondition == ReleaseCondition.TimeBased) {
            require(block.timestamp >= escrow.releaseTime, "Release time not reached");
        } else if (escrow.releaseCondition == ReleaseCondition.OracleVerified) {
            require(conditionalReleases[_escrowId].conditionMet, "Condition not met");
        } else if (escrow.releaseCondition == ReleaseCondition.MultiSignature) {
            require(escrow.currentSignatures >= escrow.requiredSignatures, "Insufficient signatures");
        }
        
        _releaseEscrow(_escrowId, _reason);
    }
    
    /**
     * @dev Refunds escrow to depositor
     * @param _escrowId ID of the escrow
     * @param _reason Reason for refund
     */
    function refundEscrow(uint256 _escrowId, string memory _reason) 
        external 
        escrowExists(_escrowId) 
        escrowNotFrozen(_escrowId) 
        escrowNotReleased(_escrowId) 
        escrowNotRefunded(_escrowId) 
        nonReentrant 
    {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        
        require(
            msg.sender == escrow.depositor ||
            msg.sender == escrow.arbiter ||
            msg.sender == owner(),
            "Not authorized to refund"
        );
        
        // Check refund conditions
        if (escrow.releaseCondition == ReleaseCondition.TimeBased) {
            require(block.timestamp < escrow.releaseTime, "Release time passed, cannot refund");
        } else if (escrow.releaseCondition == ReleaseCondition.OracleVerified) {
            require(!conditionalReleases[_escrowId].conditionMet, "Condition met, cannot refund");
        }
        
        escrow.isRefunded = true;
        
        require(
            aitbcToken.transfer(escrow.depositor, escrow.amount),
            "Refund transfer failed"
        );
        
        emit EscrowRefunded(_escrowId, escrow.depositor, escrow.amount, _reason);
    }
    
    /**
     * @dev Requests emergency release
     * @param _escrowId ID of the escrow
     * @param _reason Reason for emergency release
     */
    function requestEmergencyRelease(uint256 _escrowId, string memory _reason) 
        external 
        escrowExists(_escrowId) 
        onlyParticipant(_escrowId) 
        escrowNotFrozen(_escrowId) 
        escrowNotReleased(_escrowId) 
        escrowNotRefunded(_escrowId) 
    {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        
        EmergencyRelease storage emergency = emergencyReleases[_escrowId];
        require(emergency.requestTime == 0, "Emergency release already requested");
        
        // Initialize emergency release without nested mapping
        emergencyReleases[_escrowId].escrowId = _escrowId;
        emergencyReleases[_escrowId].initiator = msg.sender;
        emergencyReleases[_escrowId].reason = _reason;
        emergencyReleases[_escrowId].requestTime = block.timestamp;
        emergencyReleases[_escrowId].votingDeadline = block.timestamp + emergencyReleaseDelay;
        emergencyReleases[_escrowId].votesFor = 0;
        emergencyReleases[_escrowId].votesAgainst = 0;
        emergencyReleases[_escrowId].totalVotes = 0;
        emergencyReleases[_escrowId].isApproved = false;
        emergencyReleases[_escrowId].isExecuted = false;
        
        emit EmergencyReleaseRequested(_escrowId, msg.sender, _reason, block.timestamp + emergencyReleaseDelay);
    }
    
    /**
     * @dev Votes on emergency release
     * @param _escrowId ID of the escrow
     * @param _vote True to approve, false to reject
     */
    function voteEmergencyRelease(uint256 _escrowId, bool _vote) 
        external 
        escrowExists(_escrowId) 
        onlyAuthorizedArbiter 
    {
        EmergencyRelease storage emergency = emergencyReleases[_escrowId];
        
        require(emergency.requestTime > 0, "No emergency release requested");
        require(block.timestamp <= emergency.votingDeadline, "Voting deadline passed");
        require(!emergency.hasVoted[msg.sender], "Already voted");
        
        emergency.hasVoted[msg.sender] = true;
        emergency.totalVotes++;
        
        if (_vote) {
            emergency.votesFor++;
        } else {
            emergency.votesAgainst++;
        }
        
        // Check if voting is complete and approved
        if (emergency.totalVotes >= 3 && emergency.votesFor > emergency.votesAgainst) {
            emergency.isApproved = true;
            emit EmergencyReleaseApproved(_escrowId, emergency.votesFor, emergency.votesAgainst, true);
            _releaseEscrow(_escrowId, "Emergency release approved");
        }
    }
    
    /**
     * @dev Freezes an escrow account
     * @param _escrowId ID of the escrow
     * @param _reason Reason for freezing
     */
    function freezeEscrow(uint256 _escrowId, string memory _reason) 
        external 
        escrowExists(_escrowId) 
        escrowNotFrozen(_escrowId) 
    {
        require(
            msg.sender == escrowAccounts[_escrowId].arbiter ||
            msg.sender == owner(),
            "Not authorized to freeze"
        );
        
        escrowAccounts[_escrowId].isFrozen = true;
        
        emit EscrowFrozen(_escrowId, msg.sender, _reason);
    }
    
    /**
     * @dev Unfreezes an escrow account
     * @param _escrowId ID of the escrow
     * @param _reason Reason for unfreezing
     */
    function unfreezeEscrow(uint256 _escrowId, string memory _reason) 
        external 
        escrowExists(_escrowId) 
    {
        require(
            msg.sender == escrowAccounts[_escrowId].arbiter ||
            msg.sender == owner(),
            "Not authorized to unfreeze"
        );
        
        escrowAccounts[_escrowId].isFrozen = false;
        
        emit EscrowUnfrozen(_escrowId, msg.sender, _reason);
    }
    
    /**
     * @dev Authorizes an oracle
     * @param _oracle Address of the oracle
     */
    function authorizeOracle(address _oracle) external onlyOwner {
        require(_oracle != address(0), "Invalid oracle address");
        authorizedOracles[_oracle] = true;
    }
    
    /**
     * @dev Revokes oracle authorization
     * @param _oracle Address of the oracle
     */
    function revokeOracle(address _oracle) external onlyOwner {
        authorizedOracles[_oracle] = false;
    }
    
    /**
     * @dev Authorizes an arbiter
     * @param _arbiter Address of the arbiter
     */
    function authorizeArbiter(address _arbiter) external onlyOwner {
        require(_arbiter != address(0), "Invalid arbiter address");
        authorizedArbiters[_arbiter] = true;
    }
    
    /**
     * @dev Revokes arbiter authorization
     * @param _arbiter Address of the arbiter
     */
    function revokeArbiter(address _arbiter) external onlyOwner {
        authorizedArbiters[_arbiter] = false;
    }
    
    // Internal functions
    
    function _setupTimeLock(uint256 _escrowId, uint256 _duration) internal {
        require(_duration >= minTimeLock && _duration <= maxTimeLock, "Invalid duration");
        
        timeLockReleases[_escrowId] = TimeLockRelease({
            escrowId: _escrowId,
            lockStartTime: block.timestamp,
            lockDuration: _duration,
            releaseWindow: _duration / 10, // 10% of lock duration as release window
            canEarlyRelease: false,
            earlyReleaseFee: 1000, // 10% fee for early release
            isReleased: false
        });
        
        emit TimeLockSet(_escrowId, _duration, _duration / 10, false);
    }
    
    function _setupMultiSignature(uint256 _escrowId) internal {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        
        // Default to requiring depositor + beneficiary signatures
        address[] memory requiredSigners = new address[](2);
        requiredSigners[0] = escrow.depositor;
        requiredSigners[1] = escrow.beneficiary;
        
        // Initialize multi-sig release without nested mapping
        multiSigReleases[_escrowId].escrowId = _escrowId;
        multiSigReleases[_escrowId].signaturesRequired = 2;
        multiSigReleases[_escrowId].currentSignatures = 0;
        multiSigReleases[_escrowId].deadline = block.timestamp + 7 days;
        multiSigReleases[_escrowId].isExecuted = false;
        
        escrow.requiredSignatures = 2;
        
        emit MultiSignatureRequired(_escrowId, requiredSigners, 2);
    }
    
    function _releaseEscrow(uint256 _escrowId, string memory _reason) internal {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        
        escrow.isReleased = true;
        
        // Transfer amount to beneficiary
        require(
            aitbcToken.transfer(escrow.beneficiary, escrow.amount),
            "Escrow release failed"
        );
        
        // Transfer platform fee to owner
        if (escrow.platformFee > 0) {
            require(
                aitbcToken.transfer(owner(), escrow.platformFee),
                "Platform fee transfer failed"
            );
            
            emit PlatformFeeCollected(_escrowId, escrow.platformFee, owner());
        }
        
        emit EscrowReleased(_escrowId, escrow.beneficiary, escrow.amount, _reason);
    }
    
    // View functions
    
    /**
     * @dev Gets escrow account details
     * @param _escrowId ID of the escrow
     */
    function getEscrowAccount(uint256 _escrowId) 
        external 
        view 
        escrowExists(_escrowId) 
        returns (
            address depositor,
            address beneficiary,
            address arbiter,
            uint256 amount,
            uint256 releaseTime,
            EscrowType escrowType,
            ReleaseCondition releaseCondition,
            bool isReleased,
            bool isRefunded
        ) 
    {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        return (
            escrow.depositor,
            escrow.beneficiary,
            escrow.arbiter,
            escrow.amount,
            escrow.releaseTime,
            escrow.escrowType,
            escrow.releaseCondition,
            escrow.isReleased,
            escrow.isRefunded
        );
    }
    
    /**
     * @dev Gets conditional release details
     * @param _escrowId ID of the escrow
     */
    function getConditionalRelease(uint256 _escrowId) 
        external 
        view 
        returns (ConditionalRelease memory) 
    {
        return conditionalReleases[_escrowId];
    }
    
    /**
     * @dev Gets multi-signature release details
     * @param _escrowId ID of the escrow
     */
    function getMultiSigRelease(uint256 _escrowId) 
        external 
        view 
        returns (
            uint256 escrowId,
            uint256 signaturesRequired,
            uint256 currentSignatures,
            uint256 deadline,
            bool isExecuted
        ) 
    {
        MultiSigRelease storage multiSig = multiSigReleases[_escrowId];
        return (
            multiSig.escrowId,
            multiSig.signaturesRequired,
            multiSig.currentSignatures,
            multiSig.deadline,
            multiSig.isExecuted
        );
    }
    
    /**
     * @dev Gets time-lock release details
     * @param _escrowId ID of the escrow
     */
    function getTimeLockRelease(uint256 _escrowId) 
        external 
        view 
        returns (TimeLockRelease memory) 
    {
        return timeLockReleases[_escrowId];
    }
    
    /**
     * @dev Gets emergency release details
     * @param _escrowId ID of the escrow
     */
    function getEmergencyRelease(uint256 _escrowId) 
        external 
        view 
        returns (
            uint256 escrowId,
            address initiator,
            string memory reason,
            uint256 requestTime,
            uint256 votingDeadline,
            uint256 votesFor,
            uint256 votesAgainst,
            uint256 totalVotes,
            bool isApproved,
            bool isExecuted
        ) 
    {
        EmergencyRelease storage emergency = emergencyReleases[_escrowId];
        return (
            emergency.escrowId,
            emergency.initiator,
            emergency.reason,
            emergency.requestTime,
            emergency.votingDeadline,
            emergency.votesFor,
            emergency.votesAgainst,
            emergency.totalVotes,
            emergency.isApproved,
            emergency.isExecuted
        );
    }
    
    /**
     * @dev Gets all escrows for a depositor
     * @param _depositor Address of the depositor
     */
    function getDepositorEscrows(address _depositor) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return depositorEscrows[_depositor];
    }
    
    /**
     * @dev Gets all escrows for a beneficiary
     * @param _beneficiary Address of the beneficiary
     */
    function getBeneficiaryEscrows(address _beneficiary) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return beneficiaryEscrows[_beneficiary];
    }
    
    /**
     * @dev Gets active escrows
     */
    function getActiveEscrows() 
        external 
        view 
        returns (uint256[] memory) 
    {
        uint256[] memory active = new uint256[](activeEscrows.length);
        uint256 activeCount = 0;
        
        for (uint256 i = 0; i < activeEscrows.length; i++) {
            EscrowAccount storage escrow = escrowAccounts[activeEscrows[i]];
            if (!escrow.isReleased && !escrow.isRefunded) {
                active[activeCount] = activeEscrows[i];
                activeCount++;
            }
        }
        
        // Create correctly sized array and copy elements
        uint256[] memory result = new uint256[](activeCount);
        for (uint256 i = 0; i < activeCount; i++) {
            result[i] = active[i];
        }
        
        return result;
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
