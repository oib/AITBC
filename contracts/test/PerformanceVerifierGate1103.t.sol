// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/PaymentProcessor.sol";
import "../contracts/AIPowerRental.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract PP1103MockToken is ERC20 {
    constructor() ERC20("T", "T") { _mint(msg.sender, 1e24); }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

/// #1103 pins: Performance and DisputeResolution release conditions used to
/// check nothing in releasePayment, so the payee could release confirmed
/// funds to itself at once; the dispute fee pulled at creation was never
/// paid out or refunded; and a created-but-unconfirmed payment had no
/// cancel path.
contract PerformanceVerifierGate1103Test is Test {
    PP1103MockToken token;
    PaymentProcessor processor;
    address owner_ = address(this);
    address payer = makeAddr("payer");
    address payee = makeAddr("payee");
    address verifier = makeAddr("verifier");

    uint256 constant AMOUNT = 100e18;
    uint256 constant PLATFORM_FEE = (AMOUNT * 250) / 10000; // 2.5e18
    uint256 constant DISPUTE_FEE = (AMOUNT * 100) / 10000; // 1e18

    function setUp() public {
        token = new PP1103MockToken();
        AIPowerRental rental = new AIPowerRental(address(token), address(0x1), address(0x2));
        processor = new PaymentProcessor(address(token), address(rental));
        processor.authorizePayer(payer);
        processor.authorizePayee(payee);
        processor.authorizeReleaseVerifier(verifier);
        token.mint(payer, 1e21);
        vm.prank(payer);
        token.approve(address(processor), type(uint256).max);
    }

    function _createConfirmed(
        PaymentProcessor.ReleaseCondition cond
    ) internal returns (uint256 paymentId) {
        vm.startPrank(payer);
        paymentId = processor.createPayment(payee, AMOUNT, bytes32(0), "job", cond);
        processor.confirmPayment(paymentId, keccak256("tx"));
        vm.stopPrank();
    }

    /// A payee must not be able to release a Performance payment on its own;
    /// only after a verifier approves can the release go through.
    function test_PayeeCannotReleasePerformanceAlone() public {
        uint256 paymentId = _createConfirmed(PaymentProcessor.ReleaseCondition.Performance);

        vm.prank(payee);
        vm.expectRevert("Release not approved by verifier");
        processor.releasePayment(paymentId);
        assertEq(token.balanceOf(payee), 0, "payee must not receive funds");

        vm.prank(verifier);
        processor.approveRelease(paymentId);

        vm.prank(payee);
        processor.releasePayment(paymentId);
        assertEq(token.balanceOf(payee), AMOUNT, "approved release pays payee");
    }

    /// Same gate for the DisputeResolution condition.
    function test_DisputeResolutionConditionGatedOnVerifier() public {
        uint256 paymentId = _createConfirmed(PaymentProcessor.ReleaseCondition.DisputeResolution);

        vm.prank(payer);
        vm.expectRevert("Release not approved by verifier");
        processor.releasePayment(paymentId);

        vm.prank(verifier);
        processor.approveRelease(paymentId);
        processor.releasePayment(paymentId);
        assertEq(token.balanceOf(payee), AMOUNT, "approved release pays payee");
    }

    /// A random caller is not a verifier and cannot approve.
    function test_NonVerifierCannotApprove() public {
        uint256 paymentId = _createConfirmed(PaymentProcessor.ReleaseCondition.Performance);
        vm.prank(payee);
        vm.expectRevert("Not a release verifier");
        processor.approveRelease(paymentId);
    }

    /// The dispute fee collected at creation is accounted: on a clean
    /// release it is refunded to the payer, not stranded.
    function test_DisputeFeeRefundedOnCleanRelease() public {
        uint256 paymentId = _createConfirmed(PaymentProcessor.ReleaseCondition.Manual);
        uint256 payerBefore = token.balanceOf(payer);

        vm.prank(payer);
        processor.releasePayment(paymentId);
        assertEq(token.balanceOf(payer), payerBefore + DISPUTE_FEE, "dispute fee refunded to payer");
        assertEq(token.balanceOf(address(processor)), 0, "nothing stranded in contract");
    }

    /// On a resolved dispute the fee is paid out (to the owner acting for
    /// arbitration), not stranded either.
    function test_DisputeFeePaidOutOnResolution() public {
        uint256 paymentId = _createConfirmed(PaymentProcessor.ReleaseCondition.Manual);
        uint256 ownerBefore = token.balanceOf(owner_);

        vm.prank(payer);
        processor.initiateDispute(paymentId, "bad job");
        processor.resolveDispute(paymentId, AMOUNT, false);
        // owner gets dispute fee now + platform fee via claim
        processor.claimPlatformFee(paymentId);
        assertEq(
            token.balanceOf(owner_),
            ownerBefore + DISPUTE_FEE + PLATFORM_FEE,
            "dispute fee paid to owner on resolution"
        );
        assertEq(token.balanceOf(address(processor)), 0, "nothing stranded in contract");
    }

    /// A created-but-unconfirmed payment can be cancelled after the confirm
    /// timeout with a full refund (amount + both fees).
    function test_TimeoutCancelRefundsEverything() public {
        vm.prank(payer);
        uint256 paymentId = processor.createPayment(
            payee, AMOUNT, bytes32(0), "job", PaymentProcessor.ReleaseCondition.Manual
        );
        uint256 payerBefore = token.balanceOf(payer);

        // early cancel must fail
        vm.prank(payer);
        vm.expectRevert("Confirm timeout not reached");
        processor.cancelPayment(paymentId);

        vm.warp(block.timestamp + processor.confirmTimeout() + 1);
        vm.prank(payer);
        processor.cancelPayment(paymentId);
        assertEq(
            token.balanceOf(payer),
            payerBefore + AMOUNT + PLATFORM_FEE + DISPUTE_FEE,
            "cancel refunds amount and fees"
        );
        assertEq(token.balanceOf(address(processor)), 0, "nothing stranded in contract");
    }
}
