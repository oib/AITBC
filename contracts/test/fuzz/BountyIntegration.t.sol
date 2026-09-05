// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/BountyIntegration.sol";
import "../../contracts/AIToken.sol";
import "../../contracts/AgentBounty.sol";
import "../../contracts/AgentStaking.sol";
import "../../contracts/PerformanceVerifier.sol";

contract BountyIntegrationFuzzTest is Test {
    BountyIntegration public integration;
    AIToken public paymentToken;
    address public owner;
    address public integrator;
    address public stranger;

    function setUp() public {
        owner = address(this);
        integrator = address(0x1);
        stranger = address(0x2);

        paymentToken = new AIToken(0);
        // Stand-ins: the external contract calls are exercised through the
        // failure paths (they revert on undeployed addresses, which
        // _processMapping catches and records as FAILED).
        integration = new BountyIntegration(
            address(0xA1),
            address(0xA2),
            address(0xA3),
            address(paymentToken)
        );
        integration.authorizeIntegrator(integrator);
    }

    function testFuzz_AuthorizeIntegratorOnlyOwner(address caller, address target) public {
        vm.assume(caller != owner);
        vm.assume(target != address(0));

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        integration.authorizeIntegrator(target);
    }

    function testFuzz_AuthorizeIntegratorRejectsZero() public {
        vm.expectRevert("Invalid integrator address");
        integration.authorizeIntegrator(address(0));
    }

    function testFuzz_AuthorizeIntegratorRejectsDuplicate() public {
        vm.expectRevert("Already authorized");
        integration.authorizeIntegrator(integrator);
    }

    function testFuzz_RevokeIntegrator(address target) public {
        vm.assume(target != address(0) && target != integrator);

        integration.authorizeIntegrator(target);
        assertTrue(integration.isAuthorizedIntegrator(target));

        integration.revokeIntegrator(target);
        assertFalse(integration.isAuthorizedIntegrator(target));
    }

    function testFuzz_RevokeIntegratorRejectsUnknown(address target) public {
        vm.assume(target != integrator);

        vm.expectRevert("Not authorized");
        integration.revokeIntegrator(target);
    }

    function testFuzz_MapPerformanceToBountyOnlyIntegrator(address caller, bytes32 hash) public {
        vm.assume(caller != integrator);
        vm.assume(hash != bytes32(0));

        vm.prank(caller);
        vm.expectRevert("Not authorized integrator");
        integration.mapPerformanceToBounty(hash, 1, 1);
    }

    function testFuzz_MapPerformanceToBountyRejectsZeroHash() public {
        vm.prank(integrator);
        vm.expectRevert("Invalid performance hash");
        integration.mapPerformanceToBounty(bytes32(0), 1, 1);
    }

    function testFuzz_MapPerformanceToBountyCreatesAndFailsProcessing(bytes32 hash, uint256 bountyId, uint256 subId)
        public
    {
        vm.assume(hash != bytes32(0));

        vm.prank(integrator);
        uint256 mappingId = integration.mapPerformanceToBounty(hash, bountyId, subId);

        assertEq(mappingId, 0);
        assertTrue(integration.performanceHashMapped(hash));
        assertEq(integration.performanceHashToMapping(hash), mappingId);

        // The stand-in bounty contract has no code, so processing lands in FAILED
        // via _processMapping's catch path.
        (bytes32 perfHash, , , BountyIntegration.IntegrationStatus status, , , string memory err) =
            integration.getPerformanceMapping(mappingId);
        assertEq(perfHash, hash);
        assertEq(uint256(status), uint256(BountyIntegration.IntegrationStatus.FAILED));
        assertTrue(bytes(err).length > 0);

        // Failed mappings are removed from the pending list.
        assertEq(integration.getPendingMappings().length, 0);
        // But the hash stays recorded.
        assertEq(integration.getPerformanceHashes().length, 1);
    }

    function testFuzz_DuplicateHashRejected(uint256 bountyId, uint256 subId) public {
        bytes32 hash = keccak256("dup");

        vm.startPrank(integrator);
        integration.mapPerformanceToBounty(hash, bountyId, subId);
        vm.expectRevert("Performance already mapped");
        integration.mapPerformanceToBounty(hash, bountyId, subId);
        vm.stopPrank();
    }

    function testFuzz_ProcessMappingRejectsInvalidId(uint256 mappingId) public {
        vm.assume(mappingId >= integration.integrationCounter());

        vm.prank(integrator);
        vm.expectRevert("Mapping does not exist");
        integration.processMapping(mappingId);
    }

    function testFuzz_ProcessBatchRejectsOversized() public {
        uint256[] memory ids = new uint256[](51);
        vm.prank(integrator);
        vm.expectRevert("Batch too large");
        integration.processBatchMappings(ids);
    }

    function testFuzz_ProcessBatchCountsFailures(uint8 n) public {
        n = uint8(bound(n, 1, 50));

        uint256[] memory ids = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            ids[i] = i; // nonexistent -> failure via try/catch
        }

        vm.prank(integrator);
        integration.processBatchMappings(ids);

        (, , BountyIntegration.IntegrationStatus st, , , uint256 successCount, uint256 failureCount) =
            integration.getBatchRequest(0);
        assertEq(successCount, 0);
        assertEq(failureCount, n);
        assertEq(uint256(st), uint256(BountyIntegration.IntegrationStatus.COMPLETED));
    }

    function testFuzz_UpdateConfiguration(uint256 threshold, uint256 batchLimit, uint256 gasThreshold) public {
        threshold = bound(threshold, 0, 100);
        batchLimit = bound(batchLimit, 0, 100);

        integration.updateConfiguration(threshold, batchLimit, gasThreshold);
        assertEq(integration.autoVerificationThreshold(), threshold);
        assertEq(integration.batchProcessingLimit(), batchLimit);
        assertEq(integration.gasOptimizationThreshold(), gasThreshold);
    }

    function testFuzz_UpdateConfigurationRejectsHighThreshold(uint256 threshold) public {
        vm.assume(threshold > 100);

        vm.expectRevert("Invalid threshold");
        integration.updateConfiguration(threshold, 50, 0);
    }

    function testFuzz_RegisterEventHandlerOnlyOwner(address caller) public {
        vm.assume(caller != owner);

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        integration.registerEventHandler(keccak256("X"), address(0x42), bytes4(uint32(1)));
    }

    function testFuzz_RegisterEventHandlerRejectsZeroTarget() public {
        vm.expectRevert("Invalid target contract");
        integration.registerEventHandler(keccak256("X"), address(0), bytes4(uint32(1)));
    }

    function testFuzz_HandlePerformanceVerifiedNoMappingIsNoop(uint256 verificationId, bytes32 hash) public {
        vm.prank(integrator);
        // No mapping for this hash: the call must not revert and must not touch state.
        integration.handlePerformanceVerified(verificationId, 50, 100, hash);
    }

    function testFuzz_GetIntegrationStatsEmpty() public {
        (uint256 total, uint256 pending, uint256 completed, uint256 failed, ) = integration.getIntegrationStats();
        assertEq(total, 0);
        assertEq(pending, 0);
        assertEq(completed, 0);
        assertEq(failed, 0);
    }

    function testFuzz_GetAuthorizedIntegratorsContainsSeeded() public {
        address[] memory list = integration.getAuthorizedIntegrators();
        assertEq(list.length, 1);
        assertEq(list[0], integrator);
    }

    // ---------- Happy path: real AgentBounty + AgentStaking fixtures ----------

    address public constant SUBMITTER = address(0x5B);
    address public constant CREATOR = address(0xC1);

    function _realFixture()
        internal
        returns (
            AIToken token,
            AgentBounty bounty,
            AgentStaking staking,
            BountyIntegration integ
        )
    {
        token = new AIToken(0);
        // PerformanceVerifier takes three addresses but the happy path never
        // calls into it — placeholders are sufficient.
        PerformanceVerifier pv = new PerformanceVerifier(address(0x11), address(0x12), address(0x13));
        bounty = new AgentBounty(address(token), address(pv));
        staking = new AgentStaking(address(token), address(pv));
        integ = new BountyIntegration(
            address(bounty),
            address(staking),
            address(pv),
            address(token)
        );

        bounty.authorizeCreator(CREATOR);
        // updateAgentPerformance requires oracle auth + a supported agent
        staking.addOracle(address(integ));
        staking.addSupportedAgent(SUBMITTER, AgentStaking.PerformanceTier.BRONZE);
        integ.authorizeIntegrator(integrator);
    }

    function _mapRealBounty(
        AIToken token,
        AgentBounty bounty,
        BountyIntegration integ,
        bytes32 perfHash,
        uint256 accuracy
    ) internal returns (uint256 bountyId, uint256 submissionId, uint256 mappingId) {
        uint256 reward = 200 * 10 ** 18; // above the BRONZE minimum of 100e18

        // Foundry starts at timestamp 1, but AIToken.mint requires
        // timestamp >= lastMintTime(0) + 1 day — even the first mint needs
        // the clock past the cooldown. Warping once here also satisfies
        // AgentStaking's 1h performanceUpdateDelay for the first update.
        vm.warp(1 days + 1);
        // _completeBounty pays from the contract's own balance — it is never
        // escrowed at createBounty time, only the creator's balance is checked.
        // createBounty escrows reward + 0.5% creation fee via transferFrom —
        // the creator needs the balance and an approval for the pull.
        token.mint(address(this), reward * 2);
        token.transfer(CREATOR, reward * 2);
        vm.prank(CREATOR);
        token.approve(address(bounty), reward * 2);

        vm.prank(CREATOR);
        bountyId = bounty.createBounty(
            "t", "d", reward, AgentBounty.BountyTier.BRONZE,
            keccak256("criteria"), 80, block.timestamp + 1 days, 5, false
        );

        vm.prank(SUBMITTER);
        submissionId = bounty.submitBountySolution(bountyId, "", perfHash, accuracy, 1200);

        vm.prank(integrator);
        mappingId = integ.mapPerformanceToBounty(perfHash, bountyId, submissionId);
    }

    function test_ProcessMappingCompletesHappyPath() public {
        (AIToken token, AgentBounty bounty, AgentStaking staking, BountyIntegration integ) = _realFixture();
        bytes32 perfHash = keccak256("perf-1");

        (uint256 bountyId, uint256 submissionId, uint256 mappingId) =
            _mapRealBounty(token, bounty, integ, perfHash, 95);

        // mapPerformanceToBounty already ran _processMapping inline, so the
        // payout landed during _mapRealBounty — assert the absolute balance
        // (SUBMITTER starts at 0). 2% success + 1% platform fee => 97%.
        uint256 reward = 200 * 10 ** 18;
        assertEq(token.balanceOf(SUBMITTER), reward - (reward * 300) / 10000);

        vm.prank(integrator);
        integ.processMapping(mappingId);

        (,,, BountyIntegration.IntegrationStatus status,,,) = integ.getPerformanceMapping(mappingId);
        assertEq(uint256(status), uint256(BountyIntegration.IntegrationStatus.COMPLETED));

        (,,,,,, AgentBounty.SubmissionStatus subStatus, address verifierAddr) =
            bounty.getSubmission(submissionId);
        assertEq(uint256(subStatus), uint256(AgentBounty.SubmissionStatus.VERIFIED));
        assertEq(verifierAddr, address(integ));

        (,,,,, AgentBounty.BountyStatus bStatus,,,,,,,) = bounty.getBounty(bountyId);
        assertEq(uint256(bStatus), uint256(AgentBounty.BountyStatus.COMPLETED));

        // staking side observed the performance update
        assertGt(staking.lastPerformanceUpdateTime(SUBMITTER), 0);
    }

    function test_ProcessMappingBelowThresholdSkipsAutoVerify() public {
        (AIToken token, AgentBounty bounty, AgentStaking staking, BountyIntegration integ) = _realFixture();
        bytes32 perfHash = keccak256("perf-2");

        // accuracy >= minAccuracy (80) but < autoVerificationThreshold (90):
        // the mapping completes without verification or staking update.
        (, uint256 submissionId, uint256 mappingId) =
            _mapRealBounty(token, bounty, integ, perfHash, 85);


        vm.prank(integrator);
        integ.processMapping(mappingId);

        (,,, BountyIntegration.IntegrationStatus status,,,) = integ.getPerformanceMapping(mappingId);
        assertEq(uint256(status), uint256(BountyIntegration.IntegrationStatus.COMPLETED));

        (,,,,,, AgentBounty.SubmissionStatus subStatus,) = bounty.getSubmission(submissionId);
        assertEq(uint256(subStatus), uint256(AgentBounty.SubmissionStatus.PENDING));
        assertEq(staking.lastPerformanceUpdateTime(SUBMITTER), 0);
    }

    function testFuzz_ProcessMappingAccuracyBoundaries(uint256 accuracy) public {
        accuracy = bound(accuracy, 80, 100);
        (AIToken token, AgentBounty bounty, AgentStaking staking, BountyIntegration integ) = _realFixture();
        bytes32 perfHash = keccak256(abi.encodePacked("perf", accuracy));

        (, uint256 submissionId, uint256 mappingId) =
            _mapRealBounty(token, bounty, integ, perfHash, accuracy);


        vm.prank(integrator);
        integ.processMapping(mappingId);

        (,,, BountyIntegration.IntegrationStatus status,,,) = integ.getPerformanceMapping(mappingId);
        assertEq(uint256(status), uint256(BountyIntegration.IntegrationStatus.COMPLETED));

        (,,,,,, AgentBounty.SubmissionStatus subStatus,) = bounty.getSubmission(submissionId);
        bool shouldVerify = accuracy >= 90;
        assertEq(
            uint256(subStatus),
            shouldVerify ? uint256(AgentBounty.SubmissionStatus.VERIFIED) : uint256(AgentBounty.SubmissionStatus.PENDING)
        );
    }

    function test_HandlePerformanceVerifiedHappyPath() public {
        (AIToken token, AgentBounty bounty, AgentStaking staking, BountyIntegration integ) = _realFixture();
        bytes32 perfHash = keccak256("perf-3");

        // Map at 85 (< autoVerificationThreshold 90): the inline processing
        // leaves the submission PENDING and skips the staking update, so
        // handlePerformanceVerified is the call that completes them — and the
        // first updateAgentPerformance call, so the 1h rate limit is not hit.
        (uint256 bountyId, uint256 submissionId,) = _mapRealBounty(token, bounty, integ, perfHash, 85);

        vm.prank(integrator);
        integ.handlePerformanceVerified(7, 95, 500, perfHash);

        assertGt(staking.lastPerformanceUpdateTime(SUBMITTER), 0);

        (,,,,,, AgentBounty.SubmissionStatus subStatus,) = bounty.getSubmission(submissionId);
        assertEq(uint256(subStatus), uint256(AgentBounty.SubmissionStatus.VERIFIED));
    }
}
