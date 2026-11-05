// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/EscrowService.sol";
import "../contracts/AIPowerRental.sol";
import "../contracts/PaymentProcessor.sol";
import "../contracts/ZKReceiptVerifier.sol";
import "../contracts/Groth16Verifier.sol";
import "../contracts/AIToken.sol";

/// #1138 pins: voteEmergencyRelease used to keep accepting votes after
/// quorum+threshold was reached. Every later vote that kept the percentage
/// above threshold re-stamped approvalTime — silently restarting the
/// emergencyReleaseTimelock — and a late against-majority could never clear
/// isApproved, so the release executed on a tally that no longer approved it.
/// The fix latches approval (approvalTime stamped once) and closes voting at
/// approval.
contract EscrowVoteLatch1138Test is Test {
    AIToken token;
    AIPowerRental rental;
    PaymentProcessor processor;
    EscrowService escrow;

    address depositor = makeAddr("depositor");
    address beneficiary = makeAddr("beneficiary");
    address arb1 = makeAddr("arb1");
    address arb2 = makeAddr("arb2");
    address arb3 = makeAddr("arb3");
    address arb4 = makeAddr("arb4");

    uint256 constant AMOUNT = 1e18;

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days); // AIToken MINTING_COOLDOWN is 1 day
        ZKReceiptVerifier zkv = new ZKReceiptVerifier();
        Groth16Verifier g16 = new Groth16Verifier();
        rental = new AIPowerRental(address(token), address(zkv), address(g16));
        processor = new PaymentProcessor(address(token), address(rental));
        escrow = new EscrowService(address(token), address(rental), address(processor));

        token.mint(depositor, 100e18);
        vm.prank(depositor);
        token.approve(address(escrow), 100e18);

        escrow.authorizeArbiter(arb1);
        escrow.authorizeArbiter(arb2);
        escrow.authorizeArbiter(arb3);
        escrow.authorizeArbiter(arb4);
    }

    function _createStandard() internal returns (uint256 id) {
        vm.prank(depositor);
        id = escrow.createEscrow(
            beneficiary,
            address(0),
            AMOUNT,
            EscrowService.EscrowType.Standard,
            EscrowService.ReleaseCondition.Manual,
            0,
            "pin"
        );
    }

    function _request(uint256 id) internal {
        vm.prank(depositor);
        escrow.requestEmergencyRelease(id, "stuck");
    }

    function _emergency(uint256 id)
        internal
        view
        returns (
            uint256 escrowId,
            address initiator,
            string memory reason,
            uint256 requestTime,
            uint256 votingDeadline,
            uint256 votesFor,
            uint256 votesAgainst,
            uint256 totalVotes,
            bool isApproved,
            bool isExecuted,
            uint256 approvalTime
        )
    {
        return escrow.emergencyReleases(id);
    }

    /// Once quorum+threshold is reached, voting is closed: a further arbiter
    /// vote reverts instead of re-stamping approvalTime.
    function test_LateVoteRejectedAfterApproval() public {
        uint256 id = _createStandard();
        _request(id);
        vm.prank(arb1);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb2);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb3);
        escrow.voteEmergencyRelease(id, true);

        (, , , , , , , , bool approved, , uint256 approvalTime) = _emergency(id);
        assertTrue(approved);

        vm.warp(block.timestamp + 1 hours);
        vm.prank(arb4);
        vm.expectRevert("Emergency release already approved");
        escrow.voteEmergencyRelease(id, false);

        // approvalTime must be untouched by the rejected vote.
        (, , , , , , , , , , uint256 approvalTimeAfter) = _emergency(id);
        assertEq(approvalTimeAfter, approvalTime);
    }

    /// The timelock clock runs from the first approving vote, not from a
    /// later one: execution succeeds at approvalTime + timelock even though
    /// wall-clock time has moved on.
    function test_TimelockRunsFromFirstApproval() public {
        uint256 id = _createStandard();
        _request(id);
        vm.prank(arb1);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb2);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb3);
        escrow.voteEmergencyRelease(id, true);

        (, , , , , , , , , , uint256 approvalTime) = _emergency(id);

        // Any attempt to keep voting is closed, so approvalTime cannot move.
        vm.warp(approvalTime + escrow.emergencyReleaseTimelock());
        escrow.executeEmergencyRelease(id);
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }

    /// Before quorum is reached, votes still count normally — the close is
    /// only at approval, not at quorum alone.
    function test_VotesBeforeApprovalStillCount() public {
        uint256 id = _createStandard();
        _request(id);
        vm.prank(arb1);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb2);
        escrow.voteEmergencyRelease(id, false);

        (, , , , , uint256 votesFor, uint256 votesAgainst, uint256 totalVotes, bool approved, , ) =
            _emergency(id);
        assertEq(totalVotes, 2);
        assertEq(votesFor, 1);
        assertEq(votesAgainst, 1);
        assertFalse(approved);

        // Third vote reaches quorum: 2/3 = 66% >= 66% threshold -> approved.
        vm.prank(arb3);
        escrow.voteEmergencyRelease(id, true);
        (, , , , , , , , bool approvedAfter, , ) = _emergency(id);
        assertTrue(approvedAfter);
    }
}
