// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/EscrowService.sol";
import "../../contracts/AIToken.sol";

contract EscrowServiceFuzzTest is Test {
    EscrowService public escrow;
    AIToken public paymentToken;
    address public client;
    address public provider;

    function setUp() public {
        client = makeAddr("client");
        provider = makeAddr("provider");

        paymentToken = new AIToken(0);
        vm.warp(block.timestamp + 2 days); // AIToken enforces a 1-day minting cooldown
        escrow = new EscrowService(address(paymentToken), address(1), address(2));
    }

    function invariant_balanceInvariant() public {
        assertEq(address(escrow).balance, 0, "Escrow should hold no stray ETH after operations");
    }

    function testFuzz_EscrowFlow(uint256 amount) public {
        amount = bound(amount, escrow.minEscrowAmount(), escrow.maxEscrowAmount());
        uint256 total = amount + (amount * escrow.platformFeePercentage()) / 10000;

        paymentToken.mint(client, total);

        vm.startPrank(client);
        paymentToken.approve(address(escrow), total);
        uint256 escrowId = escrow.createEscrow(
            provider,
            address(0),
            amount,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.Manual,
            0,
            "fuzz"
        );
        vm.stopPrank();

        (address depositor, address beneficiary, , uint256 storedAmount, , , , bool isReleased, bool isRefunded) =
            escrow.getEscrowAccount(escrowId);

        assertEq(depositor, client);
        assertEq(beneficiary, provider);
        assertEq(storedAmount, amount);
        assertFalse(isReleased);
        assertFalse(isRefunded);
        assertEq(paymentToken.balanceOf(address(escrow)), total);
    }
}
