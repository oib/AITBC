// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/DynamicPricing.sol";

contract DynamicPricingFuzzTest is Test {
    DynamicPricing public pricing;
    address public owner;
    address public provider;

    function setUp() public {
        owner = address(this);
        provider = makeAddr("provider");
        pricing = new DynamicPricing();
        vm.prank(owner);
        pricing.addProvider(provider);
    }

    function invariant_noNegativePrice() public {
        uint256 price = pricing.getCurrentPrice(provider);
        assertGe(price, 0, "Price should never be negative");
    }

    function testFuzz_PriceAdjustment(uint256 basePrice, uint256 utilization) public {
        vm.assume(basePrice >= 0.001 ether && basePrice <= 10 ether);
        vm.assume(utilization >= 0 && utilization <= 10000); // basis points

        vm.prank(provider);
        pricing.setBasePrice(basePrice);

        vm.prank(owner);
        pricing.updateUtilization(provider, utilization);

        uint256 price = pricing.getCurrentPrice(provider);
        assertGe(price, 0, "Adjusted price must be non-negative");
    }
}
