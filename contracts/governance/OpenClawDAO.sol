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

/**
 * @title OpenClawDAO
 * @dev Decentralized Autonomous Organization for AITBC governance
 * @notice Implements on-chain voting for protocol decisions
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
    // Voting parameters
    uint256 private constant VOTING_DELAY = 1 days;
    uint256 private constant VOTING_PERIOD = 7 days;
    uint256 private constant PROPOSAL_THRESHOLD = 1000e18; // 1000 tokens
    uint256 private constant QUORUM_PERCENTAGE = 4; // 4%

    // Proposal types
    enum ProposalType {
        PARAMETER_CHANGE,
        PROTOCOL_UPGRADE,
        TREASURY_ALLOCATION,
        EMERGENCY_ACTION
    }

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
    }

    // State variables
    IERC20 public governanceToken;
    mapping(uint256 => Proposal) public proposals;
    uint256 public proposalCount;
    
    // Events
    event ProposalCreated(
        uint256 indexed proposalId,
        address indexed proposer,
        ProposalType proposalType,
        string description
    );
    
    event VoteCast(
        uint256 indexed proposalId,
        address indexed voter,
        uint8 support,
        uint256 weight,
        string reason
    );

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
    }

    /**
     * @dev Create a new proposal
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
    ) public override returns (uint256) {
        require(
            governanceToken.balanceOf(msg.sender) >= PROPOSAL_THRESHOLD,
            "OpenClawDAO: insufficient tokens to propose"
        );

        uint256 proposalId = super.propose(targets, values, calldatas, description);
        
        proposals[proposalId] = Proposal({
            proposer: msg.sender,
            startTime: block.timestamp + VOTING_DELAY,
            endTime: block.timestamp + VOTING_DELAY + VOTING_PERIOD,
            proposalType: proposalType,
            description: description,
            executed: false,
            forVotes: 0,
            againstVotes: 0,
            abstainVotes: 0
        });
        
        proposalCount++;
        
        emit ProposalCreated(proposalId, msg.sender, proposalType, description);
        
        return proposalId;
    }

    /**
     * @dev Cast a vote on a proposal
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
        
        uint256 weight = governanceToken.balanceOf(msg.sender);
        require(weight > 0, "OpenClawDAO: no voting power");
        
        uint256 votes = super.castVoteWithReason(proposalId, support, reason);
        
        // Update vote counts
        if (support == 1) {
            proposals[proposalId].forVotes += weight;
        } else if (support == 0) {
            proposals[proposalId].againstVotes += weight;
        } else {
            proposals[proposalId].abstainVotes += weight;
        }
        
        emit VoteCast(proposalId, msg.sender, support, weight, reason);
        
        return votes;
    }

    /**
     * @dev Execute a successful proposal
     * @param proposalId ID of the proposal
     */
    function execute(
        uint256 proposalId
    ) public payable override {
        require(
            state(proposalId) == ProposalState.Succeeded,
            "OpenClawDAO: proposal not successful"
        );
        
        proposals[proposalId].executed = true;
        super.execute(proposalId);
    }

    /**
     * @dev Get proposal details
     * @param proposalId ID of the proposal
     * @return Proposal details
     */
    function getProposal(uint256 proposalId) 
        public 
        view 
        returns (Proposal memory) 
    {
        return proposals[proposalId];
    }

    /**
     * @dev Get all active proposals
     * @return Array of active proposal IDs
     */
    function getActiveProposals() public view returns (uint256[] memory) {
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

    /**
     * @dev Emergency pause functionality
     */
    function emergencyPause() public onlyOwner {
        // Implementation for emergency pause
        _setProposalDeadline(0, block.timestamp + 1 hours);
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
        return (governanceToken.getTotalSupply() * QUORUM_PERCENTAGE) / 100;
    }

    function proposalThreshold() public pure override returns (uint256) {
        return PROPOSAL_THRESHOLD;
    }
}
