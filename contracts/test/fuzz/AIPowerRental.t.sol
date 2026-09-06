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

        AIPowerRental.RentalEnergyTerms memory terms = rental.getRentalEnergyTerms(agreementId);
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

    function test_LegacyRentalBlockedWhenRequireProtected() public {
        // When requireProtectedRentals is true, createRental is blocked.
        rental.setRequireProtectedRentals(true);
        uint256 price = 1 ether;
        uint256 totalAmount = price + (price * rental.platformFeePercentage()) / 10000;
        paymentToken.mint(renter, totalAmount);

        vm.startPrank(renter);
        vm.expectRevert("Legacy rentals disabled; use createProtectedRental");
        rental.createRental(provider, renter, 3600, price, "GPU", 1);
        vm.stopPrank();
    }

    function test_LegacyRentalAllowedWhenNotRequired() public {
        // When requireProtectedRentals is false (default), createRental works.
        assertFalse(rental.requireProtectedRentals());
        uint256 price = 1 ether;
        uint256 totalAmount = price + (price * rental.platformFeePercentage()) / 10000;
        paymentToken.mint(renter, totalAmount);

        vm.startPrank(renter);
        uint256 agreementId = rental.createRental(provider, renter, 3600, price, "GPU", 1);
        vm.stopPrank();
        assertLt(agreementId, rental.agreementCounter());
    }

    function test_StartRentalRevertsWhenPaused() public {
        // startRental should revert when the contract is paused.
        uint256 price = 1 ether;
        uint256 totalAmount = price + (price * rental.platformFeePercentage()) / 10000;
        paymentToken.mint(renter, totalAmount);

        vm.startPrank(renter);
        uint256 agreementId = rental.createRental(provider, renter, 3600, price, "GPU", 1);
        paymentToken.approve(address(rental), totalAmount);
        vm.stopPrank();

        rental.pause(); // owner (address(this)) pauses
        vm.prank(renter);
        vm.expectRevert("Pausable: paused");
        rental.startRental(agreementId);
    }
}

contract AIPowerRentalOverflowTest is Test {
    DynamicPricing public energyPricing;
    AIToken public paymentToken;
    address public provider;
    address public publisher;

    function setUp() public {
        provider = makeAddr("provider");
        publisher = makeAddr("publisher");
        paymentToken = new AIToken(0);
        vm.warp(block.timestamp + 2 days);
        energyPricing = new DynamicPricing(address(0), address(0), address(paymentToken));
        energyPricing.setEnergyPublisher(publisher);
    }

    function test_GetEnergyFloorMaxValuesNoOverflow() public {
        // Register a profile with extreme but valid values to test that
        // getEnergyFloor does not overflow with mulDiv intermediates.
        energyPricing.registerEnergyProfile(
            "gpu-extreme",
            provider,
            "extreme-gpu",
            50000, // MAX_TDP_WATTS
            1_000_000 * 1e18 // MAX_EUR_PER_KWH_WHOLE * SCALE
        );
        vm.prank(publisher);
        energyPricing.publishEnergyRate(
            1_000_000_000 * 1e18, // MAX_AIT_PER_EUR_WHOLE * SCALE
            block.timestamp,
            "operator_reference"
        );

        (uint256 netFloor, bool valid, ) = energyPricing.getEnergyFloor(
            "gpu-extreme",
            10000, // MAX_GPU_COUNT
            86400 * 365, // MAX_DURATION_SECONDS
            1e36 // MAX_SETTLEMENT_UNIT_SCALE
        );
        assertTrue(valid);
        assertGt(netFloor, 0);
        // The result must fit in uint256 (no revert from overflow).
    }

    function test_GetEnergyFloorMatchesPythonArithmetic() public {
        // Reference vector: 165W, 0.30 EUR/kWh, 1 GPU, 3600s, 4 AIT/EUR, 1e18 scale
        energyPricing.registerEnergyProfile(
            "gpu-ref",
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

        (uint256 netFloor, bool valid, ) = energyPricing.getEnergyFloor(
            "gpu-ref",
            1,
            3600,
            1e18
        );
        assertTrue(valid);
        // Python: ceil(165 * 1 * 3600 * 3e17 * 4e18 * 1e18 / (1000 * 3600 * 1e18 * 1e18))
        // = ceil(165 * 3e17 * 4e18 * 1e18 / (1000 * 1e18 * 1e18))
        // = ceil(165 * 12e53 / 1e39)
        // = ceil(1980e14) = 198_000_000_000_000_000
        assertEq(netFloor, 198_000_000_000_000_000);
    }
}

contract AIPowerRentalPinnedFloorTest is Test {
    AIPowerRental public rental;
    DynamicPricing public energyPricing;
    AIToken public paymentToken;
    address public provider;
    address public renter;
    address public publisher;

    function setUp() public {
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
    }

    function test_StartRentalUsesPinnedFloorNotRecomputed() public {
        // §5.1: Create a protected rental at the current floor, then raise the
        // rate before startRental. The pinned floor from creation should be
        // used, not the new (higher) floor. If startRental re-prices, the
        // previously-valid agreement would be rejected.
        uint256 price = 200_000_000_000_000_000; // above the floor
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
        vm.stopPrank();

        // Raise the rate significantly — the new floor would be much higher.
        vm.prank(publisher);
        energyPricing.publishEnergyRate(
            100_000_000_000_000_000_000, // 100 AIT/EUR, up from 4
            block.timestamp,
            "operator_reference"
        );

        // startRental should still succeed because it uses the pinned floor
        // from creation, not the new (higher) recomputed floor.
        vm.startPrank(renter);
        paymentToken.approve(address(rental), totalAmount);
        rental.startRental(agreementId);
        vm.stopPrank();

        AIPowerRental.RentalAgreement memory agreement = rental.getRentalAgreement(agreementId);
        assertEq(uint8(agreement.status), uint8(AIPowerRental.RentalStatus.Active));
    }

    function test_StartRentalRevertsOnInsufficientBalance() public {
        // §5.4: startRental should revert with a clear message when the buyer
        // has insufficient token balance.
        uint256 price = 200_000_000_000_000_000;
        uint256 platformFee = (price * rental.platformFeePercentage()) / 10000;
        uint256 totalAmount = price + platformFee;
        // Mint less than required
        paymentToken.mint(renter, totalAmount - 1);

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
        vm.expectRevert("Insufficient token balance");
        rental.startRental(agreementId);
        vm.stopPrank();
    }

    function test_StartRentalRevertsOnInsufficientAllowance() public {
        // §5.4: startRental should revert with a clear message when the buyer
        // has insufficient allowance.
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
        // Approve less than required
        paymentToken.approve(address(rental), totalAmount - 1);
        vm.expectRevert("Insufficient token allowance");
        rental.startRental(agreementId);
        vm.stopPrank();
    }
}
