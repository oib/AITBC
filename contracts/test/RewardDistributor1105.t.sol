// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/RewardDistributor.sol";
import "../contracts/ContractRegistry.sol";
import "../contracts/AIToken.sol";

/// #1105 pins: reward pools are funded at creation, claims can never exceed
/// the deposited backing, and performance rewards become real claims the
/// agent can actually be paid.

contract RewardDistributor1105Test is Test {
    ContractRegistry registry;
    RewardDistributor distributor;
    AIToken token;
    address agent = address(0xB2);
    address claimant = address(0xC3);

    uint256 constant POOL = 1000e18;
    uint256 constant FEE_BPS = 10; // CLAIM_FEE_PERCENTAGE

    function setUp() public {
        registry = new ContractRegistry();
        token = new AIToken(1_000_000e18); // minted to this contract (owner)
        distributor = new RewardDistributor();
        registry.registerContract(keccak256("RewardDistributor"), address(distributor));
        distributor.initialize(address(registry));
        token.approve(address(distributor), type(uint256).max);
    }

    function _net(uint256 amount) internal pure returns (uint256) {
        return amount - (amount * FEE_BPS) / 10_000;
    }

    function _createPool() internal returns (uint256 poolId) {
        return distributor.createRewardPool(address(token), POOL);
    }

    function test_PoolCreationPullsTokensAndReturnsId() public {
        uint256 balBefore = token.balanceOf(address(distributor));
        uint256 poolId = _createPool();
        assertEq(poolId, 1);
        assertEq(token.balanceOf(address(distributor)) - balBefore, POOL, "pool must be funded at creation");
        assertEq(distributor.reservedByToken(address(token)), POOL);
        (, , uint256 total, , , bool active, , , ) = distributor.rewardPools(poolId);
        assertEq(total, POOL);
        assertTrue(active);
    }

    function test_PoolCreationRevertsWithoutApproval() public {
        token.approve(address(distributor), 0);
        vm.expectRevert();
        _createPool();
    }

    function test_DistributeCannotExceedFundedPool() public {
        uint256 poolId = _createPool();
        address[] memory recipients = new address[](2);
        recipients[0] = claimant;
        recipients[1] = agent;
        uint256[] memory amounts = new uint256[](2);
        amounts[0] = POOL;
        amounts[1] = 1; // one wei over the funded amount
        vm.expectRevert();
        distributor.distributeRewards(poolId, recipients, amounts);
    }

    function test_ClaimsCannotExceedDepositsAcrossPools() public {
        // Two pools share one token; the second must not spend the first's
        // backing — claims are bounded by each pool's own funded total.
        uint256 p1 = _createPool();
        uint256 p2 = _createPool();
        assertEq(token.balanceOf(address(distributor)), 2 * POOL);

        address[] memory r1 = new address[](1);
        r1[0] = claimant;
        uint256[] memory a1 = new uint256[](1);
        a1[0] = POOL;
        distributor.distributeRewards(p1, r1, a1);

        // p2 still has its full backing available
        uint256[] memory a2 = new uint256[](1);
        a2[0] = POOL;
        distributor.distributeRewards(p2, r1, a2);

        uint256[] memory claims = distributor.getUserClaims(claimant);
        assertEq(claims.length, 2);

        vm.prank(claimant);
        distributor.claimReward(claims[0]);
        uint256 balAfterFirst = token.balanceOf(claimant);
        vm.prank(claimant);
        distributor.claimReward(claims[1]);
        assertEq(token.balanceOf(claimant) - balAfterFirst, _net(POOL), "second claim must pay from p2 backing");
    }

    function test_EmergencyWithdrawCannotTouchPoolBacking() public {
        _createPool();
        // Surplus above the reserve is withdrawable; the reserve is not.
        token.transfer(address(distributor), 100e18);
        distributor.emergencyWithdraw(address(token), 100e18);
        vm.expectRevert();
        distributor.emergencyWithdraw(address(token), POOL);
    }

    function test_PerformanceRewardBecomesClaimable() public {
        uint256 poolId = _createPool();
        distributor.createPerformanceReward(agent, 100e18, poolId);
        distributor.distributePerformanceReward(1);

        uint256[] memory claims = distributor.getUserClaims(agent);
        assertEq(claims.length, 1, "performance reward must create a real claim");

        uint256 balBefore = token.balanceOf(agent);
        vm.prank(agent);
        distributor.claimReward(claims[0]);
        uint256 gained = token.balanceOf(agent) - balBefore;
        assertGt(gained, 0, "agent must actually receive tokens");
        assertEq(gained, _net(100e18), "payout bounded by reward amount minus fee");
    }

    function test_PerformanceRewardBeyondPoolReverts() public {
        uint256 poolId = _createPool();
        distributor.createPerformanceReward(agent, POOL + 1, poolId);
        vm.expectRevert();
        distributor.distributePerformanceReward(1);
    }
}
