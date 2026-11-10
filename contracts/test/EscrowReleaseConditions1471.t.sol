// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/EscrowService.sol";
import "../contracts/AIPowerRental.sol";
import "../contracts/PaymentProcessor.sol";
import "../contracts/ZKReceiptVerifier.sol";
import "../contracts/Groth16Verifier.sol";
import "../contracts/AIToken.sol";

/// #1471 pins: releaseEscrow's condition chain had no branch for
/// Automatic, PerformanceMet or Emergency, so any depositor/beneficiary/
/// arbiter/owner could pay the beneficiary immediately — including
/// bypassing the whole emergency quorum+timelock path.
contract EscrowReleaseConditions1471Test is Test {
    AIToken token;
    AIPowerRental rental;
    PaymentProcessor processor;
    EscrowService escrow;

    address depositor = makeAddr("depositor");
    address beneficiary = makeAddr("beneficiary");
    address arbiter = makeAddr("arbiter");
    address arb1 = makeAddr("arb1");
    address arb2 = makeAddr("arb2");
    address arb3 = makeAddr("arb3");
    address oracle1 = makeAddr("oracle1");
    address oracle2 = makeAddr("oracle2");

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

        escrow.authorizeOracle(oracle1);
        escrow.authorizeOracle(oracle2);
        escrow.authorizeArbiter(arb1);
        escrow.authorizeArbiter(arb2);
        escrow.authorizeArbiter(arb3);
    }

    function _create(
        EscrowService.ReleaseCondition condition
    ) internal returns (uint256 id) {
        vm.prank(depositor);
        id = escrow.createEscrow(
            beneficiary,
            arbiter,
            AMOUNT,
            EscrowService.EscrowType.Standard,
            condition,
            0,
            "release-condition pin"
        );
    }

    /// Automatic mirrors the Manual caller set: the beneficiary must not
    /// be able to self-release; depositor or arbiter can.
    function test_AutomaticReleaseCallerSet() public {
        uint256 id = _create(EscrowService.ReleaseCondition.Automatic);

        vm.prank(beneficiary);
        vm.expectRevert("Automatic release requires depositor or arbiter");
        escrow.releaseEscrow(id, "self release");

        vm.prank(depositor);
        escrow.releaseEscrow(id, "depositor release");
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }

    /// Arbiter may also trigger an Automatic release on a fresh escrow.
    function test_AutomaticReleaseByArbiter() public {
        uint256 id = _create(EscrowService.ReleaseCondition.Automatic);
        vm.prank(arbiter);
        escrow.releaseEscrow(id, "arbiter release");
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }

    /// PerformanceMet fails closed until a performance condition is proven
    /// through the oracle path; once verified (and the delay elapsed) the
    /// escrow releases normally.
    function test_PerformanceMetRequiresVerifiedCondition() public {
        uint256 id = _create(EscrowService.ReleaseCondition.PerformanceMet);

        // No proof at all: every participant is rejected.
        vm.prank(beneficiary);
        vm.expectRevert("Performance condition not met");
        escrow.releaseEscrow(id, "no proof");

        vm.prank(depositor);
        escrow.setReleaseCondition(id, keccak256("perf>=99"), oracle1, "perf proof");

        address[] memory panel = new address[](2);
        panel[0] = oracle1;
        panel[1] = oracle2;
        escrow.assignMultipleOracles(id, panel);

        vm.prank(oracle1);
        escrow.verifyCondition(id, true, 95);
        vm.prank(oracle2);
        escrow.verifyCondition(id, true, 95);

        // Verified but inside the oracle delay: still closed.
        vm.prank(depositor);
        vm.expectRevert("Oracle verification delay not elapsed");
        escrow.releaseEscrow(id, "too early");

        vm.warp(block.timestamp + escrow.oracleVerificationDelay());
        vm.prank(depositor);
        escrow.releaseEscrow(id, "performance verified");
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }

    /// PerformanceMet with a negative oracle verdict never releases via
    /// releaseEscrow.
    function test_PerformanceMetNegativeVerdictStaysClosed() public {
        uint256 id = _create(EscrowService.ReleaseCondition.PerformanceMet);
        vm.prank(depositor);
        escrow.setReleaseCondition(id, keccak256("perf>=99"), oracle1, "perf proof");

        address[] memory panel = new address[](1);
        panel[0] = oracle1;
        escrow.assignMultipleOracles(id, panel);

        vm.prank(oracle1);
        escrow.verifyCondition(id, false, 10);

        vm.warp(block.timestamp + escrow.oracleVerificationDelay() + 1);
        vm.prank(depositor);
        vm.expectRevert("Performance condition not met");
        escrow.releaseEscrow(id, "failed perf");
        assertEq(token.balanceOf(beneficiary), 0);
    }

    /// Emergency escrows must go through the quorum+timelock executor —
    /// releaseEscrow reverts for every participant even after approval.
    function test_EmergencyReleaseEscrowRejectsDirectRelease() public {
        uint256 id = _create(EscrowService.ReleaseCondition.Emergency);

        // Even before any request, direct release is impossible.
        vm.prank(beneficiary);
        vm.expectRevert("Emergency release requires executeEmergencyRelease");
        escrow.releaseEscrow(id, "shortcut");

        // Approve an emergency release through the proper path.
        escrow.setEmergencyReleaseTimelock(1);
        vm.prank(depositor);
        escrow.requestEmergencyRelease(id, "stuck");
        vm.prank(arb1);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb2);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb3);
        escrow.voteEmergencyRelease(id, true);

        // Approved — but releaseEscrow still must not shortcut the executor.
        vm.prank(beneficiary);
        vm.expectRevert("Emergency release requires executeEmergencyRelease");
        escrow.releaseEscrow(id, "shortcut after approval");
        vm.prank(depositor);
        vm.expectRevert("Emergency release requires executeEmergencyRelease");
        escrow.releaseEscrow(id, "shortcut after approval");

        // The legitimate path still works once the timelock elapses.
        vm.warp(block.timestamp + 2);
        escrow.executeEmergencyRelease(id);
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }
}
