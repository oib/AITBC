// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/BountyIntegration.sol";
import "../contracts/AIToken.sol";

/// #1114 pins: _processMappingInternal is self-call only, and the batch
/// actually marks each mapping's status instead of leaving PENDING forever.
contract BountyIntegration1114Test is Test {
    BountyIntegration integration;
    AIToken paymentToken;
    address integrator = address(0x1);

    function setUp() public {
        paymentToken = new AIToken(0);
        // Stand-ins: inner calls revert on undeployed addresses, which the
        // processing path records as FAILED — perfect for pinning the status
        // write without a full bounty/staking fixture.
        integration = new BountyIntegration(address(0xA1), address(0xA2), address(0xA3), address(paymentToken));
        integration.authorizeIntegrator(integrator);
    }

    function test_ProcessMappingInternalRejectsDirectCallers() public {
        vm.prank(integrator);
        uint256 mid = integration.mapPerformanceToBounty(keccak256("h"), 1, 1);

        vm.expectRevert("self-call only");
        integration._processMappingInternal(mid);
    }

    function test_BatchMarksMappingStatus() public {
        vm.startPrank(integrator);
        uint256 mid = integration.mapPerformanceToBounty(keccak256("h"), 1, 1);
        uint256[] memory ids = new uint256[](1);
        ids[0] = mid;
        integration.processBatchMappings(ids);
        vm.stopPrank();

        // used to stay PENDING forever — the batch never wrote the mapping row
        (, , , BountyIntegration.IntegrationStatus st, , , ) = integration.getPerformanceMapping(mid);
        assertEq(uint256(st), uint256(BountyIntegration.IntegrationStatus.FAILED));
    }
}
