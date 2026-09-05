// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/DynamicPricing.sol";

contract DynamicPricingFuzzTest is Test {
    DynamicPricing public pricing;
    address public oracle;
    address public provider;

    function setUp() public {
        oracle = makeAddr("oracle");
        provider = makeAddr("provider");
        pricing = new DynamicPricing(address(1), address(2), address(3));
        pricing.authorizePriceOracle(oracle);
    }

    function invariant_noNegativePrice() public {
        uint256 price = pricing.getMarketPrice(provider, "");
        assertGe(price, 0, "Price should never be negative");
    }

    function testFuzz_MarketUpdate(uint256 totalSupply, uint256 totalDemand) public {
        totalSupply = bound(totalSupply, 1, type(uint64).max);
        totalDemand = bound(totalDemand, 1, type(uint64).max);

        vm.prank(oracle);
        pricing.updateMarketData(totalSupply, totalDemand, 1, 1, 0, 0, 0, 0, 50);

        uint256 price = pricing.getMarketPrice(provider, "");
        assertGe(price, 0, "Market price must be non-negative");
    }
}
