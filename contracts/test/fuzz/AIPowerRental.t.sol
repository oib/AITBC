// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/AIPowerRental.sol";
import "../../contracts/ZKReceiptVerifier.sol";
import "../../contracts/Groth16Verifier.sol";
import "../../contracts/AIToken.sol";

contract AIPowerRentalFuzzTest is Test {
    AIPowerRental public rental;
    AIToken public paymentToken;
    address public provider;
    address public renter;

    function setUp() public {
        provider = makeAddr("provider");
        renter = makeAddr("renter");

        paymentToken = new AIToken(0);
        vm.warp(block.timestamp + 2 days); // AIToken enforces a 1-day minting cooldown
        ZKReceiptVerifier zkVerifier = new ZKReceiptVerifier();
        Groth16Verifier groth16Verifier = new Groth16Verifier();
        rental = new AIPowerRental(
            address(paymentToken),
            address(zkVerifier),
            address(groth16Verifier)
        );

        rental.authorizeProvider(provider);
        rental.authorizeConsumer(renter);
    }

    function invariant_balanceInvariant() public {
        assertEq(address(rental).balance, 0, "Contract should hold no stray ETH");
    }

    function testFuzz_RentalFlow(uint256 duration, uint256 price) public {
        duration = bound(duration, rental.minRentalDuration(), rental.maxRentalDuration());
        price = bound(price, 1, 1_000_000 ether);

        uint256 totalAmount = price + (price * rental.platformFeePercentage()) / 10000;
        paymentToken.mint(renter, totalAmount);

        vm.startPrank(renter);
        uint256 agreementId = rental.createRental(provider, renter, duration, price, "GPU", 1);
        paymentToken.approve(address(rental), totalAmount);
        rental.startRental(agreementId);
        vm.stopPrank();

        AIPowerRental.RentalAgreement memory agreement = rental.getRentalAgreement(agreementId);
        assertEq(agreement.endTime, agreement.startTime + duration);
        assertEq(uint8(agreement.status), uint8(AIPowerRental.RentalStatus.Active));
    }
}
