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
    event RentalResolutionFailed(uint256 indexed agreementId, address indexed winner, uint256 resolutionAmount);

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
        // and the decision moved funds: the provider filed and won, so
        // the PROVIDER is paid the escrowed price — not the consumer
        // (#1108 rework; the old leg paid the wrong side).
        assertGe(token.balanceOf(provider), 100e18);
    }

    /// A consumer-filed dispute that the consumer loses pays the provider
    /// the escrowed price — the old code resolved with amount 0 and left
    /// the escrow stranded on a resolved record (#1108 rework).
    function test_ConsumerInitiatedLossPaysProvider() public {
        // second agreement, filed by the consumer this time
        vm.warp(block.timestamp + 1 days + 1); // AIToken MINTING_COOLDOWN is 1 day — setUp already minted
        token.mint(consumer, 200e18);
        vm.prank(consumer);
        uint256 agreementId2 = rental.createRental(provider, consumer, 1 days, 100e18, "GPU", 1);
        vm.startPrank(consumer);
        token.approve(address(rental), 200e18);
        rental.startRental(agreementId2);
        rental.disputeRental(agreementId2, "refund me");
        disputes_.fileDispute(agreementId2, provider, DisputeResolution.DisputeType.ServiceQuality, "refund me", keccak256("e2"));
        vm.stopPrank();

        address[] memory arbs = new address[](3);
        arbs[0] = arb1; arbs[1] = arb2; arbs[2] = arb3;
        disputes_.assignArbitrators(1, arbs);
        // full panel votes against the initiator (consumer) -> provider wins
        vm.prank(arb1);
        disputes_.submitArbitrationVote(1, false, 60, "a");
        vm.prank(arb2);
        disputes_.submitArbitrationVote(1, false, 60, "b");
        vm.prank(arb3);
        disputes_.submitArbitrationVote(1, false, 60, "c");

        (, , , , DisputeResolution.DisputeStatus st, , , , , , ) = disputes_.getDispute(1);
        assertEq(uint256(st), uint256(DisputeResolution.DisputeStatus.Resolved));
        assertGe(token.balanceOf(provider), 100e18);
        // and the rental-side record is resolved, not stranded
        AIPowerRental.DisputeInfo memory di = rental.getDisputeInfo(agreementId2);
        assertTrue(di.resolved);
    }

    /// When this contract does not own the rental the payout leg reverts —
    /// the panel result must still land, not re-freeze (#1108 rework).
    function test_ResolutionSurvivesNonOwnerRental() public {
        // take rental ownership back from the panel contract
        vm.prank(address(disputes_));
        rental.transferOwnership(address(this));

        _assign();
        vm.prank(arb1);
        disputes_.submitArbitrationVote(0, true, 80, "clear");
        vm.warp(block.timestamp + 11 days);
        vm.expectEmit(true, true, false, true);
        emit RentalResolutionFailed(agreementId, provider, 100e18);
        disputes_.resolveDisputeAfterDeadline(0);

        (, , , , DisputeResolution.DisputeStatus st, , , , , , ) = disputes_.getDispute(0);
        assertEq(uint256(st), uint256(DisputeResolution.DisputeStatus.Resolved));
        // payout leg reverted inside try/catch: nobody was paid, but the
        // dispute is final rather than frozen
        assertEq(token.balanceOf(provider), 0);
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
