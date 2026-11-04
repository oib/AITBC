// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/DynamicPricing.sol";

/// #1121 pins: price alerts are capped per subscriber, cancellable, and the
/// update-time scan is bounded — a spammed alert queue can no longer
/// gas-starve updateMarketData and freeze the oracle price feed.
contract DynamicPricing1121Test is Test {
    DynamicPricing pricing;
    address oracle = address(0x0A);
    address sub1 = address(0xB1);
    address sub2 = address(0xB2);
    address sub3 = address(0xB3);

    function setUp() public {
        pricing = new DynamicPricing(address(0), address(0), address(0));
        pricing.authorizePriceOracle(oracle);
    }

    function _update() internal {
        vm.prank(oracle);
        pricing.updateMarketData(1000, 900, 10, 5, 1e6, 100, 50, 90, 50);
    }

    function _spam(address sub, uint256 n) internal {
        for (uint256 i = 0; i < n; i++) {
            pricing.createPriceAlert(sub, DynamicPricing.PriceAlertType.PriceAbove, 1, "x");
        }
    }

    function test_AlertCapPerSubscriber() public {
        _spam(sub1, pricing.MAX_ALERTS_PER_SUBSCRIBER());
        assertEq(pricing.subscriberAlertCount(sub1), 50);
        vm.expectRevert("Alert cap reached");
        pricing.createPriceAlert(sub1, DynamicPricing.PriceAlertType.PriceAbove, 1, "x");
    }

    function test_CancelBySubscriberRemovesAndFreesSlot() public {
        uint256 id = pricing.createPriceAlert(sub1, DynamicPricing.PriceAlertType.PriceAbove, 1, "x");
        vm.prank(sub1);
        pricing.cancelPriceAlert(id);
        assertEq(pricing.activePriceAlertCount(), 0);
        assertEq(pricing.subscriberAlertCount(sub1), 0);
        // slot freed: subscriber can alert again
        pricing.createPriceAlert(sub1, DynamicPricing.PriceAlertType.PriceAbove, 1, "x");
        assertEq(pricing.activePriceAlertCount(), 1);
    }

    function test_CancelByStrangerReverts() public {
        uint256 id = pricing.createPriceAlert(sub1, DynamicPricing.PriceAlertType.PriceAbove, 1, "x");
        vm.prank(sub2);
        vm.expectRevert("Not alert subscriber");
        pricing.cancelPriceAlert(id);
    }

    function test_BoundedScanKeepsUpdateAlive() public {
        // 150 triggering alerts across 3 subscribers — more than one update's
        // batch (100) — must not stall the oracle update.
        _spam(sub1, 50);
        _spam(sub2, 50);
        _spam(sub3, 50);

        _update(); // used to iterate all 150+; now bounded
        assertEq(pricing.alertCheckCursor(), 100);
        _update(); // next batch of 100 wraps around the ring
        assertEq(pricing.alertCheckCursor(), 50);

        // every alert got its trigger across the two updates
        uint256 triggered;
        for (uint256 i = 0; i < 150; i++) {
            (, , , , , , uint256 lastTriggered, ) = pricing.priceAlerts(i);
            if (lastTriggered > 0) triggered++;
        }
        assertEq(triggered, 150);
        assertGt(pricing.getMarketPrice(address(0), ""), 0, "oracle price still served");
    }

    function test_CancelRemovesFromMiddleOfQueue() public {
        _spam(sub1, 3);
        vm.prank(sub1);
        pricing.cancelPriceAlert(1); // middle entry swap-pops
        assertEq(pricing.activePriceAlertCount(), 2);
        assertEq(pricing.activePriceAlerts(1), 2); // last id moved into the gap
    }
}
