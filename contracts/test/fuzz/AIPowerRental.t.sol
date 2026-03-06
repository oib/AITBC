// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/AIPowerRental.sol";

contract AIPowerRentalFuzzTest is Test {
    AIPowerRental public rental;
    address public owner;
    address public provider;
    address payable public renter;

    function setUp() public {
        owner = address(this);
        provider = makeAddr("provider");
        renter = payable(makeAddr("renter"));
        rental = new AIPowerRental();
    }

    function invariant_balanceInvariant() public {
        assertEq(address(rental).balance, 0, "Contract should hold no stray ETH");
    }

    function testFuzz_RentalFlow(uint256 duration, uint256 price) public {
        vm.assume(duration > 0 && duration <= 365 days);
        vm.assume(price >= 0.001 ether && price <= 10 ether);
        
        uint256 rentAmount = price * duration / 1 days;
        vm.deal(renter, rentAmount + 1 ether);
        
        vm.prank(provider);
        rental.createRental(price, duration);
        
        uint256 rentalId = 0;
        vm.prank(renter);
        rental.startRental{value: rentAmount}(rentalId);
        
        assertEq(rental.getRentalEnd(rentalId), block.timestamp + duration);
    }
}
