// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/StakingPoolFactory.sol";
import "../contracts/RewardDistributor.sol";
import "../contracts/ContractRegistry.sol";
import "../contracts/AIToken.sol";

/// #1467 pins: unstakeFromPool must advance position.lastRewardTime, so a
/// second unstake only earns the delta since the previous checkpoint —
/// not the whole window since lock start again on the reduced amount.
/// Asserts on position.accumulatedRewards (banked on every unstake) rather
/// than distributor claims, since sub-1-token rewards skip the best-effort
/// rewards leg by design.

contract MockPerformanceAggregator {
    uint256 public multiplier = 10000;

    function getReputationScore(address) external pure returns (uint256) {
        return 100;
    }

    function calculateAPYMultiplier(uint256) external view returns (uint256) {
        return multiplier;
    }
}

contract StakingPoolRewardCheckpoint1467Test is Test {
    ContractRegistry registry;
    StakingPoolFactory factory;
    RewardDistributor distributor;
    AIToken token;
    MockPerformanceAggregator agg;
    address staker = address(0x5);

    uint256 constant STAKE = 1000e18;
    uint256 constant APY = 1000; // 10% in basis points
    uint256 constant WINDOW = 31 days;
    uint256 startTime;

    function setUp() public {
        registry = new ContractRegistry();
        token = new AIToken(10_000_000e18);
        factory = new StakingPoolFactory(address(token));
        distributor = new RewardDistributor();
        agg = new MockPerformanceAggregator();

        registry.registerContract(keccak256("StakingPoolFactory"), address(factory));
        registry.registerContract(keccak256("PerformanceAggregator"), address(agg));
        registry.registerContract(keccak256("RewardDistributor"), address(distributor));
        factory.initialize(address(registry));
        distributor.initialize(address(registry));

        factory.createPool("p", APY, 30 days);
        // Reward float on top of staked principal, plus headroom for the
        // createRewardPool pulls the unstake rewards leg performs.
        token.transfer(address(factory), 100 * STAKE);
        token.transfer(staker, 2 * STAKE);
        vm.prank(staker);
        token.approve(address(factory), 2 * STAKE);
        vm.prank(staker);
        factory.stakeInPool(1, STAKE);
        startTime = block.timestamp;
    }

    function _accumulated() internal view returns (uint256) {
        (, , , , , , uint256 acc, , ) = factory.getPositionDetails(1);
        return acc;
    }

    function _expectedRewards(uint256 amount, uint256 elapsed) internal pure returns (uint256) {
        // Mirrors _calculateRewards with multiplier == BASIS_POINTS (no bonus).
        return (amount * APY * elapsed) / (10000 * 365 days);
    }

    function test_PartialUnstakeDoesNotRepayAccrualWindow() public {
        vm.warp(startTime + WINDOW); // lock over, first window accrued

        // First unstake: half the position, rewards over the full window.
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE / 2);
        uint256 afterFirst = _accumulated();
        assertEq(afterFirst, _expectedRewards(STAKE, WINDOW));

        // Second window: only the delta since the checkpoint may accrue,
        // and only on the remaining half position. Pre-fix this recomputed
        // (STAKE/2) * rate * (2 * WINDOW) — the whole window again.
        vm.warp(startTime + 2 * WINDOW);
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE / 2);
        uint256 total = _accumulated();
        assertEq(total, afterFirst + _expectedRewards(STAKE / 2, WINDOW));
        assertLt(total - afterFirst, afterFirst);
    }

    function test_BackToBackUnstakesEarnNoOverlappingWindow() public {
        vm.warp(startTime + WINDOW);

        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE / 4);
        uint256 afterFirst = _accumulated();
        assertEq(afterFirst, _expectedRewards(STAKE, WINDOW));

        // Unstake again 10 days later: only the 10-day delta on the
        // remaining 3/4 position — not the whole 41-day window again.
        vm.warp(startTime + WINDOW + 10 days);
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE / 4);
        uint256 total = _accumulated();
        assertEq(total, afterFirst + _expectedRewards((STAKE * 3) / 4, 10 days));
    }
}
