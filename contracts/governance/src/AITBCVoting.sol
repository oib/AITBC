// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./AITBCGovernanceToken.sol";

contract AITBCVoting {
    enum ProposalStatus { Draft, Active, Passed, Rejected, Executed }

    struct Proposal {
        bytes32 id;
        address proposer;
        string proposalType;
        string title;
        string description;
        bytes value;
        ProposalStatus status;
        uint256 votingStart;
        uint256 votingEnd;
        uint256 quorumRequired;
        uint256 yesVotes;
        uint256 noVotes;
    }

    mapping(bytes32 => Proposal) public proposals;
    mapping(bytes32 => mapping(address => bool)) public hasVoted;
    AITBCGovernanceToken public governanceToken;

    uint256 public constant QUORUM_PERCENTAGE = 10; // 10% of total supply
    uint256 public constant EXECUTION_DELAY = 1 days;
    uint256 public constant MIN_VOTING_PERIOD = 1 days;
    uint256 public constant MAX_VOTING_PERIOD = 30 days;

    event ProposalCreated(bytes32 indexed proposalId, address indexed proposer);
    event VoteCast(bytes32 indexed proposalId, address indexed voter, bool support, uint256 power);
    event ProposalExecuted(bytes32 indexed proposalId);

    constructor(address _tokenAddress) {
        governanceToken = AITBCGovernanceToken(_tokenAddress);
    }

    function createProposal(
        string memory proposalType,
        string memory title,
        string memory description,
        bytes memory value,
        uint256 votingPeriod
    ) external returns (bytes32) {
        require(votingPeriod >= MIN_VOTING_PERIOD, "Voting period too short");
        require(votingPeriod <= MAX_VOTING_PERIOD, "Voting period too long");

        bytes32 proposalId = keccak256(abi.encodePacked(msg.sender, block.timestamp, title));

        uint256 votingPower = governanceToken.getVotingPower(msg.sender);
        uint256 totalSupply = governanceToken.totalSupply();
        uint256 quorumRequired = (totalSupply * QUORUM_PERCENTAGE) / 100;

        proposals[proposalId] = Proposal({
            id: proposalId,
            proposer: msg.sender,
            proposalType: proposalType,
            title: title,
            description: description,
            value: value,
            status: ProposalStatus.Active,
            votingStart: block.timestamp,
            votingEnd: block.timestamp + votingPeriod,
            quorumRequired: quorumRequired,
            yesVotes: 0,
            noVotes: 0
        });

        emit ProposalCreated(proposalId, msg.sender);
        return proposalId;
    }

    function vote(bytes32 proposalId, bool support) external {
        Proposal storage proposal = proposals[proposalId];
        require(proposal.status == ProposalStatus.Active, "Proposal not active");
        require(block.timestamp >= proposal.votingStart, "Voting not started");
        require(block.timestamp <= proposal.votingEnd, "Voting ended");
        require(!hasVoted[proposalId][msg.sender], "Already voted");

        uint256 votingPower = governanceToken.getVotingPower(msg.sender);
        require(votingPower > 0, "No voting power");

        hasVoted[proposalId][msg.sender] = true;

        if (support) {
            proposal.yesVotes += votingPower;
        } else {
            proposal.noVotes += votingPower;
        }

        emit VoteCast(proposalId, msg.sender, support, votingPower);
    }

    function executeProposal(bytes32 proposalId) external {
        Proposal storage proposal = proposals[proposalId];
        require(proposal.status == ProposalStatus.Active, "Proposal not active");
        require(block.timestamp > proposal.votingEnd, "Voting still active");
        require(block.timestamp >= proposal.votingEnd + EXECUTION_DELAY, "Execution delay not met");

        uint256 totalVotes = proposal.yesVotes + proposal.noVotes;
        require(totalVotes >= proposal.quorumRequired, "Quorum not met");
        require(proposal.yesVotes > proposal.noVotes, "Proposal rejected");

        proposal.status = ProposalStatus.Executed;
        emit ProposalExecuted(proposalId);

        // Execute proposal logic here - would call appropriate contract functions
        _executeProposalValue(proposalId, proposal.value);
    }

    function _executeProposalValue(bytes32 proposalId, bytes memory value) internal {
        // Placeholder for proposal execution logic
        // Different proposal types would have different execution paths
    }

    function getProposal(bytes32 proposalId) external view returns (Proposal memory) {
        return proposals[proposalId];
    }

    function hasVotedOn(address voter, bytes32 proposalId) external view returns (bool) {
        return hasVoted[proposalId][voter];
    }
}
