// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/AgentServiceMarketplace.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract AgentServiceMarketplaceFuzzTest is Test {
    AgentServiceMarketplace public marketplace;
    MockToken public token;
    address public owner;
    address public provider;
    address public consumer;

    function setUp() public {
        owner = address(this);
        provider = address(0x1);
        consumer = address(0x2);

        token = new MockToken();
        marketplace = new AgentServiceMarketplace(address(token));

        token.transfer(consumer, 100_000 * 10**18);
        token.transfer(provider, 100_000 * 10**18);
    }

    function testFuzz_RegisterService(uint256 pricePerUse, uint256 subPrice, bool subAvailable) public {
        pricePerUse = bound(pricePerUse, 1, 10_000 * 10**18);
        subPrice = bound(subPrice, 1, 10_000 * 10**18);

        vm.prank(provider);
        uint256 serviceId = marketplace.registerService("ipfs://test", pricePerUse, subPrice, subAvailable);

        assertEq(serviceId, 0);
        (uint256 id, address providerAgent, , uint256 ppu, uint256 spm, bool subAvail, bool isActive, , , ) =
            marketplace.services(serviceId);
        assertEq(id, serviceId);
        assertEq(providerAgent, provider);
        assertEq(ppu, pricePerUse);
        assertEq(spm, subPrice);
        assertEq(subAvail, subAvailable);
        assertTrue(isActive);
        assertEq(marketplace.providerServices(provider, 0), serviceId);
    }

    function testFuzz_RegisterServiceRejectsEmptyURI() public {
        vm.prank(provider);
        vm.expectRevert("Invalid URI");
        marketplace.registerService("", 1e18, 10e18, true);
    }

    function testFuzz_UpdateServiceOnlyProvider(address caller) public {
        vm.assume(caller != provider);

        vm.prank(provider);
        marketplace.registerService("ipfs://test", 1e18, 10e18, true);

        vm.prank(caller);
        vm.expectRevert("Not service provider");
        marketplace.updateService(0, 2e18, 20e18, false, true);
    }

    function testFuzz_PurchaseService(uint256 price) public {
        price = bound(price, 1, 50_000 * 10**18);

        vm.prank(provider);
        uint256 serviceId = marketplace.registerService("ipfs://test", price, 10e18, true);

        uint256 providerBefore = token.balanceOf(provider);
        vm.startPrank(consumer);
        token.approve(address(marketplace), price);
        marketplace.purchaseService(serviceId);
        vm.stopPrank();

        uint256 fee = (price * 250) / 10000;
        assertEq(token.balanceOf(provider), providerBefore + price - fee);

        (, , , , , , , uint256 totalUses, uint256 totalRevenue, ) = marketplace.services(serviceId);
        assertEq(totalUses, 1);
        assertEq(totalRevenue, price - fee);
    }

    function testFuzz_PurchaseServiceRejectsInactive() public {
        vm.prank(provider);
        marketplace.registerService("ipfs://test", 1e18, 10e18, true);
        vm.prank(provider);
        marketplace.updateService(0, 1e18, 10e18, true, false);

        vm.prank(consumer);
        vm.expectRevert("Service inactive");
        marketplace.purchaseService(0);
    }

    function testFuzz_PurchaseServiceRejectsZeroPrice() public {
        vm.prank(provider);
        marketplace.registerService("ipfs://test", 0, 10e18, true);

        vm.prank(consumer);
        vm.expectRevert("Not available for single use");
        marketplace.purchaseService(0);
    }

    function testFuzz_SubscribeToService(uint256 subPrice) public {
        subPrice = bound(subPrice, 1, 50_000 * 10**18);

        vm.prank(provider);
        uint256 serviceId = marketplace.registerService("ipfs://test", 1e18, subPrice, true);

        uint256 providerBefore = token.balanceOf(provider);
        vm.startPrank(consumer);
        token.approve(address(marketplace), subPrice);
        uint256 subId = marketplace.subscribeToService(serviceId);
        vm.stopPrank();

        uint256 fee = (subPrice * 250) / 10000;
        assertEq(token.balanceOf(provider), providerBefore + subPrice - fee);

        (, , address subscriber, uint256 expiry, bool isActive) = marketplace.subscriptions(subId);
        assertEq(subscriber, consumer);
        assertEq(expiry, block.timestamp + 30 days);
        assertTrue(isActive);
        assertTrue(marketplace.checkSubscription(subId));
    }

    function testFuzz_SubscribeRejectsUnavailable() public {
        vm.prank(provider);
        marketplace.registerService("ipfs://test", 1e18, 10e18, false);

        vm.prank(consumer);
        vm.expectRevert("Subscriptions not enabled");
        marketplace.subscribeToService(0);
    }

    function testFuzz_CheckSubscriptionExpiry() public {
        vm.prank(provider);
        marketplace.registerService("ipfs://test", 1e18, 10e18, true);

        vm.startPrank(consumer);
        token.approve(address(marketplace), 10e18);
        uint256 subId = marketplace.subscribeToService(0);
        vm.stopPrank();

        vm.warp(block.timestamp + 31 days);
        assertFalse(marketplace.checkSubscription(subId));
    }

    function testFuzz_UpdateServiceReputationOnlyOwner(address caller, uint256 score) public {
        vm.assume(caller != owner);

        vm.prank(provider);
        marketplace.registerService("ipfs://test", 1e18, 10e18, true);

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        marketplace.updateServiceReputation(0, score);
    }

    function testFuzz_UpdatePlatformFee(uint256 newFee) public {
        newFee = bound(newFee, 0, 1000);

        marketplace.updatePlatformFee(newFee);
        assertEq(marketplace.platformFeePercentage(), newFee);
    }

    function testFuzz_UpdatePlatformFeeRejectsHigh(uint256 newFee) public {
        vm.assume(newFee > 1000);

        vm.expectRevert("Fee too high");
        marketplace.updatePlatformFee(newFee);
    }

    function testFuzz_WithdrawPlatformFees(uint256 price) public {
        price = bound(price, 40, 50_000 * 10**18); // fee rounds to 0 below 40

        vm.prank(provider);
        marketplace.registerService("ipfs://test", price, 10e18, true);

        vm.startPrank(consumer);
        token.approve(address(marketplace), price);
        marketplace.purchaseService(0);
        vm.stopPrank();

        uint256 before = token.balanceOf(owner);
        marketplace.withdrawPlatformFees();
        assertEq(token.balanceOf(owner), before + (price * 250) / 10000);
    }

    function testFuzz_PauseBlocksWrites() public {
        marketplace.pause();

        vm.prank(provider);
        vm.expectRevert("Pausable: paused");
        marketplace.registerService("ipfs://test", 1e18, 10e18, true);
        marketplace.unpause();
    }

    function testFuzz_ServiceExistsModifier(uint256 serviceId) public {
        vm.assume(serviceId >= marketplace.serviceCounter());

        vm.expectRevert("Service does not exist");
        marketplace.purchaseService(serviceId);
    }
}
