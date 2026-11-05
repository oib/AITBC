// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "./AgentDAO1117.t.sol";
import "../src/GovernanceAgentWallet.sol";
import "@openzeppelin/contracts/governance/TimelockController.sol";

/// #1120 pins: tokens sent to the wallet for voting power were stranded;
/// the reputation gate was self-set by the caller it gated; the vote path
/// read self-set reputation.
contract GovWallet1120Test is Test {
    MockVotesToken token;
    AgentDAO dao;
    GovernanceAgentWallet wallet;
    address owner = makeAddr("owner");

    function setUp() public {
        token = new MockVotesToken();
        TimelockController tl = new TimelockController(0, new address[](0), new address[](0), address(this));
        dao = new AgentDAO(address(token), tl);
        vm.prank(owner);
        wallet = new GovernanceAgentWallet(owner, GovernanceAgentWallet.AgentRole.PROVIDER, address(dao), address(token));
    }

    function test_OwnerWithdrawsTokens() public {
        token.mint(address(wallet), 50e18);
        assertEq(token.balanceOf(address(wallet)), 50e18);
        vm.prank(owner);
        wallet.withdrawTokens(owner, 50e18);
        assertEq(token.balanceOf(address(wallet)), 0);
        assertEq(token.balanceOf(owner), 50e18);
        // Non-owner cannot withdraw.
        vm.expectRevert();
        wallet.withdrawTokens(address(this), 1);
    }

    function test_ReputationComesFromDAO() public {
        // Wallet not registered in the DAO: daoReputation = 0, canVote false —
        // there is no longer any self-settable reputation to satisfy the gate.
        assertEq(wallet.daoReputation(), 0);
        vm.prank(owner);
        vm.expectRevert();
        wallet.castVote(1, true, "x");
    }
}
