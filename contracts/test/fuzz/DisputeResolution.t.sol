// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/DisputeResolution.sol";
import "../../contracts/AIPowerRental.sol";
import "../../contracts/ZKReceiptVerifier.sol";
import "../../contracts/Groth16Verifier.sol";
import "../../contracts/AIToken.sol";

contract DisputeResolutionFuzzTest is Test {
    DisputeResolution public disputes_;
    AIPowerRental public rental;
    AIToken public token;
    address public owner;
    address public provider;
    address public consumer;
    address public arb1;
    address public arb2;
    address public arb3;
    uint256 public agreementId;

    function setUp() public {
        owner = address(this);
        provider = makeAddr("provider");
        consumer = makeAddr("consumer");
        arb1 = makeAddr("arb1");
        arb2 = makeAddr("arb2");
        arb3 = makeAddr("arb3");

        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days); // AIToken minting cooldown
        ZKReceiptVerifier zkVerifier = new ZKReceiptVerifier();
        Groth16Verifier groth16Verifier = new Groth16Verifier();
        rental = new AIPowerRental(address(token), address(zkVerifier), address(groth16Verifier));
        rental.authorizeProvider(provider);
        rental.authorizeConsumer(consumer);

        vm.prank(consumer);
        agreementId = rental.createRental(provider, consumer, 1 days, 100e18, "GPU", 1);

        disputes_ = new DisputeResolution(
            address(rental),
            address(0xB1), // PaymentProcessor stand-in (unused in tested paths)
            address(0xB2)  // PerformanceVerifier stand-in
        );

        disputes_.authorizeArbitrator(arb1, 100);
        disputes_.authorizeArbitrator(arb2, 100);
        disputes_.authorizeArbitrator(arb3, 100);
    }

    function _file() internal returns (uint256 disputeId) {
        vm.prank(provider);
        disputeId = disputes_.fileDispute(
            agreementId, consumer, DisputeResolution.DisputeType.ServiceQuality, "bad service", keccak256("e")
        );
    }

    function _fileAndAssign() internal returns (uint256 disputeId) {
        disputeId = _file();
        address[] memory arbs = new address[](3);
        arbs[0] = arb1;
        arbs[1] = arb2;
        arbs[2] = arb3;
        disputes_.assignArbitrators(disputeId, arbs);
    }

    // ---------- fileDispute ----------

    function testFuzz_FileDispute(bool byProvider, string calldata reason, bytes32 evidenceHash) public {
        vm.assume(bytes(reason).length > 0 && bytes(reason).length <= 128);

        address initiator = byProvider ? provider : consumer;
        address respondent = byProvider ? consumer : provider;

        vm.prank(initiator);
        uint256 disputeId = disputes_.fileDispute(
            agreementId, respondent, DisputeResolution.DisputeType.Payment, reason, evidenceHash
        );

        assertEq(disputeId, 0);
        DisputeResolution.Dispute memory d = disputes_.getDispute(disputeId);
        assertEq(d.initiator, initiator);
        assertEq(d.respondent, respondent);
        assertEq(uint256(d.status), uint256(DisputeResolution.DisputeStatus.Filed));
        assertEq(d.evidenceDeadline, block.timestamp + 3 days);
        assertEq(disputes_.userDisputes(initiator, 0), disputeId);
        assertEq(disputes_.userDisputes(respondent, 0), disputeId);
        assertEq(disputes_.agreementDisputes(agreementId), disputeId);
    }

    function testFuzz_FileDisputeRejectsZeroRespondent() public {
        vm.prank(provider);
        vm.expectRevert("Invalid respondent");
        disputes_.fileDispute(agreementId, address(0), DisputeResolution.DisputeType.Payment, "r", bytes32(0));
    }

    function testFuzz_FileDisputeRejectsSelf() public {
        vm.prank(provider);
        vm.expectRevert("Cannot dispute yourself");
        disputes_.fileDispute(agreementId, provider, DisputeResolution.DisputeType.Payment, "r", bytes32(0));
    }

    function testFuzz_FileDisputeRejectsEmptyReason() public {
        vm.prank(provider);
        vm.expectRevert("Reason required");
        disputes_.fileDispute(agreementId, consumer, DisputeResolution.DisputeType.Payment, "", bytes32(0));
    }

    function testFuzz_FileDisputeRejectsInvalidAgreement(uint256 badAgreementId) public {
        vm.assume(badAgreementId != agreementId);

        // AIPowerRental.getRentalAgreement itself reverts for unknown ids,
        // before the dispute contract's own "Invalid agreement" check.
        vm.prank(provider);
        vm.expectRevert("Agreement does not exist");
        disputes_.fileDispute(badAgreementId, consumer, DisputeResolution.DisputeType.Payment, "r", bytes32(0));
    }

    function testFuzz_FileDisputeRejectsNonParticipant(address caller) public {
        vm.assume(caller != provider && caller != consumer);

        vm.prank(caller);
        vm.expectRevert("Not agreement participant");
        disputes_.fileDispute(agreementId, consumer, DisputeResolution.DisputeType.Payment, "r", bytes32(0));
    }

    function testFuzz_FileDisputeRejectsWrongRespondent(address wrongRespondent) public {
        vm.assume(wrongRespondent != address(0) && wrongRespondent != consumer && wrongRespondent != provider);

        vm.prank(provider);
        vm.expectRevert("Respondent not in agreement");
        disputes_.fileDispute(agreementId, wrongRespondent, DisputeResolution.DisputeType.Payment, "r", bytes32(0));
    }

    // ---------- evidence ----------

    function testFuzz_SubmitEvidence(bool byInitiator, string calldata data) public {
        vm.assume(bytes(data).length <= 256);
        uint256 disputeId = _file();

        address submitter = byInitiator ? provider : consumer;
        vm.prank(submitter);
        disputes_.submitEvidence(disputeId, "Documents", data);

        DisputeResolution.Evidence[] memory ev = disputes_.getDisputeEvidence(disputeId);
        assertEq(ev.length, 1);
        assertEq(ev[0].submitter, submitter);
        assertEq(uint256(disputes_.getDispute(disputeId).status), uint256(DisputeResolution.DisputeStatus.EvidenceSubmitted));
    }

    function testFuzz_SubmitEvidenceRejectsNonParticipant(address caller) public {
        vm.assume(caller != provider && caller != consumer);
        uint256 disputeId = _file();

        vm.prank(caller);
        vm.expectRevert("Not dispute participant");
        disputes_.submitEvidence(disputeId, "Documents", "x");
    }

    function testFuzz_SubmitEvidenceRejectsAfterDeadline() public {
        uint256 disputeId = _file();

        vm.warp(block.timestamp + 3 days + 1);
        vm.prank(provider);
        vm.expectRevert("Deadline passed");
        disputes_.submitEvidence(disputeId, "Documents", "x");
    }

    function testFuzz_VerifyEvidenceOnlyArbitrator(address caller) public {
        vm.assume(caller != arb1 && caller != arb2 && caller != arb3);
        uint256 disputeId = _file();

        vm.prank(provider);
        disputes_.submitEvidence(disputeId, "Documents", "x");

        vm.prank(caller);
        vm.expectRevert("Not authorized arbitrator");
        disputes_.verifyEvidence(disputeId, 0, true, 80);
    }

    function testFuzz_VerifyEvidence(uint256 score) public {
        uint256 disputeId = _file();

        vm.prank(provider);
        disputes_.submitEvidence(disputeId, "Documents", "x");

        vm.prank(arb1);
        disputes_.verifyEvidence(disputeId, 0, true, score);

        DisputeResolution.Evidence[] memory ev = disputes_.getDisputeEvidence(disputeId);
        assertTrue(ev[0].isValid);
        assertEq(ev[0].verificationScore, score);
        assertEq(ev[0].verifiedBy, arb1);
    }

    // ---------- arbitrators ----------

    function testFuzz_AuthorizeArbitratorOnlyOwner(address caller, address target) public {
        vm.assume(caller != owner);
        vm.assume(target != address(0));

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        disputes_.authorizeArbitrator(target, 50);
    }

    function testFuzz_AuthorizeArbitratorRejectsDuplicate() public {
        vm.expectRevert("Arbitrator already authorized");
        disputes_.authorizeArbitrator(arb1, 50);
    }

    function testFuzz_RevokeArbitrator(address target) public {
        vm.assume(target != address(0) && target != arb1 && target != arb2 && target != arb3);

        disputes_.authorizeArbitrator(target, 50);
        disputes_.revokeArbitrator(target, "misconduct");

        assertFalse(disputes_.authorizedArbitrators(target));
        DisputeResolution.Arbitrator memory a = disputes_.getArbitrator(target);
        assertEq(uint256(a.status), uint256(DisputeResolution.ArbitratorStatus.Suspended));
    }

    function testFuzz_RevokeArbitratorRejectsUnknown(address target) public {
        vm.assume(target != arb1 && target != arb2 && target != arb3);

        vm.expectRevert("Arbitrator not authorized");
        disputes_.revokeArbitrator(target, "n/a");
    }

    function testFuzz_AssignArbitratorsOnlyOwner(address caller) public {
        vm.assume(caller != owner);
        uint256 disputeId = _file();

        address[] memory arbs = new address[](3);
        arbs[0] = arb1;
        arbs[1] = arb2;
        arbs[2] = arb3;

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        disputes_.assignArbitrators(disputeId, arbs);
    }

    function testFuzz_AssignArbitratorsRejectsBadCount(uint8 count) public {
        count = uint8(bound(count, 0, 10));
        vm.assume(count < 3 || count > 5);
        uint256 disputeId = _file();

        address[] memory arbs = new address[](count);
        for (uint256 i = 0; i < count; i++) {
            arbs[i] = address(uint160(0x100 + i));
        }

        vm.expectRevert("Invalid arbitrator count");
        disputes_.assignArbitrators(disputeId, arbs);
    }

    function testFuzz_AssignArbitratorsRejectsUnauthorized(address unauthorized) public {
        vm.assume(unauthorized != arb1 && unauthorized != arb2 && unauthorized != arb3);
        vm.assume(unauthorized != provider && unauthorized != consumer);
        uint256 disputeId = _file();

        address[] memory arbs = new address[](3);
        arbs[0] = arb1;
        arbs[1] = arb2;
        arbs[2] = unauthorized;

        vm.expectRevert("Arbitrator not authorized");
        disputes_.assignArbitrators(disputeId, arbs);
    }

    function testFuzz_AssignArbitratorsRejectsConflictOfInterest() public {
        uint256 disputeId = _file();

        disputes_.authorizeArbitrator(provider, 10);
        address[] memory arbs = new address[](3);
        arbs[0] = arb1;
        arbs[1] = arb2;
        arbs[2] = provider; // initiator is a party

        vm.expectRevert("Conflict of interest");
        disputes_.assignArbitrators(disputeId, arbs);
    }

    function testFuzz_AssignArbitratorsTransitionsStatus() public {
        uint256 disputeId = _fileAndAssign();

        DisputeResolution.Dispute memory d = disputes_.getDispute(disputeId);
        assertEq(d.arbitratorCount, 3);
        assertEq(uint256(d.status), uint256(DisputeResolution.DisputeStatus.ArbitrationInProgress));
        assertEq(disputes_.getArbitratorDisputes(arb1).length, 1);
    }

    // ---------- voting ----------

    function testFuzz_SubmitVoteRejectsUnassignedArbitrator(address unassigned) public {
        vm.assume(unassigned != address(0));
        vm.assume(unassigned != arb1 && unassigned != arb2 && unassigned != arb3);
        uint256 disputeId = _fileAndAssign();

        disputes_.authorizeArbitrator(unassigned, 10);
        vm.prank(unassigned);
        vm.expectRevert("Arbitrator not assigned");
        disputes_.submitArbitrationVote(disputeId, true, 80, "ok");
    }

    function testFuzz_SubmitVoteRejectsDoubleVote() public {
        uint256 disputeId = _fileAndAssign();

        vm.startPrank(arb1);
        disputes_.submitArbitrationVote(disputeId, true, 80, "first");
        vm.expectRevert("Already voted");
        disputes_.submitArbitrationVote(disputeId, true, 80, "second");
        vm.stopPrank();
    }

    function testFuzz_ResolutionInitiatorWins() public {
        uint256 disputeId = _fileAndAssign();

        vm.prank(arb1);
        disputes_.submitArbitrationVote(disputeId, true, 90, "yes");
        vm.prank(arb2);
        disputes_.submitArbitrationVote(disputeId, true, 90, "yes");
        vm.prank(arb3);
        disputes_.submitArbitrationVote(disputeId, false, 50, "no");

        DisputeResolution.Dispute memory d = disputes_.getDispute(disputeId);
        assertEq(uint256(d.status), uint256(DisputeResolution.DisputeStatus.Resolved));
        assertEq(d.winner, provider); // initiator
        assertEq(d.resolutionAmount, 100e18);
    }

    function testFuzz_ResolutionRespondentWins() public {
        uint256 disputeId = _fileAndAssign();

        vm.prank(arb1);
        disputes_.submitArbitrationVote(disputeId, false, 90, "no");
        vm.prank(arb2);
        disputes_.submitArbitrationVote(disputeId, false, 90, "no");
        vm.prank(arb3);
        disputes_.submitArbitrationVote(disputeId, true, 50, "yes");

        DisputeResolution.Dispute memory d = disputes_.getDispute(disputeId);
        assertEq(d.winner, consumer); // respondent
        assertEq(d.resolutionAmount, 0);
    }

    function testFuzz_VoteRejectsWrongStatus() public {
        uint256 disputeId = _file(); // Filed, not ArbitrationInProgress

        vm.prank(arb1);
        vm.expectRevert("Invalid dispute status");
        disputes_.submitArbitrationVote(disputeId, true, 80, "ok");
    }

    // ---------- escalation ----------

    function testFuzz_EscalateOnlyAfterResolved() public {
        uint256 disputeId = _fileAndAssign();

        vm.expectRevert("Cannot escalate unresolved dispute");
        disputes_.escalateDispute(disputeId, "appeal");
    }

    function testFuzz_EscalateResolvedDispute() public {
        uint256 disputeId = _fileAndAssign();

        vm.prank(arb1);
        disputes_.submitArbitrationVote(disputeId, true, 90, "y");
        vm.prank(arb2);
        disputes_.submitArbitrationVote(disputeId, true, 90, "y");
        vm.prank(arb3);
        disputes_.submitArbitrationVote(disputeId, false, 50, "n");

        disputes_.escalateDispute(disputeId, "appeal");

        DisputeResolution.Dispute memory d = disputes_.getDispute(disputeId);
        assertEq(uint256(d.status), uint256(DisputeResolution.DisputeStatus.Escalated));
        assertEq(d.escalationLevel, 2);
        assertTrue(d.isEscalated);
    }

    function testFuzz_EscalateOnlyOwner(address caller) public {
        vm.assume(caller != owner);
        uint256 disputeId = _fileAndAssign();

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        disputes_.escalateDispute(disputeId, "appeal");
    }

    // ---------- views ----------

    function testFuzz_GetDisputeRejectsInvalidId(uint256 disputeId) public {
        vm.assume(disputeId >= disputes_.disputeCounter());

        vm.expectRevert("Dispute does not exist");
        disputes_.getDispute(disputeId);
    }

    function testFuzz_GetActiveDisputes() public {
        _file();
        uint256[] memory active = disputes_.getActiveDisputes();
        assertEq(active.length, 1);
        assertEq(active[0], 0);
    }

    function testFuzz_PauseBlocksFiling() public {
        disputes_.pause();

        vm.prank(provider);
        vm.expectRevert("Pausable: paused");
        disputes_.fileDispute(agreementId, consumer, DisputeResolution.DisputeType.Payment, "r", bytes32(0));
        disputes_.unpause();
    }
}
