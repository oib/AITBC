// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./PerformanceVerifier.sol";
import "./AIToken.sol";

/**
 * @title Agent Bounty System
 * @dev Automated bounty board for AI agent capabilities with ZK-proof verification
 * @notice Allows DAO and users to create bounties that are automatically completed when agents submit valid ZK-proofs
 */
contract AgentBounty is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    IERC20 public aitbcToken;
    PerformanceVerifier public performanceVerifier;
    
    uint256 public bountyCounter;
    uint256 public creationFeePercentage = 50; // 0.5% in basis points
    uint256 public successFeePercentage = 200; // 2% in basis points
    uint256 public disputeFeePercentage = 10; // 0.1% in basis points
    uint256 public platformFeePercentage = 100; // 1% in basis points
    
    // Bounty tiers
    enum BountyTier { BRONZE, SILVER, GOLD, PLATINUM }
    
    // Bounty status
    enum BountyStatus { CREATED, ACTIVE, SUBMITTED, VERIFIED, COMPLETED, EXPIRED, DISPUTED }
    
    // Submission status
    enum SubmissionStatus { PENDING, VERIFIED, REJECTED, DISPUTED }
    
    // Structs
    struct Bounty {
        uint256 bountyId;
        string title;
        string description;
        uint256 rewardAmount;
        address creator;
        BountyTier tier;
        BountyStatus status;
        bytes32 performanceCriteria; // Hash of performance requirements
        uint256 minAccuracy;
        uint256 deadline;
        uint256 creationTime;
        uint256 maxSubmissions;
        uint256 submissionCount;
        address winningSubmission;
        bool requiresZKProof;
        mapping(address => bool) authorizedSubmitters;
    }
    
    struct Submission {
        uint256 submissionId;
        uint256 bountyId;
        address submitter;
        bytes zkProof;
        bytes32 performanceHash;
        uint256 accuracy;
        uint256 responseTime;
        uint256 submissionTime;
        SubmissionStatus status;
        string disputeReason;
        address verifier;
    }
    
    struct BountyStats {
        uint256 totalBounties;
        uint256 activeBounties;
        uint256 completedBounties;
        uint256 totalValueLocked;
        uint256 averageReward;
        uint256 successRate;
    }
    
    // Mappings
    mapping(uint256 => Bounty) public bounties;
    mapping(uint256 => Submission) public submissions;
    mapping(uint256 => uint256[]) public bountySubmissions;
    mapping(address => uint256[]) public userSubmissions;
    mapping(address => uint256[]) public creatorBounties;
    mapping(BountyTier => uint256) public tierRequirements;
    mapping(uint256 => mapping(address => bool)) public hasSubmitted;
    
    // Arrays
    uint256[] public activeBountyIds;
    address[] public authorizedCreators;
    
    // Events
    event BountyCreated(
        uint256 indexed bountyId,
        string title,
        uint256 rewardAmount,
        address indexed creator,
        BountyTier tier,
        uint256 deadline
    );
    
    event BountySubmitted(
        uint256 indexed bountyId,
        uint256 indexed submissionId,
        address indexed submitter,
        bytes32 performanceHash,
        uint256 accuracy
    );
    
    event BountyVerified(
        uint256 indexed bountyId,
        uint256 indexed submissionId,
        address indexed submitter,
        bool success,
        uint256 rewardAmount
    );
    
    event BountyCompleted(
        uint256 indexed bountyId,
        address indexed winner,
        uint256 rewardAmount,
        uint256 completionTime
    );
    
    event BountyExpired(
        uint256 indexed bountyId,
        uint256 refundAmount
    );
    
    event BountyDisputed(
        uint256 indexed bountyId,
        uint256 indexed submissionId,
        address indexed disputer,
        string reason
    );
    
    event PlatformFeeCollected(
        uint256 indexed bountyId,
        uint256 feeAmount,
        address indexed collector
    );
    
    // Modifiers
    modifier bountyExists(uint256 _bountyId) {
        require(_bountyId < bountyCounter, "Bounty does not exist");
        _;
    }
    
    modifier onlyAuthorizedCreator() {
        require(isAuthorizedCreator(msg.sender), "Not authorized to create bounties");
        _;
    }
    
    modifier validBountyStatus(uint256 _bountyId, BountyStatus _requiredStatus) {
        require(bounties[_bountyId].status == _requiredStatus, "Invalid bounty status");
        _;
    }
    
    modifier beforeDeadline(uint256 _deadline) {
        require(block.timestamp <= _deadline, "Deadline passed");
        _;
    }
    
    modifier sufficientBalance(uint256 _amount) {
        require(aitbcToken.balanceOf(msg.sender) >= _amount, "Insufficient balance");
        _;
    }
    
    constructor(address _aitbcToken, address _performanceVerifier) {
        aitbcToken = IERC20(_aitbcToken);
        performanceVerifier = PerformanceVerifier(_performanceVerifier);
        
        // Set tier requirements (minimum reward amounts)
        tierRequirements[BountyTier.BRONZE] = 100 * 10**18;   // 100 AITBC
        tierRequirements[BountyTier.SILVER] = 500 * 10**18;   // 500 AITBC
        tierRequirements[BountyTier.GOLD] = 1000 * 10**18;   // 1000 AITBC
        tierRequirements[BountyTier.PLATINUM] = 5000 * 10**18; // 5000 AITBC
    }
    
    /**
     * @dev Creates a new bounty
     * @param _title Bounty title
     * @param _description Detailed description
     * @param _rewardAmount Reward amount in AITBC tokens
     * @param _tier Bounty tier
     * @param _performanceCriteria Hash of performance requirements
     * @param _minAccuracy Minimum accuracy required
     * @param _deadline Bounty deadline
     * @param _maxSubmissions Maximum number of submissions allowed
     * @param _requiresZKProof Whether ZK-proof is required
     */
    function createBounty(
        string memory _title,
        string memory _description,
        uint256 _rewardAmount,
        BountyTier _tier,
        bytes32 _performanceCriteria,
        uint256 _minAccuracy,
        uint256 _deadline,
        uint256 _maxSubmissions,
        bool _requiresZKProof
    ) external 
        onlyAuthorizedCreator
        sufficientBalance(_rewardAmount)
        beforeDeadline(_deadline)
        nonReentrant 
        returns (uint256) 
    {
        require(_rewardAmount >= tierRequirements[_tier], "Reward below tier minimum");
        require(_minAccuracy <= 100, "Invalid accuracy");
        require(_maxSubmissions > 0, "Invalid max submissions");
        require(_deadline > block.timestamp, "Invalid deadline");
        
        uint256 bountyId = bountyCounter++;
        
        Bounty storage bounty = bounties[bountyId];
        bounty.bountyId = bountyId;
        bounty.title = _title;
        bounty.description = _description;
        bounty.rewardAmount = _rewardAmount;
        bounty.creator = msg.sender;
        bounty.tier = _tier;
        bounty.status = BountyStatus.CREATED;
        bounty.performanceCriteria = _performanceCriteria;
        bounty.minAccuracy = _minAccuracy;
        bounty.deadline = _deadline;
        bounty.creationTime = block.timestamp;
        bounty.maxSubmissions = _maxSubmissions;
        bounty.submissionCount = 0;
        bounty.requiresZKProof = _requiresZKProof;
        
        // Calculate and collect creation fee
        uint256 creationFee = (_rewardAmount * creationFeePercentage) / 10000;
        uint256 totalRequired = _rewardAmount + creationFee;
        
        require(aitbcToken.balanceOf(msg.sender) >= totalRequired, "Insufficient total amount");
        
        // Transfer tokens to contract
        require(aitbcToken.transferFrom(msg.sender, address(this), totalRequired), "Transfer failed");
        
        // Transfer creation fee to DAO treasury (owner for now)
        if (creationFee > 0) {
            require(aitbcToken.transfer(owner(), creationFee), "Fee transfer failed");
            emit PlatformFeeCollected(bountyId, creationFee, owner());
        }
        
        // Update tracking arrays
        activeBountyIds.push(bountyId);
        creatorBounties[msg.sender].push(bountyId);
        
        // Activate bounty
        bounty.status = BountyStatus.ACTIVE;
        
        emit BountyCreated(bountyId, _title, _rewardAmount, msg.sender, _tier, _deadline);
        
        return bountyId;
    }
    
    /**
     * @dev Submits a solution to a bounty
     * @param _bountyId Bounty ID
     * @param _zkProof Zero-knowledge proof (if required)
     * @param _performanceHash Hash of performance metrics
     * @param _accuracy Achieved accuracy
     * @param _responseTime Response time in milliseconds
     */
    function submitBountySolution(
        uint256 _bountyId,
        bytes memory _zkProof,
        bytes32 _performanceHash,
        uint256 _accuracy,
        uint256 _responseTime
    ) external 
        bountyExists(_bountyId)
        validBountyStatus(_bountyId, BountyStatus.ACTIVE)
        beforeDeadline(bounties[_bountyId].deadline)
        nonReentrant 
        returns (uint256) 
    {
        Bounty storage bounty = bounties[_bountyId];
        
        require(!hasSubmitted[_bountyId][msg.sender], "Already submitted");
        require(bounty.submissionCount < bounty.maxSubmissions, "Max submissions reached");
        
        if (bounty.requiresZKProof) {
            require(_zkProof.length > 0, "ZK-proof required");
        }
        
        uint256 submissionId = bounty.submissionCount; // Use count as ID
        
        Submission storage submission = submissions[submissionId];
        submission.submissionId = submissionId;
        submission.bountyId = _bountyId;
        submission.submitter = msg.sender;
        submission.zkProof = _zkProof;
        submission.performanceHash = _performanceHash;
        submission.accuracy = _accuracy;
        submission.responseTime = _responseTime;
        submission.submissionTime = block.timestamp;
        submission.status = SubmissionStatus.PENDING;
        
        // Update tracking
        bounty.submissionCount++;
        hasSubmitted[_bountyId][msg.sender] = true;
        bountySubmissions[_bountyId].push(submissionId);
        userSubmissions[msg.sender].push(submissionId);
        
        // Auto-verify if ZK-proof is provided
        if (_zkProof.length > 0) {
            _verifySubmission(_bountyId, submissionId);
        }
        
        emit BountySubmitted(_bountyId, submissionId, msg.sender, _performanceHash, _accuracy);
        
        return submissionId;
    }
    
    /**
     * @dev Manually verifies a submission (oracle or automated)
     * @param _bountyId Bounty ID
     * @param _submissionId Submission ID
     * @param _verified Whether the submission is verified
     * @param _verifier Address of the verifier
     */
    function verifySubmission(
        uint256 _bountyId,
        uint256 _submissionId,
        bool _verified,
        address _verifier
    ) external 
        bountyExists(_bountyId)
        nonReentrant 
    {
        Bounty storage bounty = bounties[_bountyId];
        Submission storage submission = submissions[_submissionId];
        
        require(submission.status == SubmissionStatus.PENDING, "Submission not pending");
        require(submission.bountyId == _bountyId, "Submission bounty mismatch");
        
        submission.status = _verified ? SubmissionStatus.VERIFIED : SubmissionStatus.REJECTED;
        submission.verifier = _verifier;
        
        if (_verified) {
            // Check if this meets the bounty requirements
            if (submission.accuracy >= bounty.minAccuracy) {
                _completeBounty(_bountyId, _submissionId);
            }
        }
        
        emit BountyVerified(_bountyId, _submissionId, submission.submitter, _verified, bounty.rewardAmount);
    }
    
    /**
     * @dev Disputes a submission
     * @param _bountyId Bounty ID
     * @param _submissionId Submission ID
     * @param _reason Reason for dispute
     */
    function disputeSubmission(
        uint256 _bountyId,
        uint256 _submissionId,
        string memory _reason
    ) external 
        bountyExists(_bountyId)
        nonReentrant 
    {
        Bounty storage bounty = bounties[_bountyId];
        Submission storage submission = submissions[_submissionId];
        
        require(submission.status == SubmissionStatus.VERIFIED, "Can only dispute verified submissions");
        require(block.timestamp - submission.submissionTime <= 86400, "Dispute window expired"); // 24 hours
        
        submission.status = SubmissionStatus.DISPUTED;
        submission.disputeReason = _reason;
        bounty.status = BountyStatus.DISPUTED;
        
        // Collect dispute fee
        uint256 disputeFee = (bounty.rewardAmount * disputeFeePercentage) / 10000;
        if (disputeFee > 0) {
            require(aitbcToken.transferFrom(msg.sender, address(this), disputeFee), "Dispute fee transfer failed");
        }
        
        emit BountyDisputed(_bountyId, _submissionId, msg.sender, _reason);
    }
    
    /**
     * @dev Resolves a dispute
     * @param _bountyId Bounty ID
     * @param _submissionId Submission ID
     * @param _upholdDispute Whether to uphold the dispute
     */
    function resolveDispute(
        uint256 _bountyId,
        uint256 _submissionId,
        bool _upholdDispute
    ) external onlyOwner bountyExists(_bountyId) nonReentrant {
        Bounty storage bounty = bounties[_bountyId];
        Submission storage submission = submissions[_submissionId];
        
        require(bounty.status == BountyStatus.DISPUTED, "No dispute to resolve");
        require(submission.status == SubmissionStatus.DISPUTED, "Submission not disputed");
        
        if (_upholdDispute) {
            // Reject the submission
            submission.status = SubmissionStatus.REJECTED;
            bounty.status = BountyStatus.ACTIVE;
            
            // Return dispute fee
            uint256 disputeFee = (bounty.rewardAmount * disputeFeePercentage) / 10000;
            if (disputeFee > 0) {
                require(aitbcToken.transfer(msg.sender, disputeFee), "Dispute fee return failed");
            }
        } else {
            // Uphold the submission
            submission.status = SubmissionStatus.VERIFIED;
            _completeBounty(_bountyId, _submissionId);
        }
    }
    
    /**
     * @dev Expires a bounty and returns funds to creator
     * @param _bountyId Bounty ID
     */
    function expireBounty(uint256 _bountyId) external bountyExists(_bountyId) nonReentrant {
        Bounty storage bounty = bounties[_bountyId];
        
        require(bounty.status == BountyStatus.ACTIVE, "Bounty not active");
        require(block.timestamp > bounty.deadline, "Deadline not passed");
        
        bounty.status = BountyStatus.EXPIRED;
        
        // Return funds to creator
        uint256 refundAmount = bounty.rewardAmount;
        require(aitbcToken.transfer(bounty.creator, refundAmount), "Refund transfer failed");
        
        // Remove from active bounties
        _removeFromActiveBounties(_bountyId);
        
        emit BountyExpired(_bountyId, refundAmount);
    }
    
    /**
     * @dev Authorizes a creator to create bounties
     * @param _creator Address to authorize
     */
    function authorizeCreator(address _creator) external onlyOwner {
        require(_creator != address(0), "Invalid address");
        require(!isAuthorizedCreator(_creator), "Already authorized");
        
        authorizedCreators.push(_creator);
        bounties[0].authorizedSubmitters[_creator] = true; // Use bounty 0 as storage
    }
    
    /**
     * @dev Revokes creator authorization
     * @param _creator Address to revoke
     */
    function revokeCreator(address _creator) external onlyOwner {
        require(isAuthorizedCreator(_creator), "Not authorized");
        
        bounties[0].authorizedSubmitters[_creator] = false; // Use bounty 0 as storage
        
        // Remove from array
        for (uint256 i = 0; i < authorizedCreators.length; i++) {
            if (authorizedCreators[i] == _creator) {
                authorizedCreators[i] = authorizedCreators[authorizedCreators.length - 1];
                authorizedCreators.pop();
                break;
            }
        }
    }
    
    /**
     * @dev Updates fee percentages
     * @param _creationFee New creation fee percentage
     * @param _successFee New success fee percentage
     * @param _platformFee New platform fee percentage
     */
    function updateFees(
        uint256 _creationFee,
        uint256 _successFee,
        uint256 _platformFee
    ) external onlyOwner {
        require(_creationFee <= 500, "Creation fee too high"); // Max 5%
        require(_successFee <= 500, "Success fee too high"); // Max 5%
        require(_platformFee <= 500, "Platform fee too high"); // Max 5%
        
        creationFeePercentage = _creationFee;
        successFeePercentage = _successFee;
        platformFeePercentage = _platformFee;
    }
    
    /**
     * @dev Updates tier requirements
     * @param _tier Bounty tier
     * @param _minimumReward New minimum reward
     */
    function updateTierRequirement(BountyTier _tier, uint256 _minimumReward) external onlyOwner {
        tierRequirements[_tier] = _minimumReward;
    }
    
    // View functions
    
    /**
     * @dev Gets bounty details
     * @param _bountyId Bounty ID
     */
    function getBounty(uint256 _bountyId) external view bountyExists(_bountyId) returns (
        string memory title,
        string memory description,
        uint256 rewardAmount,
        address creator,
        BountyTier tier,
        BountyStatus status,
        bytes32 performanceCriteria,
        uint256 minAccuracy,
        uint256 deadline,
        uint256 creationTime,
        uint256 maxSubmissions,
        uint256 submissionCount,
        bool requiresZKProof
    ) {
        Bounty storage bounty = bounties[_bountyId];
        return (
            bounty.title,
            bounty.description,
            bounty.rewardAmount,
            bounty.creator,
            bounty.tier,
            bounty.status,
            bounty.performanceCriteria,
            bounty.minAccuracy,
            bounty.deadline,
            bounty.creationTime,
            bounty.maxSubmissions,
            bounty.submissionCount,
            bounty.requiresZKProof
        );
    }
    
    /**
     * @dev Gets submission details
     * @param _submissionId Submission ID
     */
    function getSubmission(uint256 _submissionId) external view returns (
        uint256 bountyId,
        address submitter,
        bytes32 performanceHash,
        uint256 accuracy,
        uint256 responseTime,
        uint256 submissionTime,
        SubmissionStatus status,
        address verifier
    ) {
        Submission storage submission = submissions[_submissionId];
        return (
            submission.bountyId,
            submission.submitter,
            submission.performanceHash,
            submission.accuracy,
            submission.responseTime,
            submission.submissionTime,
            submission.status,
            submission.verifier
        );
    }
    
    /**
     * @dev Gets all submissions for a bounty
     * @param _bountyId Bounty ID
     */
    function getBountySubmissions(uint256 _bountyId) external view bountyExists(_bountyId) returns (uint256[] memory) {
        return bountySubmissions[_bountyId];
    }
    
    /**
     * @dev Gets all bounties created by a user
     * @param _creator Creator address
     */
    function getCreatorBounties(address _creator) external view returns (uint256[] memory) {
        return creatorBounties[_creator];
    }
    
    /**
     * @dev Gets all submissions by a user
     * @param _submitter Submitter address
     */
    function getUserSubmissions(address _submitter) external view returns (uint256[] memory) {
        return userSubmissions[_submitter];
    }
    
    /**
     * @dev Gets all active bounty IDs
     */
    function getActiveBounties() external view returns (uint256[] memory) {
        return activeBountyIds;
    }
    
    /**
     * @dev Gets bounty statistics
     */
    function getBountyStats() external view returns (BountyStats memory) {
        uint256 totalValue = 0;
        uint256 activeCount = 0;
        uint256 completedCount = 0;
        
        for (uint256 i = 0; i < bountyCounter; i++) {
            if (bounties[i].status == BountyStatus.ACTIVE) {
                activeCount++;
                totalValue += bounties[i].rewardAmount;
            } else if (bounties[i].status == BountyStatus.COMPLETED) {
                completedCount++;
                totalValue += bounties[i].rewardAmount;
            }
        }
        
        uint256 avgReward = bountyCounter > 0 ? totalValue / bountyCounter : 0;
        uint256 successRate = completedCount > 0 ? (completedCount * 100) / bountyCounter : 0;
        
        return BountyStats({
            totalBounties: bountyCounter,
            activeBounties: activeCount,
            completedBounties: completedCount,
            totalValueLocked: totalValue,
            averageReward: avgReward,
            successRate: successRate
        });
    }
    
    /**
     * @dev Checks if an address is authorized to create bounties
     * @param _creator Address to check
     */
    function isAuthorizedCreator(address _creator) public view returns (bool) {
        return bounties[0].authorizedSubmitters[_creator]; // Use bounty 0 as storage
    }
    
    // Internal functions
    
    function _verifySubmission(uint256 _bountyId, uint256 _submissionId) internal {
        Bounty storage bounty = bounties[_bountyId];
        Submission storage submission = submissions[_submissionId];
        
        // Verify ZK-proof using PerformanceVerifier
        bool proofValid = performanceVerifier.verifyPerformanceProof(
            0, // Use dummy agreement ID for bounty verification
            submission.responseTime,
            submission.accuracy,
            95, // Default availability
            100, // Default compute power
            submission.zkProof
        );
        
        if (proofValid && submission.accuracy >= bounty.minAccuracy) {
            submission.status = SubmissionStatus.VERIFIED;
            _completeBounty(_bountyId, _submissionId);
        } else {
            submission.status = SubmissionStatus.REJECTED;
        }
    }
    
    function _completeBounty(uint256 _bountyId, uint256 _submissionId) internal {
        Bounty storage bounty = bounties[_bountyId];
        Submission storage submission = submissions[_submissionId];
        
        require(bounty.status == BountyStatus.ACTIVE || bounty.status == BountyStatus.SUBMITTED, "Bounty not active");
        
        bounty.status = BountyStatus.COMPLETED;
        bounty.winningSubmission = submission.submitter;
        
        // Calculate fees
        uint256 successFee = (bounty.rewardAmount * successFeePercentage) / 10000;
        uint256 platformFee = (bounty.rewardAmount * platformFeePercentage) / 10000;
        uint256 totalFees = successFee + platformFee;
        uint256 winnerReward = bounty.rewardAmount - totalFees;
        
        // Transfer reward to winner
        if (winnerReward > 0) {
            require(aitbcToken.transfer(submission.submitter, winnerReward), "Reward transfer failed");
        }
        
        // Transfer fees to treasury
        if (totalFees > 0) {
            require(aitbcToken.transfer(owner(), totalFees), "Fee transfer failed");
            emit PlatformFeeCollected(_bountyId, totalFees, owner());
        }
        
        // Remove from active bounties
        _removeFromActiveBounties(_bountyId);
        
        emit BountyCompleted(_bountyId, submission.submitter, winnerReward, block.timestamp);
    }
    
    function _removeFromActiveBounties(uint256 _bountyId) internal {
        for (uint256 i = 0; i < activeBountyIds.length; i++) {
            if (activeBountyIds[i] == _bountyId) {
                activeBountyIds[i] = activeBountyIds[activeBountyIds.length - 1];
                activeBountyIds.pop();
                break;
            }
        }
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
