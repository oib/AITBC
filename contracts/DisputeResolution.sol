// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "./AIPowerRental.sol";
import "./AITBCPaymentProcessor.sol";
import "./PerformanceVerifier.sol";

/**
 * @title Dispute Resolution
 * @dev Advanced dispute resolution contract with automated arbitration and evidence verification
 * @notice Handles disputes between AI service providers and consumers with fair resolution mechanisms
 */
contract DisputeResolution is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    AIPowerRental public aiPowerRental;
    AITBCPaymentProcessor public paymentProcessor;
    PerformanceVerifier public performanceVerifier;
    
    uint256 public disputeCounter;
    uint256 public arbitrationFeePercentage = 100; // 1% in basis points
    uint256 public evidenceSubmissionPeriod = 3 days;
    uint256 public arbitrationPeriod = 7 days;
    uint256 public escalationThreshold = 3; // Number of disputes before escalation
    uint256 public minArbitrators = 3;
    uint256 public maxArbitrators = 5;
    
    // Structs
    struct Dispute {
        uint256 disputeId;
        uint256 agreementId;
        address initiator;
        address respondent;
        DisputeStatus status;
        DisputeType disputeType;
        string reason;
        bytes32 evidenceHash;
        uint256 filingTime;
        uint256 evidenceDeadline;
        uint256 arbitrationDeadline;
        uint256 resolutionAmount;
        address winner;
        string resolutionReason;
        uint256 arbitratorCount;
        bool isEscalated;
        uint256 escalationLevel;
    }
    
    struct Evidence {
        uint256 evidenceId;
        uint256 disputeId;
        address submitter;
        string evidenceType;
        string evidenceData;
        bytes32 evidenceHash;
        uint256 submissionTime;
        bool isValid;
        uint256 verificationScore;
        address verifiedBy;
    }
    
    struct Arbitrator {
        address arbitratorAddress;
        bool isAuthorized;
        uint256 reputationScore;
        uint256 totalDisputes;
        uint256 successfulResolutions;
        uint256 lastActiveTime;
        ArbitratorStatus status;
    }
    
    struct ArbitrationVote {
        uint256 disputeId;
        address arbitrator;
        bool voteInFavorOfInitiator;
        uint256 confidence;
        string reasoning;
        uint256 voteTime;
        bool isValid;
    }
    
    struct EscalationRecord {
        uint256 disputeId;
        uint256 escalationLevel;
        address escalatedBy;
        string escalationReason;
        uint256 escalationTime;
        address[] assignedArbitrators;
    }
    
    // Enums
    enum DisputeStatus {
        Filed,
        EvidenceSubmitted,
        UnderReview,
        ArbitrationInProgress,
        Resolved,
        Escalated,
        Rejected,
        Expired
    }
    
    enum DisputeType {
        Performance,
        Payment,
        ServiceQuality,
        Availability,
        Other
    }
    
    enum ArbitratorStatus {
        Active,
        Inactive,
        Suspended,
        Retired
    }
    
    enum EvidenceType {
        PerformanceMetrics,
        Logs,
        Screenshots,
        Videos,
        Documents,
        Testimonials,
        BlockchainProof,
        ZKProof
    }
    
    // Mappings
    mapping(uint256 => Dispute) public disputes;
    mapping(uint256 => Evidence[]) public disputeEvidence;
    mapping(uint256 => ArbitrationVote[]) public arbitrationVotes;
    mapping(uint256 => EscalationRecord) public escalations;
    mapping(address => Arbitrator) public arbitrators;
    mapping(address => uint256[]) public arbitratorDisputes;
    mapping(address => uint256[]) public userDisputes;
    mapping(uint256 => uint256) public agreementDisputes;
    mapping(address => bool) public authorizedArbitrators;
    mapping(uint256 => mapping(address => bool)) public hasVoted;
    
    // Arrays for tracking
    address[] public authorizedArbitratorList;
    uint256[] public activeDisputes;
    
    // Events
    event DisputeFiled(
        uint256 indexed disputeId,
        uint256 indexed agreementId,
        address indexed initiator,
        address respondent,
        DisputeType disputeType,
        string reason
    );
    
    event EvidenceSubmitted(
        uint256 indexed disputeId,
        uint256 indexed evidenceId,
        address indexed submitter,
        string evidenceType,
        bytes32 evidenceHash
    );
    
    event EvidenceVerified(
        uint256 indexed disputeId,
        uint256 indexed evidenceId,
        bool isValid,
        uint256 verificationScore
    );
    
    event ArbitratorAssigned(
        uint256 indexed disputeId,
        address indexed arbitrator,
        uint256 escalationLevel
    );
    
    event ArbitrationVoteSubmitted(
        uint256 indexed disputeId,
        address indexed arbitrator,
        bool voteInFavorOfInitiator,
        uint256 confidence
    );
    
    event DisputeResolved(
        uint256 indexed disputeId,
        address indexed winner,
        uint256 resolutionAmount,
        string resolutionReason
    );
    
    event DisputeEscalated(
        uint256 indexed disputeId,
        uint256 escalationLevel,
        address indexed escalatedBy,
        string escalationReason
    );
    
    event ArbitratorAuthorized(
        address indexed arbitrator,
        uint256 reputationScore
    );
    
    event ArbitratorRevoked(
        address indexed arbitrator,
        string reason
    );
    
    event ArbitrationFeeCollected(
        uint256 indexed disputeId,
        uint256 feeAmount,
        address indexed collector
    );
    
    // Modifiers
    modifier onlyAuthorizedArbitrator() {
        require(authorizedArbitrators[msg.sender], "Not authorized arbitrator");
        _;
    }
    
    modifier disputeExists(uint256 _disputeId) {
        require(_disputeId < disputeCounter, "Dispute does not exist");
        _;
    }
    
    modifier validStatus(uint256 _disputeId, DisputeStatus _requiredStatus) {
        require(disputes[_disputeId].status == _requiredStatus, "Invalid dispute status");
        _;
    }
    
    modifier onlyParticipant(uint256 _disputeId) {
        require(
            msg.sender == disputes[_disputeId].initiator ||
            msg.sender == disputes[_disputeId].respondent,
            "Not dispute participant"
        );
        _;
    }
    
    modifier withinDeadline(uint256 _deadline) {
        require(block.timestamp <= _deadline, "Deadline passed");
        _;
    }
    
    modifier hasNotVoted(uint256 _disputeId) {
        require(!hasVoted[_disputeId][msg.sender], "Already voted");
        _;
    }
    
    // Constructor
    constructor(
        address _aiPowerRental,
        address _paymentProcessor,
        address _performanceVerifier
    ) {
        aiPowerRental = AIPowerRental(_aiPowerRental);
        paymentProcessor = AITBCPaymentProcessor(_paymentProcessor);
        performanceVerifier = PerformanceVerifier(_performanceVerifier);
        disputeCounter = 0;
    }
    
    /**
     * @dev Files a new dispute
     * @param _agreementId ID of the agreement being disputed
     * @param _respondent The other party in the dispute
     * @param _disputeType Type of dispute
     * @param _reason Reason for the dispute
     * @param _evidenceHash Hash of initial evidence
     */
    function fileDispute(
        uint256 _agreementId,
        address _respondent,
        DisputeType _disputeType,
        string memory _reason,
        bytes32 _evidenceHash
    ) external nonReentrant whenNotPaused returns (uint256) {
        require(_respondent != address(0), "Invalid respondent");
        require(_respondent != msg.sender, "Cannot dispute yourself");
        require(bytes(_reason).length > 0, "Reason required");
        
        // Verify agreement exists and get participants
        (, address provider, address consumer, , , , , , , ) = aiPowerRental.getRentalAgreement(_agreementId);
        require(provider != address(0), "Invalid agreement");
        
        // Verify caller is a participant
        require(
            msg.sender == provider || msg.sender == consumer,
            "Not agreement participant"
        );
        
        // Verify respondent is the other participant
        address otherParticipant = msg.sender == provider ? consumer : provider;
        require(_respondent == otherParticipant, "Respondent not in agreement");
        
        uint256 disputeId = disputeCounter++;
        
        disputes[disputeId] = Dispute({
            disputeId: disputeId,
            agreementId: _agreementId,
            initiator: msg.sender,
            respondent: _respondent,
            status: DisputeStatus.Filed,
            disputeType: _disputeType,
            reason: _reason,
            evidenceHash: _evidenceHash,
            filingTime: block.timestamp,
            evidenceDeadline: block.timestamp + evidenceSubmissionPeriod,
            arbitrationDeadline: block.timestamp + evidenceSubmissionPeriod + arbitrationPeriod,
            resolutionAmount: 0,
            winner: address(0),
            resolutionReason: "",
            arbitratorCount: 0,
            isEscalated: false,
            escalationLevel: 1
        });
        
        userDisputes[msg.sender].push(disputeId);
        userDisputes[_respondent].push(disputeId);
        agreementDisputes[_agreementId] = disputeId;
        activeDisputes.push(disputeId);
        
        emit DisputeFiled(disputeId, _agreementId, msg.sender, _respondent, _disputeType, _reason);
        
        return disputeId;
    }
    
    /**
     * @dev Submits evidence for a dispute
     * @param _disputeId ID of the dispute
     * @param _evidenceType Type of evidence
     * @param _evidenceData Evidence data (can be IPFS hash, URL, etc.)
     */
    function submitEvidence(
        uint256 _disputeId,
        string memory _evidenceType,
        string memory _evidenceData
    ) external disputeExists(_disputeId) onlyParticipant(_disputeId) withinDeadline(disputes[_disputeId].evidenceDeadline) nonReentrant {
        Dispute storage dispute = disputes[_disputeId];
        
        require(dispute.status == DisputeStatus.Filed || dispute.status == DisputeStatus.EvidenceSubmitted, "Cannot submit evidence");
        
        uint256 evidenceId = disputeEvidence[_disputeId].length;
        bytes32 evidenceHash = keccak256(abi.encodePacked(_evidenceData, msg.sender, block.timestamp));
        
        disputeEvidence[_disputeId].push(Evidence({
            evidenceId: evidenceId,
            disputeId: _disputeId,
            submitter: msg.sender,
            evidenceType: _evidenceType,
            evidenceData: _evidenceData,
            evidenceHash: evidenceHash,
            submissionTime: block.timestamp,
            isValid: false,
            verificationScore: 0,
            verifiedBy: address(0)
        }));
        
        dispute.status = DisputeStatus.EvidenceSubmitted;
        
        emit EvidenceSubmitted(_disputeId, evidenceId, msg.sender, _evidenceType, evidenceHash);
    }
    
    /**
     * @dev Verifies evidence submitted in a dispute
     * @param _disputeId ID of the dispute
     * @param _evidenceId ID of the evidence
     * @param _isValid Whether the evidence is valid
     * @param _verificationScore Verification score (0-100)
     */
    function verifyEvidence(
        uint256 _disputeId,
        uint256 _evidenceId,
        bool _isValid,
        uint256 _verificationScore
    ) external onlyAuthorizedArbitrator disputeExists(_disputeId) nonReentrant {
        require(_evidenceId < disputeEvidence[_disputeId].length, "Invalid evidence ID");
        
        Evidence storage evidence = disputeEvidence[_disputeId][_evidenceId];
        evidence.isValid = _isValid;
        evidence.verificationScore = _verificationScore;
        evidence.verifiedBy = msg.sender;
        
        emit EvidenceVerified(_disputeId, _evidenceId, _isValid, _verificationScore);
    }
    
    /**
     * @dev Assigns arbitrators to a dispute
     * @param _disputeId ID of the dispute
     * @param _arbitrators Array of arbitrator addresses
     */
    function assignArbitrators(
        uint256 _disputeId,
        address[] memory _arbitrators
    ) external onlyOwner disputeExists(_disputeId) nonReentrant {
        Dispute storage dispute = disputes[_disputeId];
        
        require(_arbitrators.length >= minArbitrators && _arbitrators.length <= maxArbitrators, "Invalid arbitrator count");
        
        for (uint256 i = 0; i < _arbitrators.length; i++) {
            require(authorizedArbitrators[_arbitrators[i]], "Arbitrator not authorized");
            require(_arbitrators[i] != dispute.initiator && _arbitrators[i] != dispute.respondent, "Conflict of interest");
        }
        
        dispute.arbitratorCount = _arbitrators.length;
        dispute.status = DisputeStatus.ArbitrationInProgress;
        
        for (uint256 i = 0; i < _arbitrators.length; i++) {
            arbitratorDisputes[_arbitrators[i]].push(_disputeId);
            emit ArbitratorAssigned(_disputeId, _arbitrators[i], dispute.escalationLevel);
        }
    }
    
    /**
     * @dev Submits arbitration vote
     * @param _disputeId ID of the dispute
     * @param _voteInFavorOfInitiator Vote for initiator
     * @param _confidence Confidence level (0-100)
     * @param _reasoning Reasoning for the vote
     */
    function submitArbitrationVote(
        uint256 _disputeId,
        bool _voteInFavorOfInitiator,
        uint256 _confidence,
        string memory _reasoning
    ) external onlyAuthorizedArbitrator disputeExists(_disputeId) validStatus(_disputeId, DisputeStatus.ArbitrationInProgress) hasNotVoted(_disputeId) withinDeadline(disputes[_disputeId].arbitrationDeadline) nonReentrant {
        Dispute storage dispute = disputes[_disputeId];
        
        // Verify arbitrator is assigned to this dispute
        bool isAssigned = false;
        for (uint256 i = 0; i < arbitratorDisputes[msg.sender].length; i++) {
            if (arbitratorDisputes[msg.sender][i] == _disputeId) {
                isAssigned = true;
                break;
            }
        }
        require(isAssigned, "Arbitrator not assigned");
        
        arbitrationVotes[_disputeId].push(ArbitrationVote({
            disputeId: _disputeId,
            arbitrator: msg.sender,
            voteInFavorOfInitiator: _voteInFavorOfInitiator,
            confidence: _confidence,
            reasoning: _reasoning,
            voteTime: block.timestamp,
            isValid: true
        }));
        
        hasVoted[_disputeId][msg.sender] = true;
        
        // Update arbitrator stats
        Arbitrator storage arbitrator = arbitrators[msg.sender];
        arbitrator.totalDisputes++;
        arbitrator.lastActiveTime = block.timestamp;
        
        emit ArbitrationVoteSubmitted(_disputeId, msg.sender, _voteInFavorOfInitiator, _confidence);
        
        // Check if all arbitrators have voted
        if (arbitrationVotes[_disputeId].length == dispute.arbitratorCount) {
            _resolveDispute(_disputeId);
        }
    }
    
    /**
     * @dev Escalates a dispute to higher level
     * @param _disputeId ID of the dispute
     * @param _escalationReason Reason for escalation
     */
    function escalateDispute(
        uint256 _disputeId,
        string memory _escalationReason
    ) external onlyOwner disputeExists(_disputeId) nonReentrant {
        Dispute storage dispute = disputes[_disputeId];
        
        require(dispute.status == DisputeStatus.Resolved, "Cannot escalate unresolved dispute");
        require(dispute.escalationLevel < 3, "Max escalation level reached");
        
        dispute.escalationLevel++;
        dispute.isEscalated = true;
        dispute.status = DisputeStatus.Escalated;
        
        escalations[_disputeId] = EscalationRecord({
            disputeId: _disputeId,
            escalationLevel: dispute.escalationLevel,
            escalatedBy: msg.sender,
            escalationReason: _escalationReason,
            escalationTime: block.timestamp,
            assignedArbitrators: new address[](0)
        });
        
        emit DisputeEscalated(_disputeId, dispute.escalationLevel, msg.sender, _escalationReason);
    }
    
    /**
     * @dev Authorizes an arbitrator
     * @param _arbitrator Address of the arbitrator
     * @param _reputationScore Initial reputation score
     */
    function authorizeArbitrator(address _arbitrator, uint256 _reputationScore) external onlyOwner {
        require(_arbitrator != address(0), "Invalid arbitrator address");
        require(!authorizedArbitrators[_arbitrator], "Arbitrator already authorized");
        
        authorizedArbitrators[_arbitrator] = true;
        authorizedArbitratorList.push(_arbitrator);
        
        arbitrators[_arbitrator] = Arbitrator({
            arbitratorAddress: _arbitrator,
            isAuthorized: true,
            reputationScore: _reputationScore,
            totalDisputes: 0,
            successfulResolutions: 0,
            lastActiveTime: block.timestamp,
            status: ArbitratorStatus.Active
        });
        
        emit ArbitratorAuthorized(_arbitrator, _reputationScore);
    }
    
    /**
     * @dev Revokes arbitrator authorization
     * @param _arbitrator Address of the arbitrator
     * @param _reason Reason for revocation
     */
    function revokeArbitrator(address _arbitrator, string memory _reason) external onlyOwner {
        require(authorizedArbitrators[_arbitrator], "Arbitrator not authorized");
        
        authorizedArbitrators[_arbitrator] = false;
        arbitrators[_arbitrator].status = ArbitratorStatus.Suspended;
        
        emit ArbitratorRevoked(_arbitrator, _reason);
    }
    
    // Internal functions
    
    function _resolveDispute(uint256 _disputeId) internal {
        Dispute storage dispute = disputes[_disputeId];
        ArbitrationVote[] storage votes = arbitrationVotes[_disputeId];
        
        uint256 votesForInitiator = 0;
        uint256 votesForRespondent = 0;
        uint256 totalConfidence = 0;
        uint256 weightedVotesForInitiator = 0;
        
        // Calculate weighted votes
        for (uint256 i = 0; i < votes.length; i++) {
            ArbitrationVote storage vote = votes[i];
            totalConfidence += vote.confidence;
            
            if (vote.voteInFavorOfInitiator) {
                votesForInitiator++;
                weightedVotesForInitiator += vote.confidence;
            } else {
                votesForRespondent++;
            }
        }
        
        // Determine winner based on weighted votes
        bool initiatorWins = weightedVotesForInitiator > (totalConfidence / 2);
        
        dispute.winner = initiatorWins ? dispute.initiator : dispute.respondent;
        dispute.status = DisputeStatus.Resolved;
        
        // Calculate resolution amount based on agreement
        (, address provider, address consumer, uint256 duration, uint256 price, , , , , ) = aiPowerRental.getRentalAgreement(dispute.agreementId);
        
        if (initiatorWins) {
            dispute.resolutionAmount = price; // Full refund/compensation
        } else {
            dispute.resolutionAmount = 0; // No compensation
        }
        
        // Update arbitrator success rates
        for (uint256 i = 0; i < votes.length; i++) {
            ArbitrationVote storage vote = votes[i];
            Arbitrator storage arbitrator = arbitrators[vote.arbitrator];
            
            if ((vote.voteInFavorOfInitiator && initiatorWins) || (!vote.voteInFavorOfInitiator && !initiatorWins)) {
                arbitrator.successfulResolutions++;
            }
        }
        
        dispute.resolutionReason = initiatorWins ? "Evidence and reasoning support initiator" : "Evidence and reasoning support respondent";
        
        emit DisputeResolved(_disputeId, dispute.winner, dispute.resolutionAmount, dispute.resolutionReason);
    }
    
    // View functions
    
    /**
     * @dev Gets dispute details
     * @param _disputeId ID of the dispute
     */
    function getDispute(uint256 _disputeId) 
        external 
        view 
        disputeExists(_disputeId) 
        returns (Dispute memory) 
    {
        return disputes[_disputeId];
    }
    
    /**
     * @dev Gets evidence for a dispute
     * @param _disputeId ID of the dispute
     */
    function getDisputeEvidence(uint256 _disputeId) 
        external 
        view 
        disputeExists(_disputeId) 
        returns (Evidence[] memory) 
    {
        return disputeEvidence[_disputeId];
    }
    
    /**
     * @dev Gets arbitration votes for a dispute
     * @param _disputeId ID of the dispute
     */
    function getArbitrationVotes(uint256 _disputeId) 
        external 
        view 
        disputeExists(_disputeId) 
        returns (ArbitrationVote[] memory) 
    {
        return arbitrationVotes[_disputeId];
    }
    
    /**
     * @dev Gets arbitrator information
     * @param _arbitrator Address of the arbitrator
     */
    function getArbitrator(address _arbitrator) 
        external 
        view 
        returns (Arbitrator memory) 
    {
        return arbitrators[_arbitrator];
    }
    
    /**
     * @dev Gets all disputes for a user
     * @param _user Address of the user
     */
    function getUserDisputes(address _user) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return userDisputes[_user];
    }
    
    /**
     * @dev Gets all disputes for an arbitrator
     * @param _arbitrator Address of the arbitrator
     */
    function getArbitratorDisputes(address _arbitrator) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return arbitratorDisputes[_arbitrator];
    }
    
    /**
     * @dev Gets all authorized arbitrators
     */
    function getAuthorizedArbitrators() 
        external 
        view 
        returns (address[] memory) 
    {
        address[] memory activeArbitrators = new address[](authorizedArbitratorList.length);
        uint256 activeCount = 0;
        
        for (uint256 i = 0; i < authorizedArbitratorList.length; i++) {
            if (authorizedArbitrators[authorizedArbitratorList[i]]) {
                activeArbitrators[activeCount] = authorizedArbitratorList[i];
                activeCount++;
            }
        }
        
        // Resize array to active count
        assembly {
            mstore(activeArbitrators, activeCount)
        }
        
        return activeArbitrators;
    }
    
    /**
     * @dev Gets active disputes
     */
    function getActiveDisputes() 
        external 
        view 
        returns (uint256[] memory) 
    {
        uint256[] memory active = new uint256[](activeDisputes.length);
        uint256 activeCount = 0;
        
        for (uint256 i = 0; i < activeDisputes.length; i++) {
            if (disputes[activeDisputes[i]].status != DisputeStatus.Resolved && 
                disputes[activeDisputes[i]].status != DisputeStatus.Rejected) {
                active[activeCount] = activeDisputes[i];
                activeCount++;
            }
        }
        
        // Resize array to active count
        assembly {
            mstore(active, activeCount)
        }
        
        return active;
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
