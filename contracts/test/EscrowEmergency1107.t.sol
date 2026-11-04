// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/EscrowService.sol";
import "../contracts/AIPowerRental.sol";
import "../contracts/PaymentProcessor.sol";
import "../contracts/ZKReceiptVerifier.sol";
import "../contracts/Groth16Verifier.sol";
import "../contracts/AIToken.sol";

/// #1107 pins: an approved emergency release used to be unexecutable
/// (the timelock was tested in the same call that stamped approvalTime),
/// the oracle verification delay was never enforced on a manual release,
/// and the platform fee was stranded on a refund for every non-compute type.
contract EscrowEmergency1107Test is Test {
    AIToken token;
    AIPowerRental rental;
    PaymentProcessor processor;
    EscrowService escrow;

    address depositor = makeAddr("depositor");
    address beneficiary = makeAddr("beneficiary");
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

        escrow.authorizeArbiter(arb1);
        escrow.authorizeArbiter(arb2);
        escrow.authorizeArbiter(arb3);
        escrow.authorizeOracle(oracle1);
        escrow.authorizeOracle(oracle2);
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

    function _approveEmergency(uint256 id) internal {
        vm.prank(depositor);
        escrow.requestEmergencyRelease(id, "stuck");
        vm.prank(arb1);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb2);
        escrow.voteEmergencyRelease(id, true);
        vm.prank(arb3);
        escrow.voteEmergencyRelease(id, true);
    }

    /// The core bug: approval stamped approvalTime and tested the timelock in
    /// the same call, so nothing ever released. A separate executor must run
    /// the release once the timelock has elapsed.
    function test_EmergencyReleaseExecutesAfterTimelock() public {
        uint256 id = _createStandard();
        _approveEmergency(id);

        vm.warp(block.timestamp + escrow.emergencyReleaseTimelock());
        escrow.executeEmergencyRelease(id);

        assertEq(token.balanceOf(beneficiary), AMOUNT);
        (, , , , , , , bool isReleased, ) = escrow.getEscrowAccount(id);
        assertTrue(isReleased);
    }

    /// The executor must actually enforce the timelock, not just exist.
    function test_EmergencyReleaseRevertsBeforeTimelock() public {
        uint256 id = _createStandard();
        _approveEmergency(id);

        vm.expectRevert("Emergency release timelock not elapsed");
        escrow.executeEmergencyRelease(id);
    }

    function test_EmergencyReleaseRevertsWithoutApproval() public {
        uint256 id = _createStandard();
        vm.expectRevert("Emergency release not approved");
        escrow.executeEmergencyRelease(id);
    }

    /// Multi-oracle verification stamps finalVerificationTime; a manual
    /// releaseEscrow must respect oracleVerificationDelay — before the fix it
    /// only checked conditionMet, so the delay was never enforced anywhere.
    function test_OracleVerificationDelayEnforcedOnManualRelease() public {
        vm.prank(depositor);
        uint256 id = escrow.createEscrow(
            beneficiary,
            address(0),
            AMOUNT,
            EscrowService.EscrowType.Conditional,
            EscrowService.ReleaseCondition.OracleVerified,
            0,
            "oracle pin"
        );

        address[] memory oracles = new address[](2);
        oracles[0] = oracle1;
        oracles[1] = oracle2;
        escrow.assignMultipleOracles(id, oracles);

        vm.prank(oracle1);
        escrow.verifyCondition(id, true, 90);
        vm.prank(oracle2);
        escrow.verifyCondition(id, true, 90);

        // Condition is met but the verification delay has not elapsed.
        vm.prank(depositor);
        vm.expectRevert("Oracle verification delay not elapsed");
        escrow.releaseEscrow(id, "manual");

        vm.warp(block.timestamp + escrow.oracleVerificationDelay());
        vm.prank(depositor);
        escrow.releaseEscrow(id, "manual");
        assertEq(token.balanceOf(beneficiary), AMOUNT);
    }

    /// The depositor pays amount + platformFee in for every escrow type, but
    /// only ProtectedCompute refunds used to return the fee — for every other
    /// type it stayed stranded in the contract.
    function test_RefundReturnsPlatformFeeForStandardEscrow() public {
        uint256 before_ = token.balanceOf(depositor);
        uint256 id = _createStandard();
        uint256 afterCreate = token.balanceOf(depositor);
        assertLt(afterCreate, before_); // amount + fee were pulled in

        vm.prank(depositor);
        escrow.refundEscrow(id, "cancelled");

        assertEq(token.balanceOf(depositor), before_);
    }
}
