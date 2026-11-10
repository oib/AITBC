// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/AgentStaking.sol";
import "../contracts/AIToken.sol";
import "../contracts/PerformanceVerifier.sol";

/// #1465 pin: the tier-update APY refresh iterated the append-only
/// agentStakes array, so an agent's lifetime stake count -- not its active
/// stake count -- set the gas cost of every tier change. The refresh now walks
/// agentActiveStakes, kept in sync on every stake status transition.
contract AgentStakingTierGas1465Test is Test {
    AIToken token;
    AgentStaking staking;
    PerformanceVerifier pv;
    address agent = makeAddr("agent");
    address oracle = makeAddr("oracle");
    address stakerA = makeAddr("stakerA");
    address stakerB = makeAddr("stakerB");

    uint256 constant MIN_STAKE = 100e18;

    function setUp() public {
        token = new AIToken(40000e18); // to this contract; mint() has a 1-day cooldown
        vm.warp(block.timestamp + 2 days);
        pv = new PerformanceVerifier(address(0x11), address(0x12), address(0x13));
        staking = new AgentStaking(address(token), address(pv));
        staking.addSupportedAgent(agent, AgentStaking.PerformanceTier.BRONZE);
        staking.addOracle(oracle);

        // Lift per-user rate limits so the fixture can accumulate the stake
        // history the bug feeds on.
        staking.setMaxStakesPerDay(100);
        staking.setMaxStakesPerUser(500);
        staking.setStakeCooldown(0);

        token.transfer(stakerA, 20000e18);
        token.transfer(stakerB, 20000e18);
        vm.prank(stakerA);
        token.approve(address(staking), type(uint256).max);
        vm.prank(stakerB);
        token.approve(address(staking), type(uint256).max);
    }

    function _stake(address staker) internal returns (uint256) {
        vm.prank(staker);
        return staking.stakeOnAgent(agent, MIN_STAKE, 30 days, false);
    }

    function _complete(address staker, uint256 stakeId) internal {
        vm.prank(staker);
        staking.unbondStake(stakeId);
        vm.prank(staker);
        staking.completeUnbonding(stakeId);
    }

    /// agentActiveStakes must mirror every status transition: added on
    /// stakeOnAgent, removed on unbond/slash, re-added when a slash appeal is
    /// approved.
    function test_ActiveListTracksTransitions() public {
        uint256 id0 = _stake(stakerA);
        uint256 id1 = _stake(stakerB);
        assertEq(staking.getAgentActiveStakes(agent).length, 2);

        // Past lock + unbonding window, then complete -> leaves the active list.
        vm.warp(block.timestamp + 40 days);
        _complete(stakerA, id0);
        assertEq(staking.getAgentActiveStakes(agent).length, 1);
        assertEq(staking.getAgentStakes(agent).length, 2); // history kept

        // Slash removes from the active list.
        uint256 id2 = _stake(stakerA);
        assertEq(staking.getAgentActiveStakes(agent).length, 2);
        vm.prank(address(this));
        staking.slashStake(id2, 10, "test");
        assertEq(staking.getAgentActiveStakes(agent).length, 1);

        // Approved appeal re-activates the stake and re-adds it.
        vm.prank(stakerA);
        staking.appealSlashing(id2, "appeal");
        vm.prank(address(this));
        staking.resolveSlashAppeal(id2, true);
        uint256[] memory active = staking.getAgentActiveStakes(agent);
        assertEq(active.length, 2);
        assertTrue(active[0] == id1 || active[1] == id1);
        assertTrue(active[0] == id2 || active[1] == id2);
    }

    /// The exploit shape: an agent accumulates far more historical stakes than
    /// active ones. A tier change must still succeed and must update exactly
    /// the active stakes -- the historical entries are skipped entirely.
    function test_TierUpdateSkipsHistoricalStakes() public {
        // 110 stakes that will be retired + 5 that stay active.
        // ids 0..99   -> stakerA
        // ids 100..109 -> stakerB (to be retired)
        // ids 110..114 -> stakerB (stay active)
        for (uint256 i = 0; i < 100; i++) {
            _stake(stakerA);
        }
        for (uint256 i = 0; i < 15; i++) {
            _stake(stakerB);
        }
        assertEq(staking.getAgentStakes(agent).length, 115);
        assertEq(staking.getAgentActiveStakes(agent).length, 115);

        // Past every lock + unbonding window, then retire 110 stakes.
        vm.warp(block.timestamp + 40 days);
        for (uint256 id = 0; id < 100; id++) {
            _complete(stakerA, id);
        }
        for (uint256 id = 100; id < 110; id++) {
            _complete(stakerB, id);
        }
        assertEq(staking.getAgentStakes(agent).length, 115); // history kept
        assertEq(staking.getAgentActiveStakes(agent).length, 5);

        // Snapshot APY/tier of an active stake (id 110) and a completed one.
        (,,,,,,,, uint256 activeApyBefore, AgentStaking.PerformanceTier activeTierBefore,) =
            staking.getStake(110);
        (,,,,,,,, uint256 doneApyBefore, AgentStaking.PerformanceTier doneTierBefore,) =
            staking.getStake(0);

        // One oracle update flips BRONZE -> DIAMOND (accuracy 100, 100% success).
        vm.prank(oracle);
        staking.updateAgentPerformance(agent, 100, true);

        (,,,,,, AgentStaking.PerformanceTier newTier,) = staking.getAgentMetrics(agent);
        assertEq(uint8(newTier), uint8(AgentStaking.PerformanceTier.DIAMOND));

        for (uint256 id = 110; id < 115; id++) {
            (,,,,,,,, uint256 apy, AgentStaking.PerformanceTier tier,) = staking.getStake(id);
            assertEq(uint8(tier), uint8(AgentStaking.PerformanceTier.DIAMOND));
            assertGt(apy, activeApyBefore, "active stake APY must be refreshed");
        }
        // Completed stake keeps its historical tier/APY -- it is not in the
        // active list and the refresh no longer scans it.
        (,,,,,,,, uint256 doneApyAfter, AgentStaking.PerformanceTier doneTierAfter,) =
            staking.getStake(0);
        assertEq(uint8(doneTierAfter), uint8(doneTierBefore));
        assertEq(doneApyAfter, doneApyBefore);
        assertEq(uint8(activeTierBefore), uint8(AgentStaking.PerformanceTier.BRONZE));
    }
}
