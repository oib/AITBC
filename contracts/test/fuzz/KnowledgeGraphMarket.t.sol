// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/KnowledgeGraphMarket.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract KnowledgeGraphMarketFuzzTest is Test {
    KnowledgeGraphMarket public market;
    MockToken public token;
    address public creator;
    address public buyer;

    function setUp() public {
        creator = address(0x1);
        buyer = address(0x2);

        token = new MockToken();
        market = new KnowledgeGraphMarket(address(token));

        token.transfer(buyer, 500_000 * 10**18);
    }

    function testFuzz_ListGraph(string calldata cid, string calldata uri, uint256 price) public {
        vm.assume(bytes(cid).length <= 128 && bytes(uri).length <= 128);

        vm.prank(creator);
        uint256 id = market.listGraph(cid, uri, price);

        (uint256 graphId, address graphCreator, string memory storedCid, string memory storedUri, uint256 storedPrice,, bool isActive) =
            market.graphs(id);
        assertEq(graphId, id);
        assertEq(graphCreator, creator);
        assertEq(storedCid, cid);
        assertEq(storedUri, uri);
        assertEq(storedPrice, price);
        assertTrue(isActive);
    }

    function testFuzz_ListGraphIncrementsId(uint8 n) public {
        vm.assume(n > 0 && n <= 20);

        for (uint256 i = 0; i < n; i++) {
            vm.prank(creator);
            uint256 id = market.listGraph("QmX", "uri", 1e18);
            assertEq(id, i);
        }
        assertEq(market.graphCounter(), n);
    }

    function testFuzz_UpdateGraphOnlyCreator(address caller, uint256 newPrice) public {
        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", 1e18);

        if (caller == creator) {
            vm.prank(caller);
            market.updateGraph(id, newPrice, false);
            (, , , , uint256 storedPrice, , bool isActive) = market.graphs(id);
            assertEq(storedPrice, newPrice);
            assertFalse(isActive);
        } else {
            vm.prank(caller);
            vm.expectRevert("Not creator");
            market.updateGraph(id, newPrice, false);
        }
    }

    function testFuzz_PurchaseGraph(uint256 price) public {
        price = bound(price, 1, 400_000 * 10**18);

        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", price);

        uint256 creatorBefore = token.balanceOf(creator);
        vm.startPrank(buyer);
        token.approve(address(market), price);
        market.purchaseGraph(id);
        vm.stopPrank();

        uint256 fee = (price * 250) / 10000;
        assertEq(token.balanceOf(creator), creatorBefore + price - fee);
        assertEq(token.balanceOf(address(market)), fee);
        assertTrue(market.hasPurchased(id, buyer));
        (, , , , , uint256 totalSales, ) = market.graphs(id);
        assertEq(totalSales, 1);
    }

    function testFuzz_PurchaseRejectsInactive() public {
        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", 1e18);
        vm.prank(creator);
        market.updateGraph(id, 1e18, false);

        vm.prank(buyer);
        vm.expectRevert("Graph inactive");
        market.purchaseGraph(id);
    }

    function testFuzz_PurchaseRejectsOwnGraph() public {
        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", 1e18);

        token.transfer(creator, 10e18);
        vm.startPrank(creator);
        token.approve(address(market), 1e18);
        vm.expectRevert("Cannot buy own graph");
        market.purchaseGraph(id);
        vm.stopPrank();
    }

    function testFuzz_PurchaseRejectsDouble(uint256 price) public {
        price = bound(price, 1, 100_000 * 10**18);

        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", price);

        vm.startPrank(buyer);
        token.approve(address(market), price * 2);
        market.purchaseGraph(id);
        vm.expectRevert("Already purchased");
        market.purchaseGraph(id);
        vm.stopPrank();
    }

    function testFuzz_DeliverAndReadKey(string calldata key) public {
        vm.assume(bytes(key).length <= 128);

        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", 1e18);

        vm.startPrank(buyer);
        token.approve(address(market), 1e18);
        market.purchaseGraph(id);
        vm.stopPrank();

        vm.prank(creator);
        market.deliverDecryptionKey(id, buyer, key);

        vm.prank(buyer);
        assertEq(market.getMyPurchaseKey(id), key);
    }

    function testFuzz_DeliverKeyOnlyCreator(address caller, uint256 price) public {
        price = bound(price, 1, 100_000 * 10**18);
        vm.assume(caller != creator);

        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", price);

        vm.startPrank(buyer);
        token.approve(address(market), price);
        market.purchaseGraph(id);
        vm.stopPrank();

        vm.prank(caller);
        vm.expectRevert("Not creator");
        market.deliverDecryptionKey(id, buyer, "k");
    }

    function testFuzz_GetKeyRevertsIfNotPurchased(address reader) public {
        vm.prank(creator);
        uint256 id = market.listGraph("QmX", "uri", 1e18);

        vm.prank(reader);
        vm.expectRevert("Not purchased");
        market.getMyPurchaseKey(id);
    }
}
