// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/StakingPoolFactory.sol";
import "../contracts/RewardDistributor.sol";
import "../contracts/ContractRegistry.sol";
import "../contracts/AIToken.sol";

/// #1106 pins: unstakeFromPool with accrued rewards must not revert-lock the
/// principal, and the rewards leg must record a real claim for the staker —
/// not pool 1 / address(0) / amount 0, which reverted every unstake.

contract MockPerformanceAggregator {
    uint256 public multiplier = 10000;

    function setMultiplier(uint256 m) external {
        multiplier = m;
    }

    function getReputationScore(address) external pure returns (uint256) {
        return 100;
    }

    function calculateAPYMultiplier(uint256) external view returns (uint256) {
        return multiplier;
    }
}

contract StakingPoolFactory1106Test is Test {
    ContractRegistry registry;
    StakingPoolFactory factory;
    RewardDistributor distributor;
    AIToken token;
    MockPerformanceAggregator agg;
    address staker = address(0x5);
    address other = address(0x6);
    uint256 constant STAKE = 1000e18;

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

        uint256 poolId = factory.createPool("p", 1000, 30 days);
        assertEq(poolId, 1);
        token.transfer(staker, STAKE);
        vm.prank(staker);
        token.approve(address(factory), STAKE);
        vm.prank(staker);
        factory.stakeInPool(1, STAKE);
        vm.warp(block.timestamp + 31 days); // lock over, rewards accrued
    }

    function _claimIdOf(address user) internal view returns (uint256) {
        uint256[] memory claims = distributor.getUserClaims(user);
        return claims.length == 0 ? 0 : claims[0];
    }

    function test_UnstakeWithRewardsDoesNotRevert() public {
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE); // used to revert inside distributeRewards
        assertEq(token.balanceOf(staker), STAKE, "principal must come back");
    }

    function test_UnstakeCreatesRealClaimForStaker() public {
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE);
        uint256 claimId = _claimIdOf(staker);
        assertTrue(claimId != 0, "staker must hold a distributor claim");
        (uint256 id, , address recipient, uint256 amount, , bool claimed, ) = distributor.rewardClaims(claimId);
        assertEq(id, claimId);
        assertEq(recipient, staker);
        assertGt(amount, 0);
        assertFalse(claimed);
    }

    function test_ClaimPaysStakerWhenDistributorFunded() public {
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE);
        uint256 claimId = _claimIdOf(staker);
        (, , , uint256 amount, , , ) = distributor.rewardClaims(claimId);
        token.transfer(address(distributor), amount * 2); // top the float up
        vm.prank(staker);
        distributor.claimReward(claimId);
        assertGt(token.balanceOf(staker), STAKE, "staker nets principal + rewards");
    }

    function test_ForeignClaimCannotBeTaken() public {
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE);
        uint256 claimId = _claimIdOf(staker);
        token.transfer(address(distributor), 1e24);
        vm.prank(other);
        vm.expectRevert();
        distributor.claimReward(claimId);
    }

    function test_DistributorFailureStillReleasesPrincipal() public {
        distributor.pause(); // make the whole rewards leg revert
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE);
        assertEq(token.balanceOf(staker), STAKE, "principal must survive a distributor outage");
    }

    function test_SubBasisMultiplierDoesNotLockPrincipal() public {
        // The real PerformanceAggregator answers <10000 for a 0-reputation
        // staker — multiplier - BASIS_POINTS underflowed and unstake reverted,
        // re-locking principal exactly like the zero-recipient bug (#1106).
        agg.setMultiplier(8000);
        vm.prank(staker);
        factory.unstakeFromPool(1, STAKE);
        assertEq(token.balanceOf(staker), STAKE, "sub-1x multiplier must not lock principal");
    }

    function test_SecondPositionUnstakeAfterFirst() public {
        // second stake from a topped-up staker, then unstake both positions
        token.transfer(staker, STAKE);
        vm.prank(staker);
        token.approve(address(factory), STAKE);
        vm.prank(staker);
        factory.stakeInPool(1, STAKE);
        vm.warp(block.timestamp + 31 days);
        vm.startPrank(staker);
        factory.unstakeFromPool(1, STAKE); // first-found position
        factory.unstakeFromPool(1, STAKE); // second position must not revert either
        vm.stopPrank();
        assertEq(token.balanceOf(staker), 2 * STAKE);
    }
}
