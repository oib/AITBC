// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/AIPowerRental.sol";
import "../../contracts/DynamicPricing.sol";
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

contract AIPowerRentalProtectedTest is Test {
    AIPowerRental public rental;
    DynamicPricing public energyPricing;
    AIToken public paymentToken;
    address public provider;
    address public renter;
    address public publisher;
    address public owner;

    function setUp() public {
        owner = address(this);
        provider = makeAddr("provider");
        renter = makeAddr("renter");
        publisher = makeAddr("publisher");

        paymentToken = new AIToken(0);
        vm.warp(block.timestamp + 2 days);

        ZKReceiptVerifier zkVerifier = new ZKReceiptVerifier();
        Groth16Verifier groth16Verifier = new Groth16Verifier();
        rental = new AIPowerRental(
            address(paymentToken),
            address(zkVerifier),
            address(groth16Verifier)
        );

        energyPricing = new DynamicPricing(address(0), address(0), address(paymentToken));
        energyPricing.setEnergyPublisher(publisher);
        rental.setEnergyPricing(address(energyPricing));

        rental.authorizeProvider(provider);
        rental.authorizeConsumer(renter);
    }

    function test_ProtectedRentalFlow() public {
        energyPricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );
        vm.prank(publisher);
        energyPricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        uint256 price = 200_000_000_000_000_000;
        uint256 platformFee = (price * rental.platformFeePercentage()) / 10000;
        uint256 totalAmount = price + platformFee;
        paymentToken.mint(renter, totalAmount);

        vm.startPrank(renter);
        uint256 agreementId = rental.createProtectedRental(
            provider,
            renter,
            "gpu-001",
            "rtx-4060-ti",
            1,
            3600,
            price,
            totalAmount,
            1_000_000_000_000_000_000
        );
        paymentToken.approve(address(rental), totalAmount);
        rental.startRental(agreementId);
        vm.stopPrank();

        AIPowerRental.RentalAgreement memory agreement = rental.getRentalAgreement(agreementId);
        assertEq(uint8(agreement.status), uint8(AIPowerRental.RentalStatus.Active));
        assertEq(agreement.price, price);

        AIPowerRental.RentalEnergyTerms memory terms = rental.rentalEnergyTerms(agreementId);
        assertTrue(terms.isProtected);
        assertEq(terms.netEnergyFloor, 198_000_000_000_000_000);
        assertEq(paymentToken.balanceOf(address(rental)), totalAmount);
    }

    function test_ProtectedRental_BelowFloorReverts() public {
        energyPricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );
        vm.prank(publisher);
        energyPricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        uint256 price = 100_000_000_000_000_000; // below floor
        uint256 platformFee = (price * rental.platformFeePercentage()) / 10000;
        uint256 totalAmount = price + platformFee;
        paymentToken.mint(renter, totalAmount);

        vm.startPrank(renter);
        vm.expectRevert();
        rental.createProtectedRental(
            provider,
            renter,
            "gpu-001",
            "rtx-4060-ti",
            1,
            3600,
            price,
            totalAmount,
            1_000_000_000_000_000_000
        );
        vm.stopPrank();
    }

    function test_ProtectedRental_StaleRateAtStartReverts() public {
        energyPricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );
        vm.prank(publisher);
        energyPricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        uint256 price = 200_000_000_000_000_000;
        uint256 platformFee = (price * rental.platformFeePercentage()) / 10000;
        uint256 totalAmount = price + platformFee;
        paymentToken.mint(renter, totalAmount);

        vm.startPrank(renter);
        uint256 agreementId = rental.createProtectedRental(
            provider,
            renter,
            "gpu-001",
            "rtx-4060-ti",
            1,
            3600,
            price,
            totalAmount,
            1_000_000_000_000_000_000
        );
        paymentToken.approve(address(rental), totalAmount);
        vm.warp(block.timestamp + 301);
        vm.expectRevert();
        rental.startRental(agreementId);
        vm.stopPrank();
    }
}
