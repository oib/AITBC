// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../src/AITBCGovernanceToken.sol";
import "../src/AITBCVoting.sol";

contract AITBCVotingTest is Test {
    AITBCGovernanceToken token;
    AITBCVoting voting;
    address owner;
    address user1;
    address user2;

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        user2 = address(0x2);

        token = new AITBCGovernanceToken();
        voting = new AITBCVoting(address(token));

        // Transfer tokens to users
        token.transfer(user1, 10000 * 10**18);
        token.transfer(user2, 10000 * 10**18);
    }

    function testCreateProposal() public {
        vm.startPrank(user1);

        bytes32 proposalId = voting.createProposal(
            "parameter_change",
            "Test Proposal",
            "Test description",
            abi.encode("test_value"),
            7 days
        );

        vm.stopPrank();

        // Verify proposal was created
        AITBCVoting.Proposal memory proposal = voting.getProposal(proposalId);

        assertEq(proposal.proposer, user1);
        assertEq(proposal.proposalType, "parameter_change");
        assertEq(proposal.title, "Test Proposal");
        assertEq(uint256(proposal.status), uint256(AITBCVoting.ProposalStatus.Active));
    }

    function testCreateProposalInvalidVotingPeriod() public {
        vm.startPrank(user1);

        vm.expectRevert("Voting period too short");
        voting.createProposal(
            "parameter_change",
            "Test Proposal",
            "Test description",
            abi.encode("test_value"),
            1 hours // Below minimum (1 day)
        );

        vm.stopPrank();
    }

    function testVoteOnProposal() public {
        vm.startPrank(user1);

        bytes32 proposalId = voting.createProposal(
            "parameter_change",
            "Test Proposal",
            "Test description",
            abi.encode("test_value"),
            7 days
        );

        voting.vote(proposalId, true);

        vm.stopPrank();

        // Verify vote was recorded
        bool hasVoted = voting.hasVotedOn(user1, proposalId);
        assertTrue(hasVoted);
    }

    function testCannotVoteTwice() public {
        vm.startPrank(user1);

        bytes32 proposalId = voting.createProposal(
            "parameter_change",
            "Test Proposal",
            "Test description",
            abi.encode("test_value"),
            7 days
        );

        voting.vote(proposalId, true);

        vm.expectRevert("Already voted");
        voting.vote(proposalId, true);

        vm.stopPrank();
    }

    function testCannotVoteAfterVotingEnds() public {
        vm.startPrank(user1);

        bytes32 proposalId = voting.createProposal(
            "parameter_change",
            "Test Proposal",
            "Test description",
            abi.encode("test_value"),
            7 days
        );

        // Fast forward past voting period
        vm.warp(block.timestamp + 8 days);

        vm.expectRevert("Voting ended");
        voting.vote(proposalId, true);

        vm.stopPrank();
    }

    function testExecuteProposal() public {
        // Transfer more tokens to meet quorum (10% of 1B = 100M tokens)
        token.transfer(user1, 100_000_001 * 10**18);

        vm.startPrank(user1);

        bytes32 proposalId = voting.createProposal(
            "parameter_change",
            "Test Proposal",
            "Test description",
            abi.encode("test_value"),
            7 days
        );

        voting.vote(proposalId, true);
        vm.stopPrank();

        // Fast forward past voting period and execution delay
        vm.warp(block.timestamp + 8 days + 2 days);

        vm.startPrank(user1);
        voting.executeProposal(proposalId);
        vm.stopPrank();

        // Verify proposal was executed
        AITBCVoting.Proposal memory proposal = voting.getProposal(proposalId);
        assertEq(uint256(proposal.status), uint256(AITBCVoting.ProposalStatus.Executed));
    }

    function testCannotExecuteRejectedProposal() public {
        // Transfer more tokens to meet quorum
        token.transfer(user1, 100_000_001 * 10**18);

        vm.startPrank(user1);

        bytes32 proposalId = voting.createProposal(
            "parameter_change",
            "Test Proposal",
            "Test description",
            abi.encode("test_value"),
            7 days
        );

        voting.vote(proposalId, false); // Vote against
        vm.stopPrank();

        // Fast forward past voting period and execution delay
        vm.warp(block.timestamp + 8 days + 2 days);

        vm.startPrank(user1);
        vm.expectRevert("Proposal rejected");
        voting.executeProposal(proposalId);
        vm.stopPrank();
    }
}
