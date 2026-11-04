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
