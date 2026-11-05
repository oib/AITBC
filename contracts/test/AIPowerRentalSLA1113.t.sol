// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../contracts/AIPowerRental.sol";
import "../contracts/ZKReceiptVerifier.sol";
import "../contracts/Groth16Verifier.sol";
import "../contracts/AIToken.sol";

/// #1113 pins: SLA-linked payout, submission-window guard, per-agreement
/// escrow accounting, and the dispute cap/remainder refund.
contract AIPowerRentalSLA1113Test is Test {
    AIPowerRental public rental;
    AIToken public token;
    address provider = makeAddr("provider");
    address consumer = makeAddr("consumer");
    address owner = address(this);

    uint256 constant PRICE = 100e18;
    uint256 constant FEE = 2.5e18; // 2.5% of 100e18
    uint256 constant DEPOSIT = PRICE + FEE;
    uint256 constant DURATION = 3600;

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days); // AIToken minting cooldown
        ZKReceiptVerifier zkv = new ZKReceiptVerifier();
        Groth16Verifier g16 = new Groth16Verifier();
        rental = new AIPowerRental(address(token), address(zkv), address(g16));
        rental.authorizeProvider(provider);
        rental.authorizeConsumer(consumer);
    }

    function _fundAndStart() internal returns (uint256 agreementId) {
        token.mint(consumer, DEPOSIT);
        vm.prank(consumer);
        agreementId = rental.createRental(provider, consumer, DURATION, PRICE, "GPU", 1);
        vm.startPrank(consumer);
        token.approve(address(rental), DEPOSIT);
        rental.startRental(agreementId);
        vm.stopPrank();
    }

    function _pastWindow() internal {
        (, , , , , , uint256 endTime, , , , , ) = rental.getRentalAgreement(0);
        vm.warp(endTime + rental.performanceSubmissionWindow() + 1);
    }

    /// Completing inside the submission window with no performance
    /// submission must revert — otherwise a consumer could cut off a
    /// provider still inside the grace period.
    function test_CompleteInsideWindowWithoutSubmissionReverts() public {
        _fundAndStart();
        (, , , , , , uint256 endTime, , , , , ) = rental.getRentalAgreement(0);
        vm.warp(endTime + 1);
        vm.prank(consumer);
        vm.expectRevert("Performance submission window open");
        rental.completeRental(0);
    }

    /// After the window with no submission, the provider is paid the
    /// penalty rate and the withheld share is refunded to the consumer.
    function test_CompleteAfterWindowPaysPenaltyAndRefunds() public {
        _fundAndStart();
        _pastWindow();
        vm.prank(consumer);
        rental.completeRental(0);

        uint256 expectedProvider = (PRICE * (10000 - rental.slaPenaltyBps())) / 10000;
        uint256 expectedRefund = PRICE - expectedProvider;
        assertEq(token.balanceOf(provider), expectedProvider);
        assertEq(token.balanceOf(owner), FEE);
        assertEq(token.balanceOf(consumer), expectedRefund);
        assertEq(token.balanceOf(address(rental)), 0);
        assertEq(rental.agreementPaidOut(0), DEPOSIT);
    }

    /// A submitted-but-unverified performance (the #1100 catch path sets
    /// withinSLA=false) skips the window wait and settles at the penalty.
    function test_UnverifiedSubmissionSettlesAtPenalty() public {
        _fundAndStart();
        vm.prank(provider);
        rental.submitPerformance(0, 1, 1, 1, 1, "");

        (, , , , , , uint256 endTime, , , , , ) = rental.getRentalAgreement(0);
        vm.warp(endTime + 1); // inside the window, but a submission exists
        vm.prank(provider);
        rental.completeRental(0);

        uint256 expectedProvider = (PRICE * (10000 - rental.slaPenaltyBps())) / 10000;
        assertEq(token.balanceOf(provider), expectedProvider);
        assertEq(token.balanceOf(consumer), PRICE - expectedProvider);
        assertEq(token.balanceOf(address(rental)), 0);
    }

    /// Dispute awards are capped at the agreement's own unspent deposit;
    /// the remainder is refunded to the consumer instead of stranding.
    function test_DisputeResolutionCappedAndRemainderRefunded() public {
        _fundAndStart();
        vm.prank(provider);
        rental.disputeRental(0, "bad service");

        vm.expectRevert("Resolution exceeds agreement funds");
        rental.resolveDispute(0, DEPOSIT + 1, true);

        rental.resolveDispute(0, PRICE, true);
        assertEq(token.balanceOf(provider), PRICE);
        assertEq(token.balanceOf(consumer), FEE); // remainder back to depositor
        assertEq(token.balanceOf(address(rental)), 0);
        assertEq(rental.agreementPaidOut(0), DEPOSIT);
    }

    /// A completed agreement's deposit is fully spent — it can no longer
    /// be disputed, closing the second-payout path.
    function test_CompletedAgreementCannotBeDisputed() public {
        _fundAndStart();
        _pastWindow();
        vm.prank(consumer);
        rental.completeRental(0);

        vm.prank(provider);
        vm.expectRevert("Cannot dispute this agreement");
        rental.disputeRental(0, "late complaint");
    }

    /// Owner bounds on the new knobs.
    function test_SetterBounds() public {
        vm.expectRevert("Penalty too high");
        rental.updateSLAPenaltyBps(10001);
        rental.updateSLAPenaltyBps(0);
        assertEq(rental.slaPenaltyBps(), 0);

        vm.expectRevert("Window out of range");
        rental.updatePerformanceSubmissionWindow(0);
        vm.expectRevert("Window out of range");
        rental.updatePerformanceSubmissionWindow(31 days);
        rental.updatePerformanceSubmissionWindow(1 days);
        assertEq(rental.performanceSubmissionWindow(), 1 days);
    }
}
