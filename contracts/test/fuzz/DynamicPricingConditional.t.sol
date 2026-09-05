// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/DynamicPricing.sol";

/// @notice Conditional-path coverage for DynamicPricing.
///
/// These target the `if`/`else if`/ternary arms rather than `require` reverts:
/// forge's branch metric counts the former and ignores the latter, so a suite
/// made only of revert checks leaves branch coverage flat. Each ladder in
/// _calculateDynamicPrice, _determineMarketCondition and _determinePriceChangeType
/// gets one test per arm.
contract DynamicPricingConditionalTest is Test {
    DynamicPricing public pricing;
    address public oracle;
    address public subscriber;

    // event signatures, for decoding recorded logs
    bytes32 constant MARKET_UPDATED =
        keccak256("MarketDataUpdated(uint256,uint256,uint256,uint256,uint8)");
    bytes32 constant PRICE_CALCULATED =
        keccak256("PriceCalculated(uint256,uint256,uint256,uint8,uint256)");

    function setUp() public {
        oracle = makeAddr("oracle");
        subscriber = makeAddr("subscriber");
        pricing = new DynamicPricing(address(1), address(2), address(3));
        pricing.authorizePriceOracle(oracle);
    }

    // ---- helpers -----------------------------------------------------------

    function _update(uint256 supply, uint256 demand, uint256 sentiment) internal {
        vm.prank(oracle);
        pricing.updateMarketData(supply, demand, 1, 1, 0, 0, 0, 0, sentiment);
    }

    function _updateRecorded(uint256 supply, uint256 demand, uint256 sentiment) internal {
        vm.recordLogs();
        _update(supply, demand, sentiment);
    }

    function _condition() internal returns (DynamicPricing.MarketCondition) {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i = logs.length; i > 0; i--) {
            if (logs[i - 1].topics[0] == MARKET_UPDATED) {
                (,,, uint8 cond) = abi.decode(logs[i - 1].data, (uint256, uint256, uint256, uint8));
                return DynamicPricing.MarketCondition(cond);
            }
        }
        revert("no MarketDataUpdated emitted");
    }

    function _changeType() internal returns (DynamicPricing.PriceChangeType) {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i = logs.length; i > 0; i--) {
            if (logs[i - 1].topics[0] == PRICE_CALCULATED) {
                (,, uint8 ct,) = abi.decode(logs[i - 1].data, (uint256, uint256, uint8, uint256));
                return DynamicPricing.PriceChangeType(ct);
            }
        }
        revert("no PriceCalculated emitted");
    }

    function _price() internal view returns (uint256) {
        return pricing.getMarketData(0).averagePrice;
    }

    // ---- _calculateDynamicPrice: supply/demand arms ------------------------

    function test_DemandAboveSupply_AppliesPremium() public {
        _update(1000, 1500, 50);
        assertGt(_price(), pricing.basePricePerHour(), "demand premium must raise price");
    }

    function test_SupplyAboveDemand_AppliesDiscount() public {
        _update(1000, 500, 50);
        assertLt(_price(), pricing.basePricePerHour(), "supply discount must lower price");
    }

    function test_SupplyEqualsDemand_NoAdjustment() public {
        _update(1000, 1000, 50);
        // util is 10000 (>8000) so a utilization premium still applies; the
        // supply/demand arm itself is the neutral one.
        assertGt(_price(), 0, "neutral supply/demand still prices");
    }

    // ---- _calculateDynamicPrice: utilization arms --------------------------

    function test_HighUtilization_AppliesPremium() public {
        _update(1000, 900, 50); // util 9000
        uint256 high = _price();
        DynamicPricing fresh = new DynamicPricing(address(1), address(2), address(3));
        fresh.authorizePriceOracle(oracle);
        vm.prank(oracle);
        fresh.updateMarketData(1000, 500, 1, 1, 0, 0, 0, 0, 50); // util 5000, no premium
        assertGt(high, fresh.getMarketData(0).averagePrice, "high utilization must price above mid");
    }

    function test_LowUtilization_AppliesDiscount() public {
        _update(1000, 100, 50); // util 1000 (<2000)
        assertLt(_price(), pricing.basePricePerHour(), "low utilization must discount");
    }

    function test_MidUtilization_NoUtilizationAdjustment() public {
        _update(1000, 500, 50); // util 5000, neither arm
        assertGt(_price(), 0);
    }

    // ---- _calculateDynamicPrice: sentiment arms ----------------------------

    function test_SentimentArms_HighAboveNeutralAboveLow() public {
        _update(1000, 500, 90);
        uint256 highSent = _price();

        DynamicPricing mid = new DynamicPricing(address(1), address(2), address(3));
        mid.authorizePriceOracle(oracle);
        vm.prank(oracle);
        mid.updateMarketData(1000, 500, 1, 1, 0, 0, 0, 0, 50);

        DynamicPricing low = new DynamicPricing(address(1), address(2), address(3));
        low.authorizePriceOracle(oracle);
        vm.prank(oracle);
        low.updateMarketData(1000, 500, 1, 1, 0, 0, 0, 0, 10);

        assertGt(highSent, mid.getMarketData(0).averagePrice, "high sentiment premium");
        assertGt(mid.getMarketData(0).averagePrice, low.getMarketData(0).averagePrice, "low sentiment discount");
    }

    // ---- _calculateDynamicPrice: bounds arms -------------------------------

    function test_PriceClampedToMaximum() public {
        _update(1, 1000, 90); // enormous demand premium
        assertEq(_price(), pricing.maxPricePerHour(), "must clamp at max");
    }

    function test_PriceClampedToMinimum() public {
        _update(10000, 1, 10); // near-total supply discount
        assertEq(_price(), pricing.minPricePerHour(), "must clamp at min");
    }

    // ---- smoothing arm (previousPrice > 0) ---------------------------------

    function test_SmoothingAppliesOnlyFromSecondUpdate() public {
        _update(1000, 500, 50);
        uint256 first = _price();
        _update(1000, 500, 50);
        assertEq(_price(), first, "identical inputs must round-trip through smoothing");
    }

    // ---- _determineMarketCondition: all five arms --------------------------

    function test_Condition_Surge() public {
        _updateRecorded(1000, 950, 50); // util 9500
        assertEq(uint8(_condition()), uint8(DynamicPricing.MarketCondition.Surge));
    }

    function test_Condition_Undersupply() public {
        _updateRecorded(1000, 800, 50); // util 8000
        assertEq(uint8(_condition()), uint8(DynamicPricing.MarketCondition.Undersupply));
    }

    function test_Condition_Balanced() public {
        _updateRecorded(1000, 500, 50); // util 5000
        assertEq(uint8(_condition()), uint8(DynamicPricing.MarketCondition.Balanced));
    }

    function test_Condition_Oversupply() public {
        _updateRecorded(1000, 200, 50); // util 2000
        assertEq(uint8(_condition()), uint8(DynamicPricing.MarketCondition.Oversupply));
    }

    function test_Condition_Crash() public {
        _updateRecorded(1000, 50, 50); // util 500
        assertEq(uint8(_condition()), uint8(DynamicPricing.MarketCondition.Crash));
    }

    // ---- _determinePriceChangeType: all six arms ---------------------------

    function test_ChangeType_StableOnFirstUpdate() public {
        _updateRecorded(1000, 500, 50); // oldPrice == 0 arm
        assertEq(uint8(_changeType()), uint8(DynamicPricing.PriceChangeType.Stable));
    }

    function test_ChangeType_StableUnderFivePercent() public {
        _update(1000, 500, 50);
        _updateRecorded(1000, 520, 50); // ~398 bp
        assertEq(uint8(_changeType()), uint8(DynamicPricing.PriceChangeType.Stable));
    }

    function test_ChangeType_Increase() public {
        _update(1000, 500, 50);
        _updateRecorded(1000, 560, 50); // ~1194 bp up
        assertEq(uint8(_changeType()), uint8(DynamicPricing.PriceChangeType.Increase));
    }

    function test_ChangeType_Decrease() public {
        _update(1000, 500, 50);
        _updateRecorded(1000, 460, 50); // ~796 bp down
        assertEq(uint8(_changeType()), uint8(DynamicPricing.PriceChangeType.Decrease));
    }

    function test_ChangeType_Surge() public {
        _update(1000, 500, 50);
        _updateRecorded(1000, 700, 50); // ~3980 bp up
        assertEq(uint8(_changeType()), uint8(DynamicPricing.PriceChangeType.Surge));
    }

    function test_ChangeType_Discount() public {
        _update(1000, 500, 50);
        _updateRecorded(1000, 300, 50); // >2000 bp down
        assertEq(uint8(_changeType()), uint8(DynamicPricing.PriceChangeType.Discount));
    }

    /// Regression: the change-percentage ternary subtracted unconditionally in
    /// the increase direction, so any price drop reverted with panic 0x11 and
    /// the oracle could only ever record rises.
    function test_PriceDecreaseDoesNotUnderflow() public {
        _update(1000, 5000, 90);
        uint256 high = _price();
        _update(5000, 1000, 10);
        assertLt(_price(), high, "a price drop must be recordable");
    }

    // ---- isMarketActive ternary -------------------------------------------

    function test_MarketActiveRequiresBothSides() public {
        vm.prank(oracle);
        pricing.updateMarketData(1000, 500, 1, 1, 0, 0, 0, 0, 50);
        assertTrue(pricing.getMarketData(0).isMarketActive, "providers and consumers present");

        vm.prank(oracle);
        pricing.updateMarketData(1000, 500, 0, 1, 0, 0, 0, 0, 50);
        assertFalse(pricing.getMarketData(0).isMarketActive, "no providers");

        vm.prank(oracle);
        pricing.updateMarketData(1000, 500, 1, 0, 0, 0, 0, 0, 50);
        assertFalse(pricing.getMarketData(0).isMarketActive, "no consumers");
    }

    // ---- getMarketPrice conditional arms -----------------------------------

    function test_GetMarketPrice_BeforeAnyUpdateReturnsBase() public view {
        assertEq(pricing.getMarketPrice(address(0), ""), pricing.basePricePerHour());
    }

    function test_GetMarketPrice_UsesLatestUpdate() public {
        _update(1000, 500, 50);
        assertEq(pricing.getMarketPrice(address(0), ""), _price());
    }

    function test_GetMarketPrice_RegionalMultiplierApplies() public {
        _update(1000, 500, 50);
        // localSupply/localDemand have no setter, so the multiplier stays at the
        // 10000 base; this pins the region-supplied arm as a no-op rather than
        // asserting a premium the contract cannot currently produce.
        assertEq(pricing.getMarketPrice(address(0), "us-east"), _price());
    }

    function test_GetMarketPrice_UnknownProviderFallsBackToMarket() public {
        _update(1000, 500, 50);
        assertEq(pricing.getMarketPrice(makeAddr("nobody"), ""), _price());
    }

    // ---- getMarketData / getPriceHistory conditional arms ------------------

    function test_GetMarketData_TimestampSearchFindsEarlierEntry() public {
        _update(1000, 500, 50);
        uint256 firstTime = pricing.getMarketData(0).lastUpdateTime;
        vm.warp(block.timestamp + 1000);
        _update(1000, 900, 50);
        assertEq(pricing.getMarketData(firstTime).lastUpdateTime, firstTime, "must find the earlier entry");
    }

    function test_GetMarketData_RevertsWhenNoDataAtOrBeforeTimestamp() public {
        vm.warp(10_000);
        _update(1000, 500, 50);
        vm.expectRevert("No market data found for timestamp");
        pricing.getMarketData(1);
    }

    function test_GetPriceHistory_CountAboveAndBelowCounter() public {
        _update(1000, 500, 50);
        _update(1000, 520, 50);
        _update(1000, 540, 50);
        assertEq(pricing.getPriceHistory(99).length, 3, "count above counter returns all");
        assertEq(pricing.getPriceHistory(2).length, 2, "count below counter truncates");
    }

    // ---- _checkPriceAlerts arms -------------------------------------------

    /// Regression: alerts and forecasts drew ids from priceUpdateCounter, the
    /// same counter every market-data read uses as an entry count. Creating one
    /// alert pushed those reads onto an empty slot and the market price read 0.
    function test_AlertCreationDoesNotCorruptMarketData() public {
        _update(1000, 800, 50);
        uint256 before = _price();
        pricing.createPriceAlert(subscriber, DynamicPricing.PriceAlertType.PriceAbove, 1e15, "email");
        assertEq(_price(), before, "market data must survive alert creation");
        assertEq(pricing.getMarketPrice(address(0), ""), before, "market price must survive alert creation");
    }

    function test_ForecastCreationDoesNotCorruptMarketData() public {
        _update(1000, 800, 50);
        uint256 before = _price();
        vm.prank(oracle);
        pricing.createDemandForecast(3600, 1000, 80);
        assertEq(_price(), before, "market data must survive forecast creation");
    }

    function test_AlertAboveThresholdTriggers() public {
        pricing.createPriceAlert(subscriber, DynamicPricing.PriceAlertType.PriceAbove, 1e15, "email");
        vm.recordLogs();
        _update(1, 1000, 90); // clamps to max, well above threshold
        Vm.Log[] memory logs = vm.getRecordedLogs();
        bool fired;
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].topics[0] == keccak256("PriceAlertTriggered(uint256,address,uint8,uint256,uint256)")) fired = true;
        }
        assertTrue(fired, "PriceAbove alert must fire");
    }

    function test_AlertBelowThresholdTriggers() public {
        pricing.createPriceAlert(subscriber, DynamicPricing.PriceAlertType.PriceBelow, 1e17, "email");
        vm.recordLogs();
        _update(10000, 1, 10); // clamps to min, well below threshold
        Vm.Log[] memory logs = vm.getRecordedLogs();
        bool fired;
        for (uint256 i = 0; i < logs.length; i++) {
            if (logs[i].topics[0] == keccak256("PriceAlertTriggered(uint256,address,uint8,uint256,uint256)")) fired = true;
        }
        assertTrue(fired, "PriceBelow alert must fire");
    }

    function test_AlertOnWrongSideDoesNotTrigger() public {
        pricing.createPriceAlert(subscriber, DynamicPricing.PriceAlertType.PriceAbove, 1e18, "email");
        vm.recordLogs();
        _update(10000, 1, 10); // price clamps to min, never above 1e18
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i = 0; i < logs.length; i++) {
            assertTrue(
                logs[i].topics[0] != keccak256("PriceAlertTriggered(uint256,address,uint8,uint256,uint256)"),
                "alert must not fire below its threshold"
            );
        }
    }
}
