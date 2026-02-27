// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "./AIPowerRental.sol";

/**
 * @title AITBC Payment Processor
 * @dev Advanced payment processing contract with escrow, automated releases, and dispute resolution
 * @notice Handles AITBC token payments for AI power rental services
 */
contract AITBCPaymentProcessor is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    IERC20 public aitbcToken;
    AIPowerRental public aiPowerRental;
    
    uint256 public paymentCounter;
    uint256 public platformFeePercentage = 250; // 2.5% in basis points
    uint256 public disputeResolutionFee = 100; // 1% in basis points
    uint256 public minPaymentAmount = 1e15; // 0.001 AITBC minimum
    uint256 public maxPaymentAmount = 1e22; // 10,000 AITBC maximum
    
    // Structs
    struct Payment {
        uint256 paymentId;
        address from;
        address to;
        uint256 amount;
        uint256 platformFee;
        uint256 disputeFee;
        PaymentStatus status;
        uint256 releaseTime;
        uint256 createdTime;
        uint256 confirmedTime;
        bytes32 agreementId;
        string paymentPurpose;
        ReleaseCondition releaseCondition;
        bytes32 conditionHash;
    }
    
    struct EscrowAccount {
        uint256 escrowId;
        address depositor;
        address beneficiary;
        uint256 amount;
        uint256 releaseTime;
        bool isReleased;
        bool isRefunded;
        bytes32 releaseCondition;
        uint256 createdTime;
        EscrowType escrowType;
    }
    
    struct ScheduledPayment {
        uint256 scheduleId;
        uint256 paymentId;
        uint256 nextReleaseTime;
        uint256 releaseInterval;
        uint256 totalReleases;
        uint256 releasedCount;
        bool isActive;
    }
    
    // Enums
    enum PaymentStatus {
        Created,
        Confirmed,
        HeldInEscrow,
        Released,
        Refunded,
        Disputed,
        Cancelled
    }
    
    enum EscrowType {
        Standard,
        PerformanceBased,
        TimeBased,
        Conditional
    }
    
    enum ReleaseCondition {
        Immediate,
        Manual,
        Performance,
        TimeBased,
        DisputeResolution
    }
    
    // Mappings
    mapping(uint256 => Payment) public payments;
    mapping(uint256 => EscrowAccount) public escrowAccounts;
    mapping(uint256 => ScheduledPayment) public scheduledPayments;
    mapping(address => uint256[]) public senderPayments;
    mapping(address => uint256[]) public recipientPayments;
    mapping(bytes32 => uint256) public agreementPayments;
    mapping(address => uint256) public userEscrowBalance;
    mapping(address => bool) public authorizedPayees;
    mapping(address => bool) public authorizedPayers;
    
    // Events
    event PaymentCreated(
        uint256 indexed paymentId,
        address indexed from,
        address indexed to,
        uint256 amount,
        bytes32 agreementId,
        string paymentPurpose
    );
    
    event PaymentConfirmed(
        uint256 indexed paymentId,
        uint256 confirmedTime,
        bytes32 transactionHash
    );
    
    event PaymentReleased(
        uint256 indexed paymentId,
        address indexed to,
        uint256 amount,
        uint256 platformFee
    );
    
    event PaymentRefunded(
        uint256 indexed paymentId,
        address indexed to,
        uint256 amount,
        string reason
    );
    
    event EscrowCreated(
        uint256 indexed escrowId,
        address indexed depositor,
        address indexed beneficiary,
        uint256 amount,
        EscrowType escrowType
    );
    
    event EscrowReleased(
        uint256 indexed escrowId,
        uint256 amount,
        bytes32 conditionHash
    );
    
    event EscrowRefunded(
        uint256 indexed escrowId,
        address indexed depositor,
        uint256 amount,
        string reason
    );
    
    event ScheduledPaymentCreated(
        uint256 indexed scheduleId,
        uint256 indexed paymentId,
        uint256 nextReleaseTime,
        uint256 releaseInterval
    );
    
    event ScheduledPaymentReleased(
        uint256 indexed scheduleId,
        uint256 indexed paymentId,
        uint256 releaseCount
    );
    
    event DisputeInitiated(
        uint256 indexed paymentId,
        address indexed initiator,
        string reason
    );
    
    event DisputeResolved(
        uint256 indexed paymentId,
        uint256 resolutionAmount,
        bool resolvedInFavorOfPayer
    );
    
    event PlatformFeeCollected(
        uint256 indexed paymentId,
        uint256 feeAmount,
        address indexed collector
    );
    
    // Modifiers
    modifier onlyAuthorizedPayer() {
        require(authorizedPayers[msg.sender], "Not authorized payer");
        _;
    }
    
    modifier onlyAuthorizedPayee() {
        require(authorizedPayees[msg.sender], "Not authorized payee");
        _;
    }
    
    modifier paymentExists(uint256 _paymentId) {
        require(_paymentId < paymentCounter, "Payment does not exist");
        _;
    }
    
    modifier validStatus(uint256 _paymentId, PaymentStatus _requiredStatus) {
        require(payments[_paymentId].status == _requiredStatus, "Invalid payment status");
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
    
    // Constructor
    constructor(address _aitbcToken, address _aiPowerRental) {
        aitbcToken = IERC20(_aitbcToken);
        aiPowerRental = AIPowerRental(_aiPowerRental);
        paymentCounter = 0;
    }
    
    /**
     * @dev Creates a new payment
     * @param _to Recipient address
     * @param _amount Payment amount
     * @param _agreementId Associated agreement ID
     * @param _paymentPurpose Purpose of the payment
     * @param _releaseCondition Release condition
     */
    function createPayment(
        address _to,
        uint256 _amount,
        bytes32 _agreementId,
        string memory _paymentPurpose,
        ReleaseCondition _releaseCondition
    ) external onlyAuthorizedPayer sufficientBalance(msg.sender, _amount) sufficientAllowance(msg.sender, _amount) nonReentrant whenNotPaused returns (uint256) {
        require(_amount >= minPaymentAmount, "Amount below minimum");
        require(_amount <= maxPaymentAmount, "Amount above maximum");
        require(_to != address(0), "Invalid recipient");
        require(authorizedPayees[_to], "Recipient not authorized");
        
        uint256 paymentId = paymentCounter++;
        
        // Calculate fees and create payment
        _createPaymentWithFees(paymentId, _to, _amount, _agreementId, _paymentPurpose, _releaseCondition);
        
        // Update tracking arrays
        _updatePaymentTracking(paymentId, _to, _agreementId);
        
        // Transfer tokens
        _transferTokensForPayment(_amount);
        
        emit PaymentCreated(paymentId, msg.sender, _to, _amount, _agreementId, _paymentPurpose);
        
        return paymentId;
    }
    
    function _createPaymentWithFees(
        uint256 _paymentId,
        address _to,
        uint256 _amount,
        bytes32 _agreementId,
        string memory _paymentPurpose,
        ReleaseCondition _releaseCondition
    ) internal {
        uint256 platformFee = (_amount * platformFeePercentage) / 10000;
        uint256 disputeFee = (_amount * disputeResolutionFee) / 10000;
        
        payments[_paymentId] = Payment({
            paymentId: _paymentId,
            from: msg.sender,
            to: _to,
            amount: _amount,
            platformFee: platformFee,
            disputeFee: disputeFee,
            status: PaymentStatus.Created,
            releaseTime: 0,
            createdTime: block.timestamp,
            confirmedTime: 0,
            agreementId: _agreementId,
            paymentPurpose: _paymentPurpose,
            releaseCondition: _releaseCondition,
            conditionHash: bytes32(0)
        });
    }
    
    function _updatePaymentTracking(uint256 _paymentId, address _to, bytes32 _agreementId) internal {
        senderPayments[msg.sender].push(_paymentId);
        recipientPayments[_to].push(_paymentId);
        
        if (_agreementId != bytes32(0)) {
            agreementPayments[_agreementId] = _paymentId;
        }
    }
    
    function _transferTokensForPayment(uint256 _amount) internal {
        uint256 platformFee = (_amount * platformFeePercentage) / 10000;
        uint256 disputeFee = (_amount * disputeResolutionFee) / 10000;
        uint256 totalAmount = _amount + platformFee + disputeFee;
        
        require(
            aitbcToken.transferFrom(msg.sender, address(this), totalAmount),
            "Payment transfer failed"
        );
    }
    
    /**
     * @dev Confirms a payment with transaction hash
     * @param _paymentId ID of the payment
     * @param _transactionHash Blockchain transaction hash
     */
    function confirmPayment(uint256 _paymentId, bytes32 _transactionHash) 
        external 
        paymentExists(_paymentId)
        validStatus(_paymentId, PaymentStatus.Created)
        nonReentrant 
    {
        Payment storage payment = payments[_paymentId];
        
        require(msg.sender == payment.from, "Only payer can confirm");
        
        payment.status = PaymentStatus.Confirmed;
        payment.confirmedTime = block.timestamp;
        payment.conditionHash = _transactionHash;
        
        // Handle immediate release
        if (payment.releaseCondition == ReleaseCondition.Immediate) {
            _releasePayment(_paymentId);
        } else if (payment.releaseCondition == ReleaseCondition.TimeBased) {
            payment.status = PaymentStatus.HeldInEscrow;
            payment.releaseTime = block.timestamp + 1 hours; // Default 1 hour hold
        } else {
            payment.status = PaymentStatus.HeldInEscrow;
        }
        
        emit PaymentConfirmed(_paymentId, block.timestamp, _transactionHash);
    }
    
    /**
     * @dev Releases a payment to the recipient
     * @param _paymentId ID of the payment
     */
    function releasePayment(uint256 _paymentId) 
        external 
        paymentExists(_paymentId)
        nonReentrant 
    {
        Payment storage payment = payments[_paymentId];
        
        require(
            payment.status == PaymentStatus.Confirmed || 
            payment.status == PaymentStatus.HeldInEscrow,
            "Payment not ready for release"
        );
        
        if (payment.releaseCondition == ReleaseCondition.Manual) {
            require(msg.sender == payment.from, "Only payer can release manually");
        } else if (payment.releaseCondition == ReleaseCondition.TimeBased) {
            require(block.timestamp >= payment.releaseTime, "Release time not reached");
        }
        
        _releasePayment(_paymentId);
    }
    
    /**
     * @dev Creates an escrow account
     * @param _beneficiary Beneficiary address
     * @param _amount Amount to lock in escrow
     * @param _releaseTime Release time (0 for no time limit)
     * @param _escrowType Type of escrow
     * @param _releaseCondition Release condition hash
     */
    function createEscrow(
        address _beneficiary,
        uint256 _amount,
        uint256 _releaseTime,
        EscrowType _escrowType,
        bytes32 _releaseCondition
    ) external onlyAuthorizedPayer sufficientBalance(msg.sender, _amount) sufficientAllowance(msg.sender, _amount) nonReentrant whenNotPaused returns (uint256) {
        require(_beneficiary != address(0), "Invalid beneficiary");
        require(_amount >= minPaymentAmount, "Amount below minimum");
        
        uint256 escrowId = paymentCounter++;
        
        escrowAccounts[escrowId] = EscrowAccount({
            escrowId: escrowId,
            depositor: msg.sender,
            beneficiary: _beneficiary,
            amount: _amount,
            releaseTime: _releaseTime,
            isReleased: false,
            isRefunded: false,
            releaseCondition: _releaseCondition,
            createdTime: block.timestamp,
            escrowType: _escrowType
        });
        
        // Transfer tokens to contract
        require(
            aitbcToken.transferFrom(msg.sender, address(this), _amount),
            "Escrow transfer failed"
        );
        
        userEscrowBalance[msg.sender] += _amount;
        
        emit EscrowCreated(escrowId, msg.sender, _beneficiary, _amount, _escrowType);
        
        return escrowId;
    }
    
    /**
     * @dev Releases escrow to beneficiary
     * @param _escrowId ID of the escrow account
     */
    function releaseEscrow(uint256 _escrowId) 
        external 
        nonReentrant 
    {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        
        require(!escrow.isReleased, "Escrow already released");
        require(!escrow.isRefunded, "Escrow already refunded");
        require(
            escrow.releaseTime == 0 || block.timestamp >= escrow.releaseTime,
            "Release time not reached"
        );
        
        escrow.isReleased = true;
        userEscrowBalance[escrow.depositor] -= escrow.amount;
        
        require(
            aitbcToken.transfer(escrow.beneficiary, escrow.amount),
            "Escrow release failed"
        );
        
        emit EscrowReleased(_escrowId, escrow.amount, escrow.releaseCondition);
    }
    
    /**
     * @dev Refunds escrow to depositor
     * @param _escrowId ID of the escrow account
     * @param _reason Reason for refund
     */
    function refundEscrow(uint256 _escrowId, string memory _reason) 
        external 
        nonReentrant 
    {
        EscrowAccount storage escrow = escrowAccounts[_escrowId];
        
        require(!escrow.isReleased, "Escrow already released");
        require(!escrow.isRefunded, "Escrow already refunded");
        require(
            msg.sender == escrow.depositor || msg.sender == owner(),
            "Only depositor or owner can refund"
        );
        
        escrow.isRefunded = true;
        userEscrowBalance[escrow.depositor] -= escrow.amount;
        
        require(
            aitbcToken.transfer(escrow.depositor, escrow.amount),
            "Escrow refund failed"
        );
        
        emit EscrowRefunded(_escrowId, escrow.depositor, escrow.amount, _reason);
    }
    
    /**
     * @dev Initiates a dispute for a payment
     * @param _paymentId ID of the payment
     * @param _reason Reason for dispute
     */
    function initiateDispute(uint256 _paymentId, string memory _reason) 
        external 
        paymentExists(_paymentId)
        nonReentrant 
    {
        Payment storage payment = payments[_paymentId];
        
        require(
            payment.status == PaymentStatus.Confirmed || 
            payment.status == PaymentStatus.HeldInEscrow,
            "Cannot dispute this payment"
        );
        
        require(
            msg.sender == payment.from || msg.sender == payment.to,
            "Only payment participants can dispute"
        );
        
        payment.status = PaymentStatus.Disputed;
        
        emit DisputeInitiated(_paymentId, msg.sender, _reason);
    }
    
    /**
     * @dev Resolves a dispute
     * @param _paymentId ID of the disputed payment
     * @param _resolutionAmount Amount to award to the winner
     * @param _resolveInFavorOfPayer True if resolving in favor of payer
     */
    function resolveDispute(
        uint256 _paymentId,
        uint256 _resolutionAmount,
        bool _resolveInFavorOfPayer
    ) external onlyOwner paymentExists(_paymentId) nonReentrant {
        Payment storage payment = payments[_paymentId];
        
        require(payment.status == PaymentStatus.Disputed, "Payment not disputed");
        require(_resolutionAmount <= payment.amount, "Resolution amount too high");
        
        address winner = _resolveInFavorOfPayer ? payment.from : payment.to;
        address loser = _resolveInFavorOfPayer ? payment.to : payment.from;
        
        // Calculate refund for loser
        uint256 refundAmount = payment.amount - _resolutionAmount;
        
        // Transfer resolution amount to winner
        if (_resolutionAmount > 0) {
            require(
                aitbcToken.transfer(winner, _resolutionAmount),
                "Resolution payment failed"
            );
        }
        
        // Refund remaining amount to loser
        if (refundAmount > 0) {
            require(
                aitbcToken.transfer(loser, refundAmount),
                "Refund payment failed"
            );
        }
        
        payment.status = PaymentStatus.Released;
        
        emit DisputeResolved(_paymentId, _resolutionAmount, _resolveInFavorOfPayer);
    }
    
    /**
     * @dev Claims platform fees
     * @param _paymentId ID of the payment
     */
    function claimPlatformFee(uint256 _paymentId) 
        external 
        onlyOwner 
        paymentExists(_paymentId)
        nonReentrant 
    {
        Payment storage payment = payments[_paymentId];
        
        require(payment.status == PaymentStatus.Released, "Payment not released");
        require(payment.platformFee > 0, "No platform fee to claim");
        
        uint256 feeAmount = payment.platformFee;
        payment.platformFee = 0;
        
        require(
            aitbcToken.transfer(owner(), feeAmount),
            "Platform fee transfer failed"
        );
        
        emit PlatformFeeCollected(_paymentId, feeAmount, owner());
    }
    
    /**
     * @dev Authorizes a payee
     * @param _payee Address to authorize
     */
    function authorizePayee(address _payee) external onlyOwner {
        authorizedPayees[_payee] = true;
    }
    
    /**
     * @dev Revokes payee authorization
     * @param _payee Address to revoke
     */
    function revokePayee(address _payee) external onlyOwner {
        authorizedPayees[_payee] = false;
    }
    
    /**
     * @dev Authorizes a payer
     * @param _payer Address to authorize
     */
    function authorizePayer(address _payer) external onlyOwner {
        authorizedPayers[_payer] = true;
    }
    
    /**
     * @dev Revokes payer authorization
     * @param _payer Address to revoke
     */
    function revokePayer(address _payer) external onlyOwner {
        authorizedPayers[_payer] = false;
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
    
    // Internal functions
    
    function _releasePayment(uint256 _paymentId) internal {
        Payment storage payment = payments[_paymentId];
        
        payment.status = PaymentStatus.Released;
        
        // Transfer amount to recipient
        require(
            aitbcToken.transfer(payment.to, payment.amount),
            "Payment transfer failed"
        );
        
        // Transfer platform fee to owner
        if (payment.platformFee > 0) {
            require(
                aitbcToken.transfer(owner(), payment.platformFee),
                "Platform fee transfer failed"
            );
        }
        
        emit PaymentReleased(_paymentId, payment.to, payment.amount, payment.platformFee);
    }
    
    // View functions
    
    /**
     * @dev Gets payment details
     * @param _paymentId ID of the payment
     */
    function getPayment(uint256 _paymentId) 
        external 
        view 
        paymentExists(_paymentId) 
        returns (Payment memory) 
    {
        return payments[_paymentId];
    }
    
    /**
     * @dev Gets escrow account details
     * @param _escrowId ID of the escrow account
     */
    function getEscrowAccount(uint256 _escrowId) 
        external 
        view 
        returns (EscrowAccount memory) 
    {
        return escrowAccounts[_escrowId];
    }
    
    /**
     * @dev Gets all payments for a sender
     * @param _sender Address of the sender
     */
    function getSenderPayments(address _sender) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return senderPayments[_sender];
    }
    
    /**
     * @dev Gets all payments for a recipient
     * @param _recipient Address of the recipient
     */
    function getRecipientPayments(address _recipient) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return recipientPayments[_recipient];
    }
    
    /**
     * @dev Gets payment associated with an agreement
     * @param _agreementId ID of the agreement
     */
    function getAgreementPayment(bytes32 _agreementId) 
        external 
        view 
        returns (uint256) 
    {
        return agreementPayments[_agreementId];
    }
    
    /**
     * @dev Gets user's escrow balance
     * @param _user Address of the user
     */
    function getUserEscrowBalance(address _user) 
        external 
        view 
        returns (uint256) 
    {
        return userEscrowBalance[_user];
    }
}
