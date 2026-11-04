// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/DisputeResolution.sol";
import "../contracts/AIPowerRental.sol";
import "../contracts/ZKReceiptVerifier.sol";
import "../contracts/Groth16Verifier.sol";
import "../contracts/AIToken.sol";

/// #1108 pins: deadline resolution path, confidence bound, duplicate
/// arbitrator rejection, vote reset on escalation, and the resolution
/// actually moving funds through the rental.
contract DisputeResolution1108Test is Test {
    DisputeResolution disputes_;
    AIPowerRental rental;
    AIToken token;
    address provider = makeAddr("provider");
    address consumer = makeAddr("consumer");
    address arb1 = makeAddr("arb1");
    address arb2 = makeAddr("arb2");
    address arb3 = makeAddr("arb3");
    uint256 agreementId;

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days);
        ZKReceiptVerifier zkv = new ZKReceiptVerifier();
        Groth16Verifier g16 = new Groth16Verifier();
        rental = new AIPowerRental(address(token), address(zkv), address(g16));
        rental.authorizeProvider(provider);
        rental.authorizeConsumer(consumer);

        // DisputeResolution must own the rental so its resolveDispute call lands.
        disputes_ = new DisputeResolution(address(rental), address(0xB1), address(0xB2));
        disputes_.authorizeArbitrator(arb1, 100);
        disputes_.authorizeArbitrator(arb2, 100);
        disputes_.authorizeArbitrator(arb3, 100);

        // Fund + activate the rental and file the rental-side dispute record.
        token.mint(consumer, 200e18);
        vm.prank(consumer);
        agreementId = rental.createRental(provider, consumer, 1 days, 100e18, "GPU", 1);
        vm.startPrank(consumer);
        token.approve(address(rental), 200e18);
        rental.startRental(agreementId);
        vm.stopPrank();
        vm.prank(provider);
        rental.disputeRental(agreementId, "bad service");

        // File the dispute-panel record for the same agreement.
        vm.prank(provider);
        disputes_.fileDispute(agreementId, consumer, DisputeResolution.DisputeType.ServiceQuality, "bad service", keccak256("e"));

        // The rental's resolveDispute is onlyOwner — hand ownership to the panel contract.
        rental.transferOwnership(address(disputes_));
    }

    function _assign() internal {
        address[] memory arbs = new address[](3);
        arbs[0] = arb1; arbs[1] = arb2; arbs[2] = arb3;
        disputes_.assignArbitrators(0, arbs);
    }

    function test_DeadlinePathResolvesWithoutFullPanel() public {
        _assign();
        vm.prank(arb1);
        disputes_.submitArbitrationVote(0, true, 80, "clear");
        // one of three votes cast — the dispute used to stall here forever
        vm.warp(block.timestamp + 11 days);
        disputes_.resolveDisputeAfterDeadline(0);
        (, , , , DisputeResolution.DisputeStatus st, , , , , , ) = disputes_.getDispute(0);
        assertEq(uint256(st), uint256(DisputeResolution.DisputeStatus.Resolved));
        // and the decision moved funds: initiator wins → consumer refunded 100e18
        assertGe(token.balanceOf(consumer), 100e18);
    }

    function test_DeadlinePathRejectsEarlyCall() public {
        _assign();
        vm.expectRevert("Deadline has not passed");
        disputes_.resolveDisputeAfterDeadline(0);
    }

    function test_ConfidenceAbove100Rejected() public {
        _assign();
        vm.prank(arb1);
        vm.expectRevert("Confidence exceeds 100");
        disputes_.submitArbitrationVote(0, true, 101, "x");
    }

    function test_DuplicateArbitratorRejected() public {
        address[] memory arbs = new address[](3);
        arbs[0] = arb1; arbs[1] = arb1; arbs[2] = arb2;
        vm.expectRevert("Duplicate arbitrator");
        disputes_.assignArbitrators(0, arbs);
    }

    function test_ReassignmentRejectedMidArbitration() public {
        _assign();
        address[] memory arbs = new address[](3);
        arbs[0] = arb3; arbs[1] = arb2; arbs[2] = arb1;
        vm.expectRevert("Arbitrators already assigned");
        disputes_.assignArbitrators(0, arbs);
    }

    function test_EscalationResetsVoteSlate() public {
        _assign();
        vm.prank(arb1);
        disputes_.submitArbitrationVote(0, true, 60, "a");
        vm.prank(arb2);
        disputes_.submitArbitrationVote(0, true, 60, "b");
        vm.prank(arb3);
        disputes_.submitArbitrationVote(0, false, 60, "c");
        disputes_.escalateDispute(0, "appeal");
        // same panel may be re-assigned and may vote again
        _assign();
        vm.prank(arb1);
        disputes_.submitArbitrationVote(0, true, 50, "round 2");
    }
}
