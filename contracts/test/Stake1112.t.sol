// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/AgentStaking.sol";
import "../contracts/AIToken.sol";
import "../contracts/PerformanceVerifier.sol";

/// #1112 pins: completeUnbonding paid unfunded APY rewards from the shared
/// balance, kept the early-exit penalty trapped in the contract, and
/// auto-compound inflated principal beyond funded deposits so a sole
/// staker's unbond underflowed.
contract Stake1112Test is Test {
    AIToken token;
    AgentStaking staking;
    PerformanceVerifier pv;
    address agent = makeAddr("agent");
    address staker = makeAddr("staker");

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days);
        pv = new PerformanceVerifier(address(0x11), address(0x12), address(0x13));
        staking = new AgentStaking(address(token), address(pv));
        staking.addSupportedAgent(agent, AgentStaking.PerformanceTier.BRONZE);
        token.mint(staker, 2000e18);
        vm.prank(staker);
        token.approve(address(staking), 2000e18);
    }

    function test_PenaltyGoesToOwnerNotTrapped() public {
        vm.prank(staker);
        uint256 id = staking.stakeOnAgent(agent, 500e18, 30 days, false);
        // accrue rewards + pass lock + unbonding, still inside 30d penalty window
        vm.warp(block.timestamp + 30 days + 7 days + 1 days);
        vm.prank(staker);
        staking.unbondStake(id);
        address treasury = staking.owner();
        uint256 before = token.balanceOf(treasury);
        uint256 stakerBefore = token.balanceOf(staker);
        vm.prank(staker);
        staking.completeUnbonding(id);
        uint256 got = token.balanceOf(staker) - stakerBefore;
        uint256 penalty = (500e18 * staking.earlyUnbondPenalty()) / 10000;
        assertEq(got, 500e18 - penalty); // principal minus penalty, nothing else
        assertEq(token.balanceOf(treasury) - before, penalty); // penalty paid out
    }

    function test_AutoCompoundDoesNotBlockUnbond() public {
        vm.prank(staker);
        uint256 id = staking.stakeOnAgent(agent, 500e18, 30 days, true);
        // accrue rewards over time so compound would have fired
        vm.warp(block.timestamp + 400 days);
        vm.prank(staker);
        staking.unbondStake(id);
        vm.prank(staker);
        staking.completeUnbonding(id); // must not underflow/revert
    }

    function test_UnfundedRewardsNotPaid() public {
        vm.prank(staker);
        uint256 id = staking.stakeOnAgent(agent, 500e18, 30 days, false);
        vm.warp(block.timestamp + 400 days); // past penalty window
        vm.prank(staker);
        staking.unbondStake(id);
        uint256 before = token.balanceOf(staker);
        vm.prank(staker);
        staking.completeUnbonding(id);
        assertEq(token.balanceOf(staker) - before, 500e18); // principal only, no phantom APY
    }
}
