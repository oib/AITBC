// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/EscrowService.sol";
import "../contracts/AIPowerRental.sol";
import "../contracts/PaymentProcessor.sol";
import "../contracts/ZKReceiptVerifier.sol";
import "../contracts/Groth16Verifier.sol";
import "../contracts/AIToken.sol";

/// #1470 pins: the multi-oracle branch of verifyCondition accepted verdicts
/// from any authorized oracle (not just the assigned panel), the
/// single-oracle path released instantly with no oracleVerificationDelay,
/// and assignMultipleOracles carried stale votes across a panel rotation.
contract EscrowOracleVerify1470Test is Test {
    AIToken token;
    AIPowerRental rental;
    PaymentProcessor processor;
    EscrowService escrow;

    address depositor = makeAddr("depositor");
    address beneficiary = makeAddr("beneficiary");
    address oracle1 = makeAddr("oracle1");
    address oracle2 = makeAddr("oracle2");
    address oracle3 = makeAddr("oracle3");
    address outsider = makeAddr("outsider"); // authorized but never assigned

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
        escrow.authorizeOracle(oracle3);
        escrow.authorizeOracle(outsider);
    }

    function _createOracleEscrow() internal returns (uint256 id) {
        vm.prank(depositor);
        id = escrow.createEscrow(
            beneficiary,
            address(0),
            AMOUNT,
            EscrowService.EscrowType.Conditional,
            EscrowService.ReleaseCondition.OracleVerified,
            0,
            "oracle pin"
        );
    }

    /// conditionalReleases auto-getter: (escrowId, condition, conditionMet,
    /// oracle, verificationTime, conditionData, confidence,
    /// verificationCount, requiredVerifications, finalVerificationTime).
    function _cond(
        uint256 id
    )
        internal
        view
        returns (
            bool conditionMetFlag,
            uint256 verificationCount,
            uint256 finalVerificationTime
        )
    {
        (, , bool met, , , , , uint256 count, , uint256 finalTime) = escrow.conditionalReleases(id);
        return (met, count, finalTime);
    }

    function _panel2() internal view returns (address[] memory panel) {
        panel = new address[](2);
        panel[0] = oracle1;
        panel[1] = oracle2;
    }

    /// An authorized oracle that is not on the assigned panel must not be
    /// able to cast a verdict or advance verificationCount.
    function test_UnassignedOracleCannotVerify() public {
        uint256 id = _createOracleEscrow();
        escrow.assignMultipleOracles(id, _panel2());

        vm.prank(outsider);
        vm.expectRevert("Not assigned oracle");
        escrow.verifyCondition(id, true, 90);

        // The rejected call must not have moved the tally.
        (, uint256 count, ) = _cond(id);
        assertEq(count, 0);

        // Legitimate panel still works.
        vm.prank(oracle1);
        escrow.verifyCondition(id, true, 90);
        vm.prank(oracle2);
        escrow.verifyCondition(id, true, 90);
        (, uint256 count2, ) = _cond(id);
        assertEq(count2, 2);
    }

    /// Once the panel threshold is met the escrow must still wait out
    /// oracleVerificationDelay before releaseEscrow pays out.
    function test_MultiOracleReleaseWaitsForDelay() public {
        uint256 id = _createOracleEscrow();
        escrow.assignMultipleOracles(id, _panel2());

        vm.prank(oracle1);
        escrow.verifyCondition(id, true, 90);
        vm.prank(oracle2);
        escrow.verifyCondition(id, true, 90);

        (bool met, , uint256 finalTime) = _cond(id);
        assertTrue(met);
        assertEq(finalTime, block.timestamp);

        vm.prank(depositor);
        vm.expectRevert("Oracle verification delay not elapsed");
        escrow.releaseEscrow(id, "manual");

        vm.warp(block.timestamp + escrow.oracleVerificationDelay());
        vm.prank(depositor);
        escrow.releaseEscrow(id, "manual");
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }

    /// The single-oracle path (empty assignedOracles, legacy oracle field
    /// set) must honour oracleVerificationDelay too — before the fix it
    /// paid the beneficiary inside verifyCondition.
    function test_SingleOraclePathHonoursDelay() public {
        vm.prank(depositor);
        uint256 id = escrow.createEscrow(
            beneficiary,
            address(0),
            AMOUNT,
            EscrowService.EscrowType.Conditional,
            EscrowService.ReleaseCondition.OracleVerified,
            0,
            "single oracle"
        );
        vm.prank(depositor);
        escrow.setReleaseCondition(id, keccak256("perf"), oracle1, "perf met?");

        // setReleaseCondition records the oracle but also pushes it into
        // assignedOracles; an empty assignMultipleOracles panel is the only
        // route to the legacy single-oracle branch.
        address[] memory empty = new address[](0);
        escrow.assignMultipleOracles(id, empty);

        vm.prank(oracle1);
        escrow.verifyCondition(id, true, 90);

        // No instant release: beneficiary must not have been paid.
        assertEq(token.balanceOf(beneficiary), 0);
        (bool met, , uint256 finalTime) = _cond(id);
        assertTrue(met);
        assertEq(finalTime, block.timestamp);

        vm.prank(depositor);
        vm.expectRevert("Oracle verification delay not elapsed");
        escrow.releaseEscrow(id, "manual");

        vm.warp(block.timestamp + escrow.oracleVerificationDelay());
        vm.prank(depositor);
        escrow.releaseEscrow(id, "manual");
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }

    /// Re-assigning the panel mid-vote must reset the tally, the met flag
    /// and every per-oracle stamp — stale votes cannot satisfy the new
    /// panel and a re-added oracle may vote again.
    function test_PanelRotationResetsVoteState() public {
        uint256 id = _createOracleEscrow();
        escrow.assignMultipleOracles(id, _panel2());

        vm.prank(oracle1);
        escrow.verifyCondition(id, true, 90);
        vm.prank(oracle2);
        escrow.verifyCondition(id, true, 90);
        (bool metBefore, , ) = _cond(id);
        assertTrue(metBefore);

        // Rotate to a fresh panel that still includes oracle1.
        address[] memory panel2 = new address[](2);
        panel2[0] = oracle1;
        panel2[1] = oracle3;
        escrow.assignMultipleOracles(id, panel2);

        // Tally and met flag are reset; releaseEscrow must fail closed.
        (bool metAfter, uint256 count, uint256 finalAfter) = _cond(id);
        assertEq(count, 0);
        assertFalse(metAfter);
        assertEq(finalAfter, 0);

        vm.prank(depositor);
        vm.expectRevert("Condition not met");
        escrow.releaseEscrow(id, "manual");

        // oracle1's old stamp was cleared: it may verify on the new panel,
        // and the old oracle2 is no longer assigned.
        vm.prank(oracle1);
        escrow.verifyCondition(id, true, 90);
        vm.prank(oracle2);
        vm.expectRevert("Not assigned oracle");
        escrow.verifyCondition(id, true, 90);
        vm.prank(oracle3);
        escrow.verifyCondition(id, true, 90);

        (bool met2, uint256 count2, ) = _cond(id);
        assertEq(count2, 2);
        assertTrue(met2);
    }

    /// Single-oracle negative verdicts still record conditionMet=false and
    /// never release.
    function test_SingleOracleNegativeVerdictDoesNotRelease() public {
        vm.prank(depositor);
        uint256 id = escrow.createEscrow(
            beneficiary,
            address(0),
            AMOUNT,
            EscrowService.EscrowType.Conditional,
            EscrowService.ReleaseCondition.OracleVerified,
            0,
            "single oracle negative"
        );
        vm.prank(depositor);
        escrow.setReleaseCondition(id, keccak256("perf"), oracle1, "perf met?");
        address[] memory empty = new address[](0);
        escrow.assignMultipleOracles(id, empty);

        vm.prank(oracle1);
        escrow.verifyCondition(id, false, 10);

        assertEq(token.balanceOf(beneficiary), 0);
        (bool met, , ) = _cond(id);
        assertFalse(met);

        vm.prank(depositor);
        vm.expectRevert("Condition not met");
        escrow.releaseEscrow(id, "manual");
    }
}
