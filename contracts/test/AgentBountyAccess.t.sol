// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/AgentBounty.sol";
import "../contracts/PerformanceVerifier.sol";
import "../contracts/AIToken.sol";

/**
 * Pins issue #1099:
 *  - verifySubmission had no access control, so a submitter (or anyone)
 *    could verify their own self-reported submission and collect the reward.
 *  - submissionId was the per-bounty submissionCount, used as the key of the
 *    global `submissions` mapping: submission 0 of bounty 1 overwrote
 *    submission 0 of bounty 0.
 */
contract AgentBountyAccessTest is Test {
    AIToken token;
    PerformanceVerifier pv;
    AgentBounty bounty;

    address owner = address(this);
    address creator = address(0xC1);
    address submitter = address(0x5B);
    address verifier = address(0xE1);
    address rando = address(0xE2);

    uint256 constant REWARD = 200 * 10 ** 18; // above BRONZE minimum

    function setUp() public {
        vm.warp(1 days + 1); // AIToken.mint needs lastMintTime + 1 day
        token = new AIToken(0);
        pv = new PerformanceVerifier(address(0x11), address(0x12), address(0x13));
        bounty = new AgentBounty(address(token), address(pv));

        bounty.authorizeCreator(creator);

        token.mint(address(this), REWARD * 4);
        token.transfer(creator, REWARD * 4);
        vm.prank(creator);
        token.approve(address(bounty), type(uint256).max);
    }

    function _createBounty() internal returns (uint256 bountyId) {
        vm.prank(creator);
        bountyId = bounty.createBounty(
            "t", "d", REWARD, AgentBounty.BountyTier.BRONZE,
            keccak256("criteria"), 80, block.timestamp + 1 days, 5, false
        );
    }

    function _submit(uint256 bountyId, address who) internal returns (uint256) {
        vm.prank(who);
        return bounty.submitBountySolution(bountyId, "", keccak256("perf"), 90, 1200);
    }

    function testSelfVerifyReverts() public {
        uint256 bountyId = _createBounty();
        uint256 submissionId = _submit(bountyId, submitter);

        // Even an owner-authorized verifier cannot verify their own submission.
        bounty.authorizeVerifier(submitter);
        vm.prank(submitter);
        vm.expectRevert("Submitter or creator cannot verify");
        bounty.verifySubmission(bountyId, submissionId, true, submitter);
    }

    function testCreatorCannotVerifyOwnBounty() public {
        uint256 bountyId = _createBounty();
        uint256 submissionId = _submit(bountyId, submitter);

        bounty.authorizeVerifier(creator);
        vm.prank(creator);
        vm.expectRevert("Submitter or creator cannot verify");
        bounty.verifySubmission(bountyId, submissionId, true, creator);
    }

    function testUnauthorizedVerifierReverts() public {
        uint256 bountyId = _createBounty();
        uint256 submissionId = _submit(bountyId, submitter);

        vm.prank(rando);
        vm.expectRevert("Not an authorized verifier");
        bounty.verifySubmission(bountyId, submissionId, true, rando);
    }

    function testSubmissionIdsNeverCollide() public {
        uint256 bountyA = _createBounty();
        uint256 subA = _submit(bountyA, submitter);

        uint256 bountyB = _createBounty();
        uint256 subB = _submit(bountyB, rando);

        assertEq(subA, 0);
        assertEq(subB, 1);

        // The first submission keeps its own row: bounty 1's submission 0 did
        // not overwrite bounty 0's submission 0.
        (uint256 bidA, address submitterA, , , , , , ) = bounty.getSubmission(subA);
        assertEq(bidA, bountyA);
        assertEq(submitterA, submitter);

        (uint256 bidB, address submitterB, , , , , , ) = bounty.getSubmission(subB);
        assertEq(bidB, bountyB);
        assertEq(submitterB, rando);
    }

    function testLegitVerifyPathPaysOut() public {
        uint256 bountyId = _createBounty();
        uint256 submissionId = _submit(bountyId, submitter);

        bounty.authorizeVerifier(verifier);
        vm.prank(verifier);
        bounty.verifySubmission(bountyId, submissionId, true, verifier);

        (,,,,,, AgentBounty.SubmissionStatus status, address recordedVerifier) =
            bounty.getSubmission(submissionId);
        assertEq(uint256(status), uint256(AgentBounty.SubmissionStatus.VERIFIED));
        // The recorded verifier is the actual caller, not a claimed address.
        assertEq(recordedVerifier, verifier);

        // 2% success + 1% platform fee: winner gets 97% of the reward.
        assertEq(token.balanceOf(submitter), REWARD - (REWARD * 300) / 10000);
    }

    function testRevokedVerifierCannotVerify() public {
        uint256 bountyId = _createBounty();
        uint256 submissionId = _submit(bountyId, submitter);

        bounty.authorizeVerifier(verifier);
        bounty.revokeVerifier(verifier);
        vm.prank(verifier);
        vm.expectRevert("Not an authorized verifier");
        bounty.verifySubmission(bountyId, submissionId, true, verifier);
    }
}

/**
 * Pins issue #1469:
 *  - disputeSubmission was permissionless: any address could freeze a
 *    verified submission for the price of the dispute fee.
 *  - resolveDispute refunded the dispute fee to msg.sender (the owner
 *    resolving), not to the disputer who paid it.
 *  - Residuals fixed alongside: a COMPLETED (already-paid) bounty could be
 *    dragged back to DISPUTED, and the reject-dispute branch of
 *    resolveDispute could never succeed because _completeBounty requires
 *    an ACTIVE/SUBMITTED bounty.
 */
contract AgentBountyDispute1469Test is AgentBountyAccessTest {
    // A bounty whose minAccuracy (95) exceeds the submitted accuracy (90):
    // verification marks the submission VERIFIED but the bounty stays
    // ACTIVE — the only state in which a dispute is meaningful.
    function _verifiedOpenSubmission() internal returns (uint256 bountyId, uint256 submissionId) {
        vm.prank(creator);
        bountyId = bounty.createBounty(
            "t", "d", REWARD, AgentBounty.BountyTier.BRONZE,
            keccak256("criteria"), 95, block.timestamp + 1 days, 5, false
        );
        submissionId = _submit(bountyId, submitter);
        bounty.authorizeVerifier(verifier);
        vm.prank(verifier);
        bounty.verifySubmission(bountyId, submissionId, true, verifier);
    }

    function test_RandomCannotDisputeVerifiedSubmission() public {
        (uint256 bountyId, uint256 submissionId) = _verifiedOpenSubmission();

        vm.prank(rando);
        vm.expectRevert("Only bounty participants can dispute");
        bounty.disputeSubmission(bountyId, submissionId, "grief");
    }

    function test_OwnerCannotDisputeEither() public {
        (uint256 bountyId, uint256 submissionId) = _verifiedOpenSubmission();

        // The owner resolves disputes but is not a bounty participant.
        vm.expectRevert("Only bounty participants can dispute");
        bounty.disputeSubmission(bountyId, submissionId, "owner grief");
    }

    function test_CreatorDispute_feeReturnsToDisputer() public {
        (uint256 bountyId, uint256 submissionId) = _verifiedOpenSubmission();
        uint256 fee = (REWARD * bounty.disputeFeePercentage()) / 10000;
        uint256 creatorBefore = token.balanceOf(creator);
        uint256 ownerBefore = token.balanceOf(owner);

        vm.prank(creator);
        bounty.disputeSubmission(bountyId, submissionId, "wrong verdict");

        (,,,,, AgentBounty.BountyStatus status,,,,,,,) = bounty.getBounty(bountyId);
        assertEq(uint256(status), uint256(AgentBounty.BountyStatus.DISPUTED));
        assertEq(bounty.submissionDisputer(submissionId), creator);
        assertEq(token.balanceOf(creator), creatorBefore - fee);

        // Owner upholds the dispute: submission rejected, bounty reopens,
        // and the fee goes back to the disputer — not to the owner.
        bounty.resolveDispute(bountyId, submissionId, true);
        assertEq(token.balanceOf(creator), creatorBefore);
        assertEq(token.balanceOf(owner), ownerBefore);

        (,,,,,, AgentBounty.SubmissionStatus subStatus,) = bounty.getSubmission(submissionId);
        assertEq(uint256(subStatus), uint256(AgentBounty.SubmissionStatus.REJECTED));
        (,,,,, AgentBounty.BountyStatus statusAfter,,,,,,,) = bounty.getBounty(bountyId);
        assertEq(uint256(statusAfter), uint256(AgentBounty.BountyStatus.ACTIVE));
    }

    function test_SubmitterCanDispute_asParticipant() public {
        // Fund the submitter BEFORE the submission exists: minting needs a
        // +1 day warp, which would push the dispute outside the 24h window.
        vm.warp(block.timestamp + 1 days + 1); // AIToken.mint cooldown
        uint256 fee = (REWARD * bounty.disputeFeePercentage()) / 10000;
        token.mint(submitter, fee * 2);
        vm.prank(submitter);
        token.approve(address(bounty), fee * 2);

        (uint256 bountyId, uint256 submissionId) = _verifiedOpenSubmission();

        vm.prank(submitter);
        bounty.disputeSubmission(bountyId, submissionId, "contest verification");
        assertEq(bounty.submissionDisputer(submissionId), submitter);
    }

    function test_CompletedBountyCannotBeDisputed() public {
        // minAccuracy 80 < submitted accuracy 90: verification completes
        // the bounty and pays the winner immediately.
        uint256 bountyId = _createBounty();
        uint256 submissionId = _submit(bountyId, submitter);
        bounty.authorizeVerifier(verifier);
        vm.prank(verifier);
        bounty.verifySubmission(bountyId, submissionId, true, verifier);

        vm.prank(creator);
        vm.expectRevert("Bounty not disputable");
        bounty.disputeSubmission(bountyId, submissionId, "too late");
    }
}

contract AgentBountyZkAutoVerifyPinTest is AgentBountyAccessTest {
    // #1099 residual: a non-empty zkProof used to auto-verify through the
    // always-true stub and pay the reward inside submitBountySolution.
    // A proof submission now stays PENDING for an authorized verifier.
    function testZkProofSubmissionStaysPendingAndPaysNothing() public {
        vm.prank(creator);
        uint256 bountyId = bounty.createBounty(
            "t", "d", REWARD, AgentBounty.BountyTier.BRONZE,
            keccak256("criteria"), 80, block.timestamp + 1 days, 5, true // requiresZKProof
        );

        uint256 before = token.balanceOf(submitter);
        vm.prank(submitter);
        uint256 submissionId = bounty.submitBountySolution(bountyId, hex"deadbeef", keccak256("perf"), 90, 1200);

        (,,,,,, AgentBounty.SubmissionStatus status,) = bounty.getSubmission(submissionId);
        assertEq(uint256(status), uint256(AgentBounty.SubmissionStatus.PENDING));
        assertEq(token.balanceOf(submitter), before);

        // The authorized path still works afterwards.
        bounty.authorizeVerifier(verifier);
        vm.prank(verifier);
        bounty.verifySubmission(bountyId, submissionId, true, verifier);
        assertEq(token.balanceOf(submitter), before + REWARD - (REWARD * 300) / 10000);
    }
}
