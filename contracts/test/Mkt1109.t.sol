// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/AgentMarketplaceV2.sol";
import "../contracts/AIToken.sol";

/// #1109 pins: purchaseCall/subscribeToCapability took no maxPrice (a price
/// raised between quote and purchase overcharged the buyer), and
/// checkSubscription answered "is this sub live" without binding it to the
/// service or the subscriber — a sub for one capability could be presented as
/// access to another.
contract Mkt1109Test is Test {
    AIToken token;
    AgentMarketplaceV2 market;
    address provider = makeAddr("provider");
    address buyer = makeAddr("buyer");

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days);
        market = new AgentMarketplaceV2(address(token));
        token.mint(buyer, 100e18);
        vm.prank(buyer);
        token.approve(address(market), 100e18);
        vm.prank(provider);
        token.approve(address(market), 100e18);
    }

    function _list(uint256 price, bool subs) internal returns (uint256 id) {
        vm.prank(provider);
        id = market.listCapability("QmX", price, 5e18, subs);
    }

    function test_MaxPriceBoundsPurchase() public {
        uint256 id = _list(10e18, true);
        vm.prank(buyer);
        vm.expectRevert("Price above maxPrice");
        market.purchaseCall(id, 9e18);
        vm.prank(buyer);
        market.purchaseCall(id, 10e18); // at the bound: ok
        assertGt(token.balanceOf(provider), 0);
    }

    function test_MaxPriceBoundsSubscribe() public {
        uint256 id = _list(1e18, true); // subscriptionPrice 5e18
        vm.prank(buyer);
        vm.expectRevert("Price above maxPrice");
        market.subscribeToCapability(id, 4e18);
        vm.prank(buyer);
        market.subscribeToCapability(id, 5e18);
    }

    function test_CheckSubscriptionBoundToServiceAndCaller() public {
        uint256 idA = _list(1e18, true);
        vm.prank(provider);
        uint256 idB = market.listCapability("QmY", 1e18, 5e18, true);
        vm.startPrank(buyer);
        uint256 subA = market.subscribeToCapability(idA, type(uint256).max);
        vm.stopPrank();
        // Wrong capability id -> false.
        vm.prank(buyer);
        assertFalse(market.checkSubscription(idB, subA));
        // Right capability -> true for the subscriber.
        vm.prank(buyer);
        assertTrue(market.checkSubscription(idA, subA));
        // A stranger cannot present the sub as theirs.
        address stranger = makeAddr("stranger");
        vm.prank(stranger);
        assertFalse(market.checkSubscription(idA, subA));
    }
}
