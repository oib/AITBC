// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/EscrowService.sol";
import "../../contracts/DynamicPricing.sol";
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

contract EscrowServiceProtectedTest is Test {
    EscrowService public escrow;
    DynamicPricing public energyPricing;
    AIToken public paymentToken;
    address public client;
    address public provider;
    address public publisher;

    function setUp() public {
        client = makeAddr("client");
        provider = makeAddr("provider");
        publisher = makeAddr("publisher");

        paymentToken = new AIToken(0);
        vm.warp(block.timestamp + 2 days);

        escrow = new EscrowService(address(paymentToken), address(1), address(2));
        energyPricing = new DynamicPricing(address(0), address(0), address(paymentToken));
        energyPricing.setEnergyPublisher(publisher);
        escrow.setEnergyPricing(address(energyPricing));
    }

    function test_ProtectedComputeEscrowFlow() public {
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

        uint256 amount = 200_000_000_000_000_000; // 0.2 AIT > floor
        uint256 platformFee = (amount * escrow.platformFeePercentage()) / 10000;
        uint256 totalAmount = amount + platformFee;
        paymentToken.mint(client, totalAmount);

        vm.startPrank(client);
        paymentToken.approve(address(escrow), totalAmount);
        uint256 escrowId = escrow.createComputeEscrow(
            provider,
            "gpu-001",
            "rtx-4060-ti",
            1,
            3600,
            amount,
            totalAmount,
            1_000_000_000_000_000_000
        );
        vm.stopPrank();

        (
            address depositor,
            address beneficiary,
            ,
            uint256 storedAmount,
            uint256 releaseTime,
            EscrowService.EscrowType escrowType,
            EscrowService.ReleaseCondition condition,
            bool released,
            bool refunded
        ) = escrow.getEscrowAccount(escrowId);
        assertEq(uint8(condition), uint8(EscrowService.ReleaseCondition.TimeBased));
        assertFalse(released);
        assertFalse(refunded);
        assertEq(depositor, client);
        assertEq(beneficiary, provider);
        assertEq(storedAmount, amount);
        assertEq(escrowType, EscrowService.EscrowType.ProtectedCompute);
        assertTrue(releaseTime > block.timestamp);
        assertEq(paymentToken.balanceOf(address(escrow)), totalAmount);

        EscrowService.ComputeEscrowTerms memory terms = escrow.computeEscrowTerms(escrowId);
        assertTrue(terms.isProtected);
        assertEq(terms.netEnergyFloor, 198_000_000_000_000_000);

        // Release after duration
        vm.warp(releaseTime + 1);
        vm.prank(provider);
        escrow.releaseEscrow(escrowId, "work completed");

        (,,,,,,, bool isReleased, bool isRefunded) = escrow.getEscrowAccount(escrowId);
        assertTrue(isReleased);
        assertFalse(isRefunded);
        assertEq(paymentToken.balanceOf(provider), amount);
    }

    function test_ProtectedComputeEscrow_BelowFloorReverts() public {
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

        uint256 amount = 100_000_000_000_000_000; // below floor
        uint256 platformFee = (amount * escrow.platformFeePercentage()) / 10000;
        uint256 totalAmount = amount + platformFee;
        paymentToken.mint(client, totalAmount);

        vm.startPrank(client);
        paymentToken.approve(address(escrow), totalAmount);
        vm.expectRevert();
        escrow.createComputeEscrow(
            provider,
            "gpu-001",
            "rtx-4060-ti",
            1,
            3600,
            amount,
            totalAmount,
            1_000_000_000_000_000_000
        );
        vm.stopPrank();
    }

    function test_ProtectedComputeEscrow_RefundBeforeRelease() public {
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

        uint256 amount = 200_000_000_000_000_000;
        uint256 platformFee = (amount * escrow.platformFeePercentage()) / 10000;
        uint256 totalAmount = amount + platformFee;
        paymentToken.mint(client, totalAmount);

        vm.startPrank(client);
        paymentToken.approve(address(escrow), totalAmount);
        uint256 escrowId = escrow.createComputeEscrow(
            provider,
            "gpu-001",
            "rtx-4060-ti",
            1,
            3600,
            amount,
            totalAmount,
            1_000_000_000_000_000_000
        );
        escrow.refundEscrow(escrowId, "cancelled");
        vm.stopPrank();

        (,,,,,,, bool isReleased, bool isRefunded) = escrow.getEscrowAccount(escrowId);
        assertFalse(isReleased);
        assertTrue(isRefunded);
        assertEq(paymentToken.balanceOf(client), totalAmount);
    }
}
