// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../src/GPUStaking.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract StakingMockToken is ERC20 {
    constructor() ERC20("Mock AITBC", "MAIT") {
        _mint(msg.sender, 10_000_000 * 10 ** 18);
    }
}

/**
 * Pins issue #1116: claimRewards used to leave lastRewardTime untouched, so
 * every call paid the full accumulated reward again from the shared token
 * balance (other providers' stakes), the pool's rewardPool was never debited,
 * and the share was computed from the provider's global gpuPower against any
 * pool id the caller named.
 */
contract GPUStakingTest is Test {
    StakingMockToken token;
    GPUStaking staking;

    address owner = address(this);
    address provider = address(0xA);
    address provider2 = address(0xB);

    uint256 constant STAKE = 100e18;
    uint256 constant POWER = 100;

    function setUp() public {
        token = new StakingMockToken();
        staking = new GPUStaking(address(token));

        token.transfer(provider, 1_000e18);
        token.transfer(provider2, 1_000e18);

        // Full utilization so rewards accrue at the pool rate.
        staking.updateUtilizationRate(1, 10000);
    }

    function _stake(address who, uint256 poolId, uint256 power, uint256 amount) internal {
        vm.startPrank(who);
        token.approve(address(staking), amount);
        staking.stakeGPU(poolId, power, amount, 7 days, "{}");
        vm.stopPrank();
    }

    function _fundPool(uint256 poolId, uint256 amount) internal {
        token.approve(address(staking), amount);
        staking.updateRewardPool(poolId, amount);
    }

    function testSecondClaimPaysNothing() public {
        _stake(provider, 1, POWER, STAKE);
        _fundPool(1, 50e18);

        vm.warp(block.timestamp + 10_000);
        uint256 pending = staking.getPendingRewards(provider, 1);
        assertGt(pending, 0);

        vm.prank(provider);
        staking.claimRewards(1);
        uint256 got = token.balanceOf(provider) - (1_000e18 - STAKE);
        assertEq(got, pending);

        // Clock advanced: a second claim has nothing to pay.
        assertEq(staking.getPendingRewards(provider, 1), 0);
        vm.prank(provider);
        vm.expectRevert("No rewards to claim");
        staking.claimRewards(1);
    }

    function testPayoutCannotExceedRewardPool() public {
        _stake(provider, 1, POWER, STAKE);
        _fundPool(1, 5e18); // deliberately underfund

        // Accrue far more than the pool holds.
        vm.warp(block.timestamp + 1_000_000);
        uint256 pending = staking.getPendingRewards(provider, 1);
        assertGt(pending, 5e18);

        uint256 contractBefore = token.balanceOf(address(staking));
        vm.prank(provider);
        staking.claimRewards(1);

        // Paid exactly the reward pool — never a wei of other stakes.
        assertEq(token.balanceOf(provider), 1_000e18 - STAKE + 5e18);
        assertEq(contractBefore - token.balanceOf(address(staking)), 5e18);

        // The unpaid remainder stays banked, not lost.
        assertGt(staking.getPendingRewards(provider, 1), 0);
    }

    function testCannotClaimAgainstAPoolNotContributedTo() public {
        _stake(provider, 1, POWER, STAKE);
        staking.createPool("pool2", 1e15);
        staking.updateUtilizationRate(2, 10000);
        _fundPool(2, 100e18);

        vm.warp(block.timestamp + 10_000);
        // Provider has power in pool 1 but none in pool 2.
        assertEq(staking.getPendingRewards(provider, 2), 0);
        vm.prank(provider);
        vm.expectRevert("No rewards to claim");
        staking.claimRewards(2);
    }

    function testRestakeBanksAccruedRewards() public {
        _stake(provider, 1, POWER, STAKE);
        _fundPool(1, 50e18);

        vm.warp(block.timestamp + 10_000);
        uint256 accrued = staking.getPendingRewards(provider, 1);
        assertGt(accrued, 0);

        // Re-staking must not forfeit what already accrued.
        _stake(provider, 1, POWER, STAKE);
        assertEq(staking.getPendingRewards(provider, 1), accrued);

        vm.warp(block.timestamp + 10_000);
        vm.prank(provider);
        staking.claimRewards(1);
        assertGt(token.balanceOf(provider), 1_000e18 - 2 * STAKE);
    }

    function testUnstakeKeepsAccruedRewardsClaimable() public {
        _stake(provider, 1, POWER, STAKE);
        _stake(provider2, 1, POWER, STAKE);
        _fundPool(1, 500e18);

        vm.warp(block.timestamp + 8 days); // past the 7-day lock
        uint256 accrued = staking.getPendingRewards(provider, 1);
        assertGt(accrued, 0);

        vm.prank(provider);
        staking.unstakeGPU(1, POWER);
        assertEq(staking.getPendingRewards(provider, 1), accrued);

        // Fully unstaked providers can still collect banked rewards.
        vm.prank(provider);
        staking.claimRewards(1);
        assertEq(token.balanceOf(provider), 1_000e18 + accrued);

        // provider2's accrued share is untouched by provider's claim.
        uint256 accrued2 = staking.getPendingRewards(provider2, 1);
        assertGt(accrued2, 0);
    }
}
