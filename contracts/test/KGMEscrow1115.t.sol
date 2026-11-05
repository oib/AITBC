// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/KnowledgeGraphMarket.sol";
import "../contracts/AIToken.sol";

/// #1115 pins: purchaseGraph used to pay the creator immediately and rely on
/// the creator to deliver the key (no refund, no escrow), take no maxPrice,
/// scan purchases linearly, and let withdrawPlatformFees sweep every token.
contract KGMEscrow1115Test is Test {
    AIToken token;
    KnowledgeGraphMarket market;
    address creator = makeAddr("creator");
    address buyer = makeAddr("buyer");
    address owner;

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days);
        market = new KnowledgeGraphMarket(address(token));
        owner = address(this);
        token.mint(buyer, 100e18);
        vm.prank(buyer);
        token.approve(address(market), 100e18);
    }

    function _buy(uint256 price, uint256 maxPrice) internal returns (uint256 id) {
        vm.prank(creator);
        id = market.listGraph("QmX", "uri", price);
        vm.prank(buyer);
        market.purchaseGraph(id, maxPrice);
    }

    function test_MaxPriceBoundsPurchase() public {
        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", 10e18);
        vm.prank(buyer);
        vm.expectRevert("Price above maxPrice");
        market.purchaseGraph(id, 9e18);
        assertFalse(market.hasPurchased(id, buyer));
    }

    function test_PaymentEscrowedUntilDelivery() public {
        uint256 id = _buy(10e18, 10e18);
        // Creator paid nothing yet; the market escrows the full price.
        assertEq(token.balanceOf(creator), 0);
        assertEq(token.balanceOf(address(market)), 10e18);
        // Delivery releases creatorAmount and accrues only the fee.
        vm.prank(creator);
        market.deliverDecryptionKey(id, buyer, "k");
        assertEq(token.balanceOf(creator), 10e18 - (10e18 * 250) / 10000);
        assertEq(market.accruedPlatformFees(), (10e18 * 250) / 10000);
    }

    function test_RefundAfterWindowWithoutKey() public {
        uint256 id = _buy(10e18, 10e18);
        vm.prank(buyer);
        vm.expectRevert("Delivery window still open");
        market.refundPurchase(id);
        vm.warp(block.timestamp + 7 days);
        uint256 before = token.balanceOf(buyer);
        vm.prank(buyer);
        market.refundPurchase(id);
        assertEq(token.balanceOf(buyer), before + 10e18);
        assertFalse(market.hasPurchased(id, buyer));
        // Creator can no longer get paid by delivering after a refund.
        vm.prank(creator);
        vm.expectRevert("Buyer has not purchased");
        market.deliverDecryptionKey(id, buyer, "k");
    }

    function test_NoRefundOnceDelivered() public {
        uint256 id = _buy(10e18, 10e18);
        vm.prank(creator);
        market.deliverDecryptionKey(id, buyer, "k");
        vm.warp(block.timestamp + 7 days);
        vm.prank(buyer);
        vm.expectRevert("Key delivered");
        market.refundPurchase(id);
    }

    function test_WithdrawOnlyAccruedFees() public {
        uint256 id = _buy(10e18, 10e18);
        // Owner cannot sweep escrowed buyer funds — only accrued fees move.
        vm.expectRevert("No fees accrued");
        market.withdrawPlatformFees(owner);
        vm.prank(creator);
        market.deliverDecryptionKey(id, buyer, "k");
        uint256 fees = market.accruedPlatformFees();
        uint256 before = token.balanceOf(owner);
        market.withdrawPlatformFees(owner);
        assertEq(token.balanceOf(owner), before + fees);
        // Undelivered escrow stays in the contract for the buyer's refund.
        vm.prank(creator);
        uint256 id2 = market.listGraph("QmY", "uri", 5e18);
        vm.prank(buyer);
        market.purchaseGraph(id2, 5e18);
        assertEq(token.balanceOf(address(market)), 5e18);
    }
}
