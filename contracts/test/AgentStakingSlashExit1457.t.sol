// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/AgentStaking.sol";
import "../contracts/AIToken.sol";
import "../contracts/PerformanceVerifier.sol";

/// #1457 pin: SLASHED used to be terminal -- unbondStake requires ACTIVE and
/// completeUnbonding requires UNBONDING, so the un-slashed remainder of every
/// slashed stake was stranded in the contract forever, and the slash also
/// never unwound agentMetrics.totalStaked / pool stakerShares / totalStaked.
/// The remainder now exits via withdrawSlashedStake after unbondingPeriod
/// measured from slashedAt, and the confiscated share leaves the accounting
/// at slash time.
contract AgentStakingSlashExit1457Test is Test {
    AIToken token;
    AgentStaking staking;
    PerformanceVerifier pv;
    address agent = makeAddr("agent");
    address staker = makeAddr("staker");
    address other = makeAddr("other");

    uint256 constant STAKE_AMOUNT = 1000e18;
    uint256 constant SLASH_PCT = 10; // percent

    function setUp() public {
        token = new AIToken(40000e18);
        vm.warp(block.timestamp + 2 days);
        pv = new PerformanceVerifier(address(0x11), address(0x12), address(0x13));
        staking = new AgentStaking(address(token), address(pv));
        staking.addSupportedAgent(agent, AgentStaking.PerformanceTier.BRONZE);

        staking.setMaxStakesPerDay(100);
        staking.setMaxStakesPerUser(500);
        staking.setStakeCooldown(0);

        token.transfer(staker, 20000e18);
        token.transfer(other, 20000e18);
        vm.startPrank(staker);
        token.approve(address(staking), type(uint256).max);
        vm.stopPrank();
        vm.startPrank(other);
        token.approve(address(staking), type(uint256).max);
        vm.stopPrank();
    }

    function _stake(address who, uint256 amount) internal returns (uint256) {
        vm.prank(who);
        return staking.stakeOnAgent(agent, amount, 30 days, false);
    }

    function _slashPctAmount(uint256 amount) internal pure returns (uint256) {
        return (amount * SLASH_PCT) / 100;
    }

    /// slashStake (owner path): exactly slashPct is confiscated, the
    /// remainder is recoverable, and metrics/pool unwind completely.
    function test_SlashRemainderWithdrawable() public {
        uint256 id = _stake(staker, STAKE_AMOUNT);
        uint256 slashAmount = _slashPctAmount(STAKE_AMOUNT);
        uint256 remainder = STAKE_AMOUNT - slashAmount;

        uint256 ownerBefore = token.balanceOf(address(this));
        uint256 stakerBefore = token.balanceOf(staker);

        vm.prank(address(this));
        staking.slashStake(id, SLASH_PCT, "test");

        // Only the configured percentage was confiscated -- not 100%.
        assertEq(token.balanceOf(address(this)) - ownerBefore, slashAmount);
        assertEq(token.balanceOf(staker), stakerBefore); // nothing paid yet

        // Accounting: the confiscated share left metrics + pool at slash time.
        (uint256 metricsStaked,,,,,,,) = staking.getAgentMetrics(agent);
        assertEq(metricsStaked, remainder);
        (uint256 poolStaked,,,) = staking.getStakingPool(agent);
        assertEq(poolStaked, remainder);

        // Too early: the unbonding delay measured from slashedAt still applies.
        vm.warp(block.timestamp + 6 days);
        vm.prank(staker);
        vm.expectRevert("Unbonding period not ended");
        staking.withdrawSlashedStake(id);

        vm.warp(block.timestamp + 2 days);
        vm.prank(staker);
        staking.withdrawSlashedStake(id);

        assertEq(token.balanceOf(staker) - stakerBefore, remainder);

        // Fully unwound: metrics and pool back to zero for this agent.
        (metricsStaked,,,,,,,) = staking.getAgentMetrics(agent);
        assertEq(metricsStaked, 0);
        (poolStaked,,,) = staking.getStakingPool(agent);
        assertEq(poolStaked, 0);

        (,,, uint256 stakedAmount,,,,,,,,,,) = staking.stakes(id);
        (,,,,,,, AgentStaking.StakeStatus stakedStatus,,,,,,) = staking.stakes(id);
        assertEq(uint8(stakedStatus), uint8(AgentStaking.StakeStatus.COMPLETED));
        assertEq(stakedAmount, remainder);

        // Terminal: no second withdrawal, no unbonding path.
        vm.prank(staker);
        vm.expectRevert("Stake not slashed");
        staking.withdrawSlashedStake(id);
        vm.prank(staker);
        vm.expectRevert("Stake not active");
        staking.unbondStake(id);
    }

    /// checkAndSlashAgent -> _slashAllStakesForAgent path: same guarantees
    /// across the batched slash loop.
    function test_BatchedSlashRemainderWithdrawable() public {
        uint256 idA = _stake(staker, STAKE_AMOUNT);
        uint256 idB = _stake(other, STAKE_AMOUNT);

        // Fresh agent: averageAccuracy is 0 (< defaultMinAccuracy), so the
        // owner's check slashes every stake at defaultSlashingPercentage.
        uint256 slashPct = staking.defaultSlashingPercentage();
        uint256 slashEach = (STAKE_AMOUNT * slashPct) / 100;
        uint256 remainderEach = STAKE_AMOUNT - slashEach;

        uint256 ownerBefore = token.balanceOf(address(this));
        vm.prank(address(this));
        staking.checkAndSlashAgent(agent);
        assertEq(token.balanceOf(address(this)) - ownerBefore, slashEach * 2);

        (uint256 metricsStaked,,,,,,,) = staking.getAgentMetrics(agent);
        assertEq(metricsStaked, remainderEach * 2);
        (uint256 poolStaked,,,) = staking.getStakingPool(agent);
        assertEq(poolStaked, remainderEach * 2);

        uint256 unbonding = staking.unbondingPeriod();
        vm.warp(block.timestamp + unbonding + 1);

        uint256 stakerBefore = token.balanceOf(staker);
        uint256 otherBefore = token.balanceOf(other);
        vm.prank(staker);
        staking.withdrawSlashedStake(idA);
        vm.prank(other);
        staking.withdrawSlashedStake(idB);

        assertEq(token.balanceOf(staker) - stakerBefore, remainderEach);
        assertEq(token.balanceOf(other) - otherBefore, remainderEach);

        (metricsStaked,,,,,,,) = staking.getAgentMetrics(agent);
        assertEq(metricsStaked, 0);
        (poolStaked,,,) = staking.getStakingPool(agent);
        assertEq(poolStaked, 0);
    }

    /// Guards: only the staker can withdraw, and only while SLASHED.
    function test_WithdrawGuards() public {
        uint256 id = _stake(staker, STAKE_AMOUNT);
        vm.prank(address(this));
        staking.slashStake(id, SLASH_PCT, "test");

        vm.prank(other);
        vm.expectRevert("Not stake owner");
        staking.withdrawSlashedStake(id);

        // An ACTIVE stake cannot use the slashed-exit path.
        uint256 id2 = _stake(other, STAKE_AMOUNT);
        vm.prank(other);
        vm.expectRevert("Stake not slashed");
        staking.withdrawSlashedStake(id2);
    }

    /// An approved appeal still restores ACTIVE -- but only while the stake
    /// is SLASHED. Once the remainder is withdrawn the stake is COMPLETED and
    /// the appeal can no longer resurrect a phantom balance.
    function test_AppealCannotResurrectWithdrawnStake() public {
        uint256 id = _stake(staker, STAKE_AMOUNT);
        vm.prank(address(this));
        staking.slashStake(id, SLASH_PCT, "test");

        vm.prank(staker);
        staking.appealSlashing(id, "not my fault");
        vm.warp(block.timestamp + staking.unbondingPeriod() + 1);
        vm.prank(staker);
        staking.withdrawSlashedStake(id);

        vm.prank(address(this));
        vm.expectRevert("Stake no longer slashed");
        staking.resolveSlashAppeal(id, true);
    }

    /// While still SLASHED (inside the appeal window), an approved appeal
    /// restores ACTIVE and the stake keeps only its un-slashed amount.
    function test_AppealRestoreStillWorks() public {
        uint256 id = _stake(staker, STAKE_AMOUNT);
        vm.prank(address(this));
        staking.slashStake(id, SLASH_PCT, "test");

        vm.prank(staker);
        staking.appealSlashing(id, "not my fault");
        vm.prank(address(this));
        staking.resolveSlashAppeal(id, true);

        (,,,,,, AgentStaking.StakeStatus status,,,,) = staking.getStake(id);
        assertEq(uint8(status), uint8(AgentStaking.StakeStatus.ACTIVE));

        // Remainder still accounted exactly once: metrics/pool hold it, and a
        // later normal unbond pays out only the remainder (slash share gone).
        (uint256 metricsStaked,,,,,,,) = staking.getAgentMetrics(agent);
        assertEq(metricsStaked, STAKE_AMOUNT - _slashPctAmount(STAKE_AMOUNT));
    }
}
