// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/KnowledgeGraphMarket.sol";
import "../contracts/AIToken.sol";

/// #1154 pins: refundPurchase clears hasPurchased so the buyer can re-buy, but
/// the buyer-indexed Purchase slot kept refunded=true — re-purchased escrow
/// was undeliverable ("Purchase refunded" forever).
contract KGMRepurchase1154Test is Test {
    AIToken token;
    KnowledgeGraphMarket market;
    address creator = makeAddr("creator");
    address buyer = makeAddr("buyer");

    function setUp() public {
        token = new AIToken(0);
        vm.warp(block.timestamp + 2 days);
        market = new KnowledgeGraphMarket(address(token));
        token.mint(buyer, 100e18);
        vm.prank(buyer);
        token.approve(address(market), 100e18);
    }

    function _buy(uint256 price) internal returns (uint256 id) {
        vm.prank(creator);
        id = market.listGraph("QmX", "uri", price);
        vm.prank(buyer);
        market.purchaseGraph(id, price);
    }

    function test_RepurchaseAfterRefundIsDeliverable() public {
        // First purchase, window lapses, refund.
        uint256 id = _buy(10e18);
        vm.warp(block.timestamp + 7 days);
        vm.prank(buyer);
        market.refundPurchase(id);
        // Re-purchase the same graph.
        vm.prank(buyer);
        market.purchaseGraph(id, 10e18);
        // Creator must be able to deliver the NEW key, and escrow pays once.
        vm.prank(creator);
        market.deliverDecryptionKey(id, buyer, "newkey");
        vm.prank(buyer);
        assertEq(market.getMyPurchaseKey(id), "newkey");
        // Second delivery blocked: escrow already paid out once.
        vm.prank(creator);
        vm.expectRevert("Key already delivered");
        market.deliverDecryptionKey(id, buyer, "again");
    }

    function test_SecondRefundCannotDoublePay() public {
        uint256 id = _buy(10e18);
        vm.warp(block.timestamp + 7 days);
        vm.prank(buyer);
        market.refundPurchase(id);
        uint256 bal = token.balanceOf(buyer);
        vm.prank(buyer);
        vm.expectRevert("Not purchased");
        market.refundPurchase(id);
        assertEq(token.balanceOf(buyer), bal);
    }
}
