// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/PaymentProcessor.sol";
import "../contracts/AIPowerRental.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract PP1102MockToken is ERC20 {
    constructor() ERC20("T", "T") { _mint(msg.sender, 1e24); }
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

/// #1102 pins: _releasePayment pays the platform fee to the owner but used
/// to leave payment.platformFee set, so claimPlatformFee could pay the same
/// fee a second time out of other users' funds. Total fees out must never
/// exceed fees in; the claim path stays for the dispute-resolution leg.
contract PlatformFeePaidOnce1102Test is Test {
    PP1102MockToken token;
    PaymentProcessor processor;
    address owner_ = address(this);
    address payer = makeAddr("payer");
    address payee = makeAddr("payee");

    uint256 constant AMOUNT = 100e18;
    uint256 constant PLATFORM_FEE = (AMOUNT * 250) / 10000; // 2.5e18
    uint256 constant DISPUTE_FEE = (AMOUNT * 100) / 10000; // 1e18

    function setUp() public {
        token = new PP1102MockToken();
        // PaymentProcessor only stores the rental address; dummy verifiers are fine.
        AIPowerRental rental = new AIPowerRental(address(token), address(0x1), address(0x2));
        processor = new PaymentProcessor(address(token), address(rental));
        processor.authorizePayer(payer);
        processor.authorizePayee(payee);
        token.mint(payer, 1e21);
        vm.prank(payer);
        token.approve(address(processor), type(uint256).max);
    }

    function _createConfirmedPayment() internal returns (uint256 paymentId) {
        vm.startPrank(payer);
        paymentId = processor.createPayment(
            payee, AMOUNT, bytes32(0), "job", PaymentProcessor.ReleaseCondition.Manual
        );
        processor.confirmPayment(paymentId, keccak256("tx"));
        vm.stopPrank();
    }

    /// Releasing pays the fee once; a claim afterwards must revert — the
    /// fee was already paid out, so platformFee is zero.
    function test_ReleaseZerosPlatformFeeSoClaimReverts() public {
        uint256 paymentId = _createConfirmedPayment();
        uint256 ownerBefore = token.balanceOf(owner_);

        vm.prank(payer);
        processor.releasePayment(paymentId);
        assertEq(token.balanceOf(owner_), ownerBefore + PLATFORM_FEE, "fee paid once at release");

        vm.expectRevert("No platform fee to claim");
        processor.claimPlatformFee(paymentId); // must revert, not pay again
        assertEq(token.balanceOf(owner_), ownerBefore + PLATFORM_FEE, "fee must not be paid twice");
    }

    /// The claim path still works for the dispute-resolution leg, where the
    /// payment reaches Released without the release-time fee payout — and
    /// only once.
    function test_DisputeResolutionKeepsSingleClaimPath() public {
        uint256 paymentId = _createConfirmedPayment();
        vm.prank(payer);
        processor.initiateDispute(paymentId, "bad job");
        processor.resolveDispute(paymentId, AMOUNT, false);

        processor.claimPlatformFee(paymentId); // first claim succeeds
        vm.expectRevert("No platform fee to claim");
        processor.claimPlatformFee(paymentId); // second claim must revert
    }
}
