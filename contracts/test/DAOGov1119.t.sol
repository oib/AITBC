// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/DAOGovernance.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract T1119Token is ERC20 {
    constructor() ERC20("T", "T") { _mint(msg.sender, 1_000_000e18); }
}

contract T1119Target {
    uint256 public calls;
    function poke() external { calls++; }
}

/// #1119 pins: bare-majority pass with no quorum, executeProposal a no-op,
/// votes surviving unstake.
contract DAOGov1119Test is Test {
    T1119Token token;
    DAOGovernance gov;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address carol = makeAddr("carol");

    function setUp() public {
        token = new T1119Token();
        gov = new DAOGovernance(address(token), 1e18);
        token.transfer(alice, 100e18);
        token.transfer(bob, 100e18);
        token.transfer(carol, 1000e18);
        vm.prank(alice); token.approve(address(gov), 100e18);
        vm.prank(bob); token.approve(address(gov), 100e18);
        vm.prank(carol); token.approve(address(gov), 1000e18);
        vm.prank(alice); gov.stake(80e18);
        vm.prank(bob); gov.stake(80e18);
        vm.prank(carol); gov.stake(80e18);
    }

    function _prop() internal returns (uint256 id) {
        vm.prank(alice);
        id = gov.createProposal("", "h", 2 days);
    }

    function test_MinVotingPeriodEnforced() public {
        vm.prank(alice);
        vm.expectRevert("Voting period too short");
        gov.createProposal("", "h", 1 hours);
    }

    function test_QuorumBlocksLowTurnout() public {
        // No votes cast: participation 0 < quorum -> execute reverts.
        uint256 id = _prop();
        vm.warp(block.timestamp + 2 days + 1);
        vm.expectRevert("Quorum not reached");
        gov.executeProposal(id);
    }

    function test_VoteLocksStakeUntilEnd() public {
        uint256 id = _prop();
        vm.prank(bob);
        gov.castVote(id, true);
        vm.prank(bob);
        vm.expectRevert("Voting lock active");
        gov.initiateUnstake(80e18);
        vm.warp(block.timestamp + 2 days + 1);
        vm.prank(bob);
        gov.initiateUnstake(80e18); // lock expired with the proposal
    }

    function test_ExecProposalReallyCalls() public {
        T1119Target target = new T1119Target();
        vm.prank(alice);
        uint256 id = gov.createProposalExec("", "h", 2 days, address(target), abi.encodeCall(T1119Target.poke, ()));
        vm.prank(bob);
        gov.castVote(id, true);
        vm.warp(block.timestamp + 2 days + 1);
        gov.executeProposal(id);
        assertEq(target.calls(), 1);
    }

    function test_TurnoutBelowQuorumRejected() public {
        // carol raises totalStaked to 740e18 -> quorum 74e18. bob unstakes first
        // to shrink turnout: he initiates unstake BEFORE voting (no lock yet),
        // then nobody votes — participation 0 < 74e18 -> rejected.
        uint256 id = _prop();
        vm.prank(carol);
        gov.stake(500e18);
        vm.warp(block.timestamp + 2 days + 1);
        vm.expectRevert("Quorum not reached");
        gov.executeProposal(id);
    }
}
