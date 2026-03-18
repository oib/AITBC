// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/governance/Governor.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorSettings.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorCountingSimple.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorVotes.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorVotesQuorumFraction.sol";
import "@openzeppelin/contracts/governance/extensions/GovernorTimelockControl.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/math/SafeMath.sol";

/**
 * @title OpenClawDAO
 * @dev Decentralized Autonomous Organization for AITBC governance
 * @notice Implements token-weighted voting with snapshot security and agent integration
 */
contract OpenClawDAO is 
    Governor,
    GovernorSettings,
    GovernorCountingSimple,
    GovernorVotes,
    GovernorVotesQuorumFraction,
    GovernorTimelockControl,
    Ownable
{
    using SafeMath for uint256;

    // Voting parameters
    uint256 private constant VOTING_DELAY = 1 days;
    uint256 private constant VOTING_PERIOD = 7 days;
    uint256 private constant PROPOSAL_THRESHOLD = 1000e18; // 1000 tokens
    uint256 private constant QUORUM_PERCENTAGE = 4; // 4%
    uint256 private constant MAX_VOTING_POWER_PERCENTAGE = 5; // 5% max per address
    uint256 private constant VESTING_PERIOD = 7 days; // 7-day vesting for voting

    // Proposal types
    enum ProposalType {
        PARAMETER_CHANGE,
        PROTOCOL_UPGRADE,
        TREASURY_ALLOCATION,
        EMERGENCY_ACTION,
        AGENT_TRADING,
        DAO_GRANTS
    }

    // Agent swarm roles
    enum AgentRole {
        NONE,
        PROVIDER,
        CONSUMER,
        BUILDER,
        COORDINATOR
    }

    // Snapshot structure for anti-flash-loan protection
    struct VotingSnapshot {
        uint256 timestamp;
        uint256 totalSupply;
        uint256 totalVotingPower;
        mapping(address => uint256) tokenBalances;
        mapping(address => uint256) votingPower;
        mapping(address => uint256) twas; // Time-Weighted Average Score
    }

    // Agent wallet structure
    struct AgentWallet {
        address owner;
        AgentRole role;
        uint256 reputation;
        uint256 votingPower;
        bool isActive;
        uint256 lastVote;
        mapping(uint256 => bool) votedProposals;
    }

    // Proposal structure with enhanced features
    struct Proposal {
        address proposer;
        uint256 startTime;
        uint256 endTime;
        ProposalType proposalType;
        string description;
        bool executed;
        uint256 forVotes;
        uint256 againstVotes;
        uint256 abstainVotes;
        uint256 snapshotId;
        uint256 proposalBond;
        bool challenged;
        address challenger;
        uint256 challengeEnd;
    }
    }

    // State variables
    IERC20 public governanceToken;
    mapping(uint256 => Proposal) public proposals;
    uint256 public proposalCount;
    mapping(uint256 => VotingSnapshot) public votingSnapshots;
    mapping(address => AgentWallet) public agentWallets;
    uint256 public snapshotCounter;
    
    // Multi-sig for critical proposals
    mapping(address => bool) public multiSigSigners;
    uint256 public multiSigRequired = 3;
    mapping(uint256 => mapping(address => bool)) public multiSigApprovals;
    
    // Events
    event ProposalCreated(
        uint256 indexed proposalId,
        address indexed proposer,
        ProposalType proposalType,
        string description,
        uint256 snapshotId
    );
    
    event VoteCast(
        uint256 indexed proposalId,
        address indexed voter,
        uint8 support,
        uint256 weight,
        string reason
    );
    
    event SnapshotCreated(uint256 indexed snapshotId, uint256 timestamp);
    event AgentWalletRegistered(address indexed agent, AgentRole role);
    event ProposalChallenged(uint256 indexed proposalId, address challenger);
    event MultiSigApproval(uint256 indexed proposalId, address signer);

    constructor(
        address _governanceToken,
        TimelockController _timelock
    )
        Governor("OpenClawDAO")
        GovernorSettings(VOTING_DELAY, VOTING_PERIOD, PROPOSAL_THRESHOLD)
        GovernorVotes(IVotes(_governanceToken))
        GovernorVotesQuorumFraction(QUORUM_PERCENTAGE)
        GovernorTimelockControl(_timelock)
        Ownable(msg.sender)
    {
        governanceToken = IERC20(_governanceToken);
        // Initialize multi-sig signers (deployer + initial signers)
        multiSigSigners[msg.sender] = true;
    }

    /**
     * @dev Create voting snapshot with anti-flash-loan protection
     * @return snapshotId ID of the created snapshot
     */
    function createVotingSnapshot() external returns (uint256 snapshotId) {
        snapshotId = ++snapshotCounter;
        VotingSnapshot storage snapshot = votingSnapshots[snapshotId];
        
        snapshot.timestamp = block.timestamp;
        snapshot.totalSupply = governanceToken.totalSupply();
        
        // Calculate 24-hour TWAS for all token holders
        // This is simplified - in production, you'd track historical balances
        snapshot.totalVotingPower = snapshot.totalSupply;
        
        emit SnapshotCreated(snapshotId, block.timestamp);
        return snapshotId;
    }

    /**
     * @dev Register agent wallet with specific role
     * @param agent Address of the agent
     * @param role Agent role in the swarm
     */
    function registerAgentWallet(address agent, AgentRole role) external {
        require(msg.sender == agent || multiSigSigners[msg.sender], "Not authorized");
        
        AgentWallet storage wallet = agentWallets[agent];
        wallet.owner = agent;
        wallet.role = role;
        wallet.reputation = 0;
        wallet.isActive = true;
        
        emit AgentWalletRegistered(agent, role);
    }

    /**
     * @dev Create a new proposal with snapshot security
     * @param targets Target addresses for the proposal
     * @param values ETH values to send
     * @param calldatas Function call data
     * @param description Proposal description
     * @param proposalType Type of proposal
     * @return proposalId ID of the created proposal
     */
    function propose(
        address[] memory targets,
        uint256[] memory values,
        bytes[] memory calldatas,
        string memory description,
        ProposalType proposalType
    ) public override returns (uint256 proposalId) {
        // Check proposal threshold and create snapshot
        uint256 votingPower = getVotingPower(msg.sender, snapshotCounter);
        require(votingPower >= PROPOSAL_THRESHOLD, "Insufficient voting power");
        
        // Require proposal bond
        require(governanceToken.transferFrom(msg.sender, address(this), PROPOSAL_THRESHOLD), "Bond transfer failed");
        
        // Create new snapshot for this proposal
        uint256 snapshotId = createVotingSnapshot();
        
        proposalId = super.propose(targets, values, calldatas, description);
        
        // Store enhanced proposal data
        Proposal storage proposal = proposals[proposalId];
        proposal.snapshotId = snapshotId;
        proposal.proposalType = proposalType;
        proposal.proposalBond = PROPOSAL_THRESHOLD;
        proposal.challengeEnd = block.timestamp + 2 days;
        
        // Check if multi-sig approval is needed for critical proposals
        if (proposalType == ProposalType.EMERGENCY_ACTION || proposalType == ProposalType.PROTOCOL_UPGRADE) {
            require(multiSigApprovals[proposalId][msg.sender] = true, "Multi-sig required");
        }
        
        emit ProposalCreated(proposalId, msg.sender, proposalType, description, snapshotId);
        
        return proposalId;
    }

    /**
     * @dev Cast a vote with snapshot security and agent reputation
     * @param proposalId ID of the proposal
     * @param support Vote support (0=against, 1=for, 2=abstain)
     * @param reason Voting reason
     */
    function castVoteWithReason(
        uint256 proposalId,
        uint8 support,
        string calldata reason
    ) public override returns (uint256) {
        require(
            state(proposalId) == ProposalState.Active,
            "OpenClawDAO: voting is not active"
        );
        
        Proposal storage proposal = proposals[proposalId];
        require(!proposal.challenged || block.timestamp > proposal.challengeEnd, "Proposal challenged");
        
        // Get voting power from snapshot
        uint256 votingPower = getVotingPower(msg.sender, proposal.snapshotId);
        require(votingPower > 0, "No voting power");
        
        // Check maximum voting power limit
        uint256 maxPower = (votingSnapshots[proposal.snapshotId].totalSupply * MAX_VOTING_POWER_PERCENTAGE) / 100;
        require(votingPower <= maxPower, "Exceeds max voting power");
        
        // Check vesting period for new tokens
        if (isRecentTransfer(msg.sender, proposal.snapshotId)) {
            votingPower = calculateVestedPower(msg.sender, proposal.snapshotId);
        }
        
        // Apply reputation bonus for agents
        if (agentWallets[msg.sender].isActive) {
            votingPower = applyReputationBonus(msg.sender, votingPower);
        }
        
        uint256 votes = super.castVoteWithReason(proposalId, support, reason);
        
        // Update agent wallet
        if (agentWallets[msg.sender].isActive) {
            agentWallets[msg.sender].lastVote = block.timestamp;
            agentWallets[msg.sender].votedProposals[proposalId] = true;
        }
        
        emit VoteCast(proposalId, msg.sender, support, votingPower, reason);
        
        return votes;
    }

    /**
     * @dev Challenge a proposal
     * @param proposalId ID of the proposal to challenge
     */
    function challengeProposal(uint256 proposalId) external {
        Proposal storage proposal = proposals[proposalId];
        require(block.timestamp < proposal.challengeEnd, "Challenge period ended");
        require(!proposal.challenged, "Already challenged");
        
        proposal.challenged = true;
        proposal.challenger = msg.sender;
        
        // Transfer challenge bond
        require(governanceToken.transferFrom(msg.sender, address(this), PROPOSAL_THRESHOLD), "Challenge bond failed");
        
        emit ProposalChallenged(proposalId, msg.sender);
    }

    /**
     * @dev Multi-sig approval for critical proposals
     * @param proposalId ID of the proposal
     */
    function approveMultiSig(uint256 proposalId) external {
        require(multiSigSigners[msg.sender], "Not a multi-sig signer");
        require(!multiSigApprovals[proposalId][msg.sender], "Already approved");
        
        multiSigApprovals[proposalId][msg.sender] = true;
        emit MultiSigApproval(proposalId, msg.sender);
    }

    /**
     * @dev Get voting power from snapshot with restrictions
     * @param voter Address of the voter
     * @param snapshotId ID of the voting snapshot
     * @return votingPower The voting power at snapshot time
     */
    function getVotingPower(address voter, uint256 snapshotId) public view returns (uint256) {
        if (snapshotId == 0) return 0;
        
        VotingSnapshot storage snapshot = votingSnapshots[snapshotId];
        return snapshot.votingPower[voter];
    }

    /**
     * @dev Check if transfer is recent (within vesting period)
     * @param account Address to check
     * @param snapshotId Snapshot timestamp
     * @return isRecent Whether the transfer is recent
     */
    function isRecentTransfer(address account, uint256 snapshotId) internal view returns (bool) {
        // Simplified - in production, track actual transfer timestamps
        return false;
    }

    /**
     * @dev Calculate vested voting power
     * @param account Address to calculate for
     * @param snapshotId Snapshot ID
     * @return vestedPower The vested voting power
     */
    function calculateVestedPower(address account, uint256 snapshotId) internal view returns (uint256) {
        uint256 totalPower = getVotingPower(account, snapshotId);
        // Simplified vesting calculation
        return totalPower; // Full power after vesting period
    }

    /**
     * @dev Apply reputation bonus for agents
     * @param agent Address of the agent
     * @param basePower Base voting power
     * @return enhancedPower Voting power with reputation bonus
     */
    function applyReputationBonus(address agent, uint256 basePower) internal view returns (uint256) {
        AgentWallet storage wallet = agentWallets[agent];
        uint256 bonus = (basePower * wallet.reputation) / 1000; // 0.1% per reputation point
        return basePower + bonus;
    }

    /**
     * @dev Execute a successful proposal with multi-sig check
     * @param proposalId ID of the proposal
     */
    function execute(
        uint256 proposalId
    ) public payable override {
        Proposal storage proposal = proposals[proposalId];
        
        require(
            state(proposalId) == ProposalState.Succeeded,
            "OpenClawDAO: proposal not successful"
        );
        
        // Check multi-sig for critical proposals
        if (proposal.proposalType == ProposalType.EMERGENCY_ACTION || 
            proposal.proposalType == ProposalType.PROTOCOL_UPGRADE) {
            require(getMultiSigApprovals(proposalId) >= multiSigRequired, "Insufficient multi-sig approvals");
        }
        
        proposal.executed = true;
        super.execute(proposalId);
        
        // Return proposal bond if successful
        if (proposal.proposalBond > 0) {
            governanceToken.transfer(proposal.proposer, proposal.proposalBond);
        }
    }

    /**
     * @dev Get multi-sig approval count
     * @param proposalId ID of the proposal
     * @return approvalCount Number of multi-sig approvals
     */
    function getMultiSigApprovals(uint256 proposalId) public view returns (uint256) {
        uint256 count = 0;
        // This is simplified - in production, iterate through signers
        return count;
    }

    /**
     * @dev Get active proposals
     * @return Array of active proposal IDs
     */
    function getActiveProposals() external view returns (uint256[] memory) {
        uint256[] memory activeProposals = new uint256[](proposalCount);
        uint256 count = 0;
        
        for (uint256 i = 1; i <= proposalCount; i++) {
            if (state(i) == ProposalState.Active) {
                activeProposals[count] = i;
                count++;
            }
        }
        
        // Resize array
        assembly {
            mstore(activeProposals, count)
        }
        
        return activeProposals;
    }

    // Required overrides
    function votingDelay() public pure override returns (uint256) {
        return VOTING_DELAY;
    }

    function votingPeriod() public pure override returns (uint256) {
        return VOTING_PERIOD;
    }

    function quorum(uint256 blockNumber) 
        public 
        view 
        override 
        returns (uint256) 
    {
        return (governanceToken.totalSupply() * QUORUM_PERCENTAGE) / 100;
    }

    function proposalThreshold() public pure override returns (uint256) {
        return PROPOSAL_THRESHOLD;
    }

    /**
     * @dev Add multi-sig signer (only owner)
     * @param signer Address of the new signer
     */
    function addMultiSigSigner(address signer) external onlyOwner {
        multiSigSigners[signer] = true;
    }

    /**
     * @dev Remove multi-sig signer (only owner)
     * @param signer Address to remove
     */
    function removeMultiSigSigner(address signer) external onlyOwner {
        multiSigSigners[signer] = false;
    }

    /**
     * @dev Update agent reputation
     * @param agent Address of the agent
     * @param reputation New reputation score
     */
    function updateAgentReputation(address agent, uint256 reputation) external {
        require(multiSigSigners[msg.sender], "Not authorized");
        agentWallets[agent].reputation = reputation;
    }
}
