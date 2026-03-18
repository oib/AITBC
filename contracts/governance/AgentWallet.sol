// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/math/SafeMath.sol";
import "./OpenClawDAO.sol";

/**
 * @title AgentWallet
 * @dev Smart contract wallet for AI agents to participate in OpenClaw DAO governance
 * @notice Enables autonomous voting and reputation-based governance participation
 */
contract AgentWallet is Ownable {
    using SafeMath for uint256;

    // Agent roles matching OpenClawDAO
    enum AgentRole {
        NONE,
        PROVIDER,
        CONSUMER,
        BUILDER,
        COORDINATOR
    }

    // Agent state
    struct AgentState {
        AgentRole role;
        uint256 reputation;
        uint256 lastVote;
        uint256 votingPower;
        bool isActive;
        address daoContract;
        mapping(uint256 => bool) votedProposals;
        mapping(address => bool) authorizedCallers;
    }

    // Voting strategy configuration
    struct VotingStrategy {
        bool autoVote;
        uint8 supportThreshold; // 0-255, higher means more likely to support
        uint256 minReputationToVote;
        bool voteBasedOnRole;
        mapping(OpenClawDAO.ProposalType => uint8) roleVotingPreferences;
    }

    // State variables
    AgentState public agentState;
    VotingStrategy public votingStrategy;
    OpenClawDAO public dao;
    IERC20 public governanceToken;

    // Events
    event AgentRegistered(address indexed agent, AgentRole role, address dao);
    event VoteCast(uint256 indexed proposalId, bool support, string reason);
    event ReputationUpdated(uint256 oldReputation, uint256 newReputation);
    event StrategyUpdated(bool autoVote, uint8 supportThreshold);
    event AutonomousVoteExecuted(uint256 indexed proposalId, bool support);

    // Modifiers
    modifier onlyAuthorized() {
        require(
            msg.sender == owner() || 
            agentState.authorizedCallers[msg.sender] || 
            msg.sender == address(agentState.daoContract),
            "Not authorized"
        );
        _;
    }

    modifier onlyActiveAgent() {
        require(agentState.isActive, "Agent not active");
        _;
    }

    constructor(
        address _owner,
        AgentRole _role,
        address _daoContract,
        address _governanceToken
    ) Ownable(_owner) {
        agentState.role = _role;
        agentState.daoContract = _daoContract;
        agentState.isActive = true;
        agentState.authorizedCallers[_owner] = true;
        
        dao = OpenClawDAO(_daoContract);
        governanceToken = IERC20(_governanceToken);
        
        // Set default voting strategy based on role
        _setDefaultVotingStrategy(_role);
        
        emit AgentRegistered(_owner, _role, _daoContract);
    }

    /**
     * @dev Register agent with OpenClaw DAO
     */
    function registerWithDAO() external onlyAuthorized {
        dao.registerAgentWallet(address(this), agentState.role);
    }

    /**
     * @dev Cast vote on proposal
     * @param proposalId ID of the proposal
     * @param support Whether to support (true) or oppose (false)
     * @param reason Voting reason
     */
    function castVote(
        uint256 proposalId,
        bool support,
        string calldata reason
    ) external onlyAuthorized onlyActiveAgent {
        require(!agentState.votedProposals[proposalId], "Already voted");
        
        // Check reputation requirement
        require(
            agentState.reputation >= votingStrategy.minReputationToVote,
            "Insufficient reputation"
        );

        // Cast vote through DAO
        uint8 supportValue = support ? 1 : 0;
        dao.castVoteWithReason(proposalId, supportValue, reason);
        
        // Update agent state
        agentState.lastVote = block.timestamp;
        agentState.votedProposals[proposalId] = true;
        
        emit VoteCast(proposalId, support, reason);
    }

    /**
     * @dev Autonomous voting based on strategy
     * @param proposalId ID of the proposal
     */
    function autonomousVote(uint256 proposalId) external onlyAuthorized onlyActiveAgent {
        require(votingStrategy.autoVote, "Auto-vote disabled");
        require(!agentState.votedProposals[proposalId], "Already voted");
        
        // Get proposal details from DAO
        (, , , , , , , , , ) = dao.getProposal(proposalId);
        
        // Determine vote based on strategy
        bool support = _calculateAutonomousVote(proposalId);
        
        // Cast the vote
        string memory reason = _generateVotingReason(proposalId, support);
        castVote(proposalId, support, reason);
        
        emit AutonomousVoteExecuted(proposalId, support);
    }

    /**
     * @dev Update agent reputation
     * @param newReputation New reputation score
     */
    function updateReputation(uint256 newReputation) external onlyAuthorized {
        uint256 oldReputation = agentState.reputation;
        agentState.reputation = newReputation;
        
        emit ReputationUpdated(oldReputation, newReputation);
    }

    /**
     * @dev Update voting strategy
     * @param autoVote Whether to enable autonomous voting
     * @param supportThreshold Support threshold (0-255)
     */
    function updateVotingStrategy(
        bool autoVote,
        uint8 supportThreshold
    ) external onlyAuthorized {
        votingStrategy.autoVote = autoVote;
        votingStrategy.supportThreshold = supportThreshold;
        
        emit StrategyUpdated(autoVote, supportThreshold);
    }

    /**
     * @dev Set role-specific voting preferences
     * @param proposalType Proposal type
     * @param preference Voting preference (0-255)
     */
    function setRoleVotingPreference(
        OpenClawDAO.ProposalType proposalType,
        uint8 preference
    ) external onlyAuthorized {
        votingStrategy.roleVotingPreferences[proposalType] = preference;
    }

    /**
     * @dev Add authorized caller
     * @param caller Address to authorize
     */
    function addAuthorizedCaller(address caller) external onlyOwner {
        agentState.authorizedCallers[caller] = true;
    }

    /**
     * @dev Remove authorized caller
     * @param caller Address to remove
     */
    function removeAuthorizedCaller(address caller) external onlyOwner {
        agentState.authorizedCallers[caller] = false;
    }

    /**
     * @dev Get current voting power
     * @return votingPower Current voting power
     */
    function getVotingPower() external view returns (uint256) {
        return governanceToken.balanceOf(address(this));
    }

    /**
     * @dev Check if agent can vote on proposal
     * @param proposalId ID of the proposal
     * @return canVote Whether agent can vote
     */
    function canVote(uint256 proposalId) external view returns (bool) {
        if (!agentState.isActive) return false;
        if (agentState.votedProposals[proposalId]) return false;
        if (agentState.reputation < votingStrategy.minReputationToVote) return false;
        
        return true;
    }

    /**
     * @dev Calculate autonomous vote based on strategy
     * @param proposalId ID of the proposal
     * @return support Whether to support the proposal
     */
    function _calculateAutonomousVote(uint256 proposalId) internal view returns (bool) {
        // Get proposal type preference
        (, , , OpenClawDAO.ProposalType proposalType, , , , , , ) = dao.getProposal(proposalId);
        uint8 preference = votingStrategy.roleVotingPreferences[proposalType];
        
        // Combine with general support threshold
        uint256 combinedScore = uint256(preference) + uint256(votingStrategy.supportThreshold);
        uint256 midpoint = 256; // Midpoint of 0-511 range
        
        return combinedScore > midpoint;
    }

    /**
     * @dev Generate voting reason based on strategy
     * @param proposalId ID of the proposal
     * @param support Whether supporting or opposing
     * @return reason Generated voting reason
     */
    function _generateVotingReason(
        uint256 proposalId,
        bool support
    ) internal view returns (string memory) {
        (, , , OpenClawDAO.ProposalType proposalType, , , , , , ) = dao.getProposal(proposalId);
        
        string memory roleString = _roleToString(agentState.role);
        string memory actionString = support ? "support" : "oppose";
        string memory typeString = _proposalTypeToString(proposalType);
        
        return string(abi.encodePacked(
            "Autonomous ",
            roleString,
            " agent votes to ",
            actionString,
            " ",
            typeString,
            " proposal based on strategy"
        ));
    }

    /**
     * @dev Set default voting strategy based on role
     * @param role Agent role
     */
    function _setDefaultVotingStrategy(AgentRole role) internal {
        votingStrategy.minReputationToVote = 100; // Default minimum reputation
        
        if (role == AgentRole.PROVIDER) {
            // Providers favor infrastructure and resource proposals
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.PARAMETER_CHANGE] = 180;
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.TREASURY_ALLOCATION] = 160;
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.AGENT_TRADING] = 200;
            votingStrategy.supportThreshold = 128;
        } else if (role == AgentRole.CONSUMER) {
            // Consumers favor access and pricing proposals
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.PARAMETER_CHANGE] = 140;
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.TREASURY_ALLOCATION] = 180;
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.AGENT_TRADING] = 160;
            votingStrategy.supportThreshold = 128;
        } else if (role == AgentRole.BUILDER) {
            // Builders favor development and upgrade proposals
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.PROTOCOL_UPGRADE] = 200;
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.DAO_GRANTS] = 180;
            votingStrategy.supportThreshold = 150;
        } else if (role == AgentRole.COORDINATOR) {
            // Coordinators favor governance and system proposals
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.PARAMETER_CHANGE] = 160;
            votingStrategy.roleVotingPreferences[OpenClawDAO.ProposalType.PROTOCOL_UPGRADE] = 180;
            votingStrategy.supportThreshold = 140;
        }
    }

    /**
     * @dev Convert role enum to string
     * @param role Agent role
     * @return roleString String representation
     */
    function _roleToString(AgentRole role) internal pure returns (string memory) {
        if (role == AgentRole.PROVIDER) return "Provider";
        if (role == AgentRole.CONSUMER) return "Consumer";
        if (role == AgentRole.BUILDER) return "Builder";
        if (role == AgentRole.COORDINATOR) return "Coordinator";
        return "Unknown";
    }

    /**
     * @dev Convert proposal type enum to string
     * @param proposalType Proposal type
     * @return typeString String representation
     */
    function _proposalTypeToString(OpenClawDAO.ProposalType proposalType) internal pure returns (string memory) {
        if (proposalType == OpenClawDAO.ProposalType.PARAMETER_CHANGE) return "Parameter Change";
        if (proposalType == OpenClawDAO.ProposalType.PROTOCOL_UPGRADE) return "Protocol Upgrade";
        if (proposalType == OpenClawDAO.ProposalType.TREASURY_ALLOCATION) return "Treasury Allocation";
        if (proposalType == OpenClawDAO.ProposalType.EMERGENCY_ACTION) return "Emergency Action";
        if (proposalType == OpenClawDAO.ProposalType.AGENT_TRADING) return "Agent Trading";
        if (proposalType == OpenClawDAO.ProposalType.DAO_GRANTS) return "DAO Grants";
        return "Unknown";
    }

    /**
     * @dev Emergency stop - disable autonomous voting
     */
    function emergencyStop() external onlyOwner {
        votingStrategy.autoVote = false;
        agentState.isActive = false;
    }

    /**
     * @dev Reactivate agent
     */
    function reactivate() external onlyOwner {
        agentState.isActive = true;
    }
}
