// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/EscrowService.sol";

contract EscrowServiceFuzzTest is Test {
    EscrowService public escrow;
    address public owner;
    address public provider;
    address payable public client;

    function setUp() public {
        owner = address(this);
        provider = makeAddr("provider");
        client = payable(makeAddr("client"));
        escrow = new EscrowService();
    }

    function invariant_balanceInvariant() public {
        assertEq(address(escrow).balance, 0, "Escrow should hold no stray ETH after operations");
    }

    function testFuzz_EscrowFlow(uint256 amount) public {
        vm.assume(amount >= 0.01 ether && amount <= 100 ether);
        vm.deal(client, amount + 1 ether);

        vm.prank(client);
        escrow.deposit{value: amount}(provider);
        assertEq(escrow.getBalance(provider), amount);

        vm.prank(owner);
        escrow.release(provider, client);
        assertEq(escrow.getBalance(provider), 0);
    }
}
