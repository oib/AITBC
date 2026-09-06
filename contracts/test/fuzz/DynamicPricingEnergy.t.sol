// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/DynamicPricing.sol";

contract DynamicPricingEnergyTest is Test {
    DynamicPricing public pricing;
    address public publisher;
    address public provider;

    function setUp() public {
        publisher = makeAddr("publisher");
        provider = makeAddr("provider");
        pricing = new DynamicPricing(address(1), address(2), address(3));
        pricing.setEnergyPublisher(publisher);
    }

    function test_RegisterAndGetProfile() public {
        pricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );

        (
            bool enabled,
            uint256 revision,
            string memory modelId,
            address p,
            uint256 tdpWatts,
            uint256 eurPerKwh
        ) = pricing.getEnergyProfile("gpu-001");

        assertTrue(enabled);
        assertEq(revision, 1);
        assertEq(modelId, "rtx-4060-ti");
        assertEq(p, provider);
        assertEq(tdpWatts, 165);
        assertEq(eurPerKwh, 300_000_000_000_000_000);
    }

    function test_PublishAndGetRate() public {
        vm.prank(publisher);
        pricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        (
            bool enabled,
            uint256 version,
            uint256 aitPerEur,
            uint256 observedAt,
            uint256 submittedAt,
            string memory sourceKind
        ) = pricing.getEnergyRate();

        assertTrue(enabled);
        assertEq(version, 1);
        assertEq(aitPerEur, 4_000_000_000_000_000_000);
        assertEq(observedAt, block.timestamp);
        assertEq(submittedAt, block.timestamp);
        assertEq(sourceKind, "operator_reference");
    }

    function test_GetEnergyFloor_NativeUnits() public {
        pricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );
        vm.prank(publisher);
        pricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        (uint256 netFloor, bool valid, string memory reason) = pricing.getEnergyFloor(
            "gpu-001",
            1,
            3600,
            36_000_000
        );

        assertTrue(valid, reason);
        assertEq(netFloor, 7_128_000);
    }

    function test_GetEnergyFloor_EvmUnits() public {
        pricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );
        vm.prank(publisher);
        pricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        (uint256 netFloor, bool valid, string memory reason) = pricing.getEnergyFloor(
            "gpu-001",
            1,
            3600,
            1_000_000_000_000_000_000
        );

        assertTrue(valid, reason);
        assertEq(netFloor, 198_000_000_000_000_000);
    }

    function test_GetEnergyFloor_MissingProfile() public {
        (uint256 netFloor, bool valid, ) = pricing.getEnergyFloor(
            "missing",
            1,
            3600,
            1_000_000_000_000_000_000
        );
        assertFalse(valid);
        assertEq(netFloor, 0);
    }

    function test_GetEnergyFloor_StaleRate() public {
        pricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );
        vm.prank(publisher);
        pricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        vm.warp(block.timestamp + 301);
        (uint256 netFloor, bool valid, ) = pricing.getEnergyFloor(
            "gpu-001",
            1,
            3600,
            1_000_000_000_000_000_000
        );
        assertFalse(valid);
        assertEq(netFloor, 0);
    }

    function test_ProviderSetResourceTariff() public {
        pricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );

        vm.prank(provider);
        pricing.setResourceTariff("gpu-001", 400_000_000_000_000_000);

        (, uint256 revision, , , , uint256 eurPerKwh) = pricing.getEnergyProfile("gpu-001");
        assertEq(revision, 2);
        assertEq(eurPerKwh, 400_000_000_000_000_000);
    }

    function test_ProviderSetResourceTariff_Unauthorized() public {
        pricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );

        address attacker = makeAddr("attacker");
        vm.prank(attacker);
        vm.expectRevert();
        pricing.setResourceTariff("gpu-001", 400_000_000_000_000_000);
    }

    function test_GetEnergyFloor_InvalidGpuCount() public {
        pricing.registerEnergyProfile(
            "gpu-001",
            provider,
            "rtx-4060-ti",
            165,
            300_000_000_000_000_000
        );
        vm.prank(publisher);
        pricing.publishEnergyRate(
            4_000_000_000_000_000_000,
            block.timestamp,
            "operator_reference"
        );

        (uint256 netFloor, bool valid, ) = pricing.getEnergyFloor(
            "gpu-001",
            0,
            3600,
            1_000_000_000_000_000_000
        );
        assertFalse(valid);
        assertEq(netFloor, 0);
    }
}
