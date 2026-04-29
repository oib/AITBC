// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/contracts/AgentMarketplaceV2.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract AgentMarketplaceV2FuzzTest is Test {
    AgentMarketplaceV2 public marketplace;
    MockToken public token;
    address public owner;
    address public provider;
    address public consumer;
    address public arbiter;

    function setUp() public {
        owner = address(this);
        provider = address(0x1);
        consumer = address(0x2);
        arbiter = address(0x3);

        token = new MockToken();
        marketplace = new AgentMarketplaceV2(address(token));

        token.transfer(consumer, 100_000 * 10**18);
        vm.prank(consumer);
        token.approve(address(marketplace), type(uint256).max);
    }

    function testFuzz_ListCapability(string memory metadataURI, uint256 pricePerCall, uint256 subscriptionPrice, bool isSubscriptionEnabled) public {
        vm.assume(bytes(metadataURI).length > 0);
        vm.assume(bytes(metadataURI).length <= 500);
        vm.assume(pricePerCall > 0);
        vm.assume(pricePerCall <= 10_000 * 10**18);
        vm.assume(subscriptionPrice > 0);
        vm.assume(subscriptionPrice <= 100_000 * 10**18);

        vm.prank(provider);
        uint256 capabilityId = marketplace.listCapability(metadataURI, pricePerCall, subscriptionPrice, isSubscriptionEnabled);

        (address providerAgent, string memory storedURI, uint256 storedPricePerCall, uint256 storedSubscriptionPrice, bool storedIsSubscriptionEnabled, bool isActive, , , , ) = marketplace.capabilities(capabilityId);
        
        assertEq(providerAgent, provider);
        assertEq(storedURI, metadataURI);
        assertEq(storedPricePerCall, pricePerCall);
        assertEq(storedSubscriptionPrice, subscriptionPrice);
        assertEq(storedIsSubscriptionEnabled, isSubscriptionEnabled);
        assertTrue(isActive);
    }

    function testFuzz_RevertIfEmptyURI(uint256 pricePerCall, uint256 subscriptionPrice) public {
        vm.assume(pricePerCall > 0);
        vm.assume(subscriptionPrice > 0);

        vm.prank(provider);
        vm.expectRevert("Invalid URI");
        marketplace.listCapability("", pricePerCall, subscriptionPrice, true);
    }

    function testFuzz_UpdateCapability(uint256 capabilityId, uint256 newPricePerCall, uint256 newSubscriptionPrice, bool newIsSubscriptionEnabled, bool newIsActive) public {
        vm.assume(newPricePerCall > 0);
        vm.assume(newPricePerCall <= 10_000 * 10**18);
        vm.assume(newSubscriptionPrice > 0);
        vm.assume(newSubscriptionPrice <= 100_000 * 10**18);

        vm.prank(provider);
        uint256 id = marketplace.listCapability("ipfs://test", 1e18, 10e18, true);

        vm.prank(provider);
        marketplace.updateCapability(id, newPricePerCall, newSubscriptionPrice, newIsSubscriptionEnabled, newIsActive);

        (, , uint256 storedPricePerCall, uint256 storedSubscriptionPrice, bool storedIsSubscriptionEnabled, bool storedIsActive, , , , ) = marketplace.capabilities(id);
        
        assertEq(storedPricePerCall, newPricePerCall);
        assertEq(storedSubscriptionPrice, newSubscriptionPrice);
        assertEq(storedIsSubscriptionEnabled, newIsSubscriptionEnabled);
        assertEq(storedIsActive, newIsActive);
    }

    function testFuzz_RevertIfNotProviderUpdatesCapability(uint256 capabilityId, uint256 newPricePerCall) public {
        vm.assume(newPricePerCall > 0);

        vm.prank(provider);
        uint256 id = marketplace.listCapability("ipfs://test", 1e18, 10e18, true);

        vm.prank(consumer);
        vm.expectRevert("Not the provider");
        marketplace.updateCapability(id, newPricePerCall, 10e18, true, true);
    }

    function testFuzz_PurchaseCall(uint256 pricePerCall, uint256 subscriptionPrice) public {
        vm.assume(pricePerCall > 0);
        vm.assume(pricePerCall <= 10_000 * 10**18);
        vm.assume(subscriptionPrice > 0);
        vm.assume(subscriptionPrice <= 100_000 * 10**18);

        vm.prank(provider);
        uint256 capabilityId = marketplace.listCapability("ipfs://test", pricePerCall, subscriptionPrice, true);

        uint256 providerBalance = token.balanceOf(provider);

        vm.prank(consumer);
        marketplace.purchaseCall(capabilityId);

        uint256 newProviderBalance = token.balanceOf(provider);
        assertTrue(newProviderBalance > providerBalance);
    }

    function testFuzz_RevertIfCapabilityInactive(uint256 pricePerCall, uint256 subscriptionPrice) public {
        vm.assume(pricePerCall > 0);
        vm.assume(subscriptionPrice > 0);

        vm.prank(provider);
        uint256 capabilityId = marketplace.listCapability("ipfs://test", pricePerCall, subscriptionPrice, true);

        vm.prank(provider);
        marketplace.updateCapability(capabilityId, pricePerCall, subscriptionPrice, true, false);

        vm.prank(consumer);
        vm.expectRevert("Capability inactive");
        marketplace.purchaseCall(capabilityId);
    }

    function testFuzz_SubscribeToCapability(uint256 pricePerCall, uint256 subscriptionPrice) public {
        vm.assume(pricePerCall > 0);
        vm.assume(subscriptionPrice > 0);
        vm.assume(subscriptionPrice <= 100_000 * 10**18);

        vm.prank(provider);
        uint256 capabilityId = marketplace.listCapability("ipfs://test", pricePerCall, subscriptionPrice, true);

        uint256 providerBalance = token.balanceOf(provider);

        vm.prank(consumer);
        uint256 subscriptionId = marketplace.subscribeToCapability(capabilityId);

        uint256 newProviderBalance = token.balanceOf(provider);
        assertTrue(newProviderBalance > providerBalance);
        assertTrue(subscriptionId > 0);
    }

    function testFuzz_RevertIfSubscriptionsNotEnabled(uint256 pricePerCall, uint256 subscriptionPrice) public {
        vm.assume(pricePerCall > 0);
        vm.assume(subscriptionPrice > 0);

        vm.prank(provider);
        uint256 capabilityId = marketplace.listCapability("ipfs://test", pricePerCall, subscriptionPrice, false);

        vm.prank(consumer);
        vm.expectRevert("Subscriptions not enabled");
        marketplace.subscribeToCapability(capabilityId);
    }

    function testFuzz_UpdatePlatformFee(uint256 newFee) public {
        vm.assume(newFee > 0);
        vm.assume(newFee <= 1000); // Max 10%

        vm.prank(owner);
        marketplace.updatePlatformFee(newFee);

        assertEq(marketplace.platformFeePercentage(), newFee);
    }

    function testFuzz_RevertIfFeeTooHigh(uint256 newFee) public {
        vm.assume(newFee > 1000);

        vm.prank(owner);
        vm.expectRevert("Fee too high");
        marketplace.updatePlatformFee(newFee);
    }

    function testFuzz_UpdateCapabilityReputation(uint256 capabilityId, uint256 newScore) public {
        vm.assume(newScore <= 100);

        vm.prank(provider);
        uint256 id = marketplace.listCapability("ipfs://test", 1e18, 10e18, true);

        vm.prank(owner);
        marketplace.updateCapabilityReputation(id, newScore);

        (, , , , , , , , uint256 reputationScore, ) = marketplace.capabilities(id);
        assertEq(reputationScore, newScore);
    }

    function testFuzz_WithdrawPlatformFunds(uint256 amount) public {
        vm.assume(amount > 0);
        vm.assume(amount <= 10_000 * 10**18);

        vm.prank(provider);
        uint256 capabilityId = marketplace.listCapability("ipfs://test", amount, amount * 10, true);

        vm.prank(consumer);
        marketplace.purchaseCall(capabilityId);

        uint256 ownerBalance = token.balanceOf(owner);

        vm.prank(owner);
        marketplace.withdrawPlatformFees();

        uint256 newOwnerBalance = token.balanceOf(owner);
        assertTrue(newOwnerBalance >= ownerBalance);
    }

    function testFuzz_CheckSubscription(uint256 pricePerCall, uint256 subscriptionPrice) public {
        vm.assume(pricePerCall > 0);
        vm.assume(subscriptionPrice > 0);

        vm.prank(provider);
        uint256 capabilityId = marketplace.listCapability("ipfs://test", pricePerCall, subscriptionPrice, true);

        vm.prank(consumer);
        uint256 subscriptionId = marketplace.subscribeToCapability(capabilityId);

        bool isValid = marketplace.checkSubscription(subscriptionId);
        assertTrue(isValid);
    }

    function testFuzz_GetProviderCapabilities(uint256 numCapabilities) public {
        vm.assume(numCapabilities > 0);
        vm.assume(numCapabilities <= 20);

        for (uint256 i = 0; i < numCapabilities; i++) {
            vm.prank(provider);
            marketplace.listCapability(string(abi.encodePacked("ipfs://", i)), 1e18, 10e18, true);
        }

        uint256[] memory capabilities = marketplace.providerCapabilities(provider);
        assertEq(capabilities.length, numCapabilities);
    }

    function testFuzz_GetSubscriberSubscriptions(uint256 numSubscriptions) public {
        vm.assume(numSubscriptions > 0);
        vm.assume(numSubscriptions <= 10);

        for (uint256 i = 0; i < numSubscriptions; i++) {
            vm.prank(provider);
            uint256 capabilityId = marketplace.listCapability(string(abi.encodePacked("ipfs://", i)), 1e18, 10e18, true);
            
            vm.prank(consumer);
            marketplace.subscribeToCapability(capabilityId);
        }

        uint256[] memory subscriptions = marketplace.subscriberSubscriptions(consumer);
        assertEq(subscriptions.length, numSubscriptions);
    }

    function testFuzz_PauseUnpause() public {
        assertFalse(marketplace.paused());

        vm.prank(owner);
        marketplace.pause();
        assertTrue(marketplace.paused());

        vm.prank(owner);
        marketplace.unpause();
        assertFalse(marketplace.paused());
    }

    function testFuzz_RevertIfPaused(uint256 pricePerCall, uint256 subscriptionPrice) public {
        vm.assume(pricePerCall > 0);
        vm.assume(subscriptionPrice > 0);

        vm.prank(owner);
        marketplace.pause();

        vm.prank(provider);
        vm.expectRevert();
        marketplace.listCapability("ipfs://test", pricePerCall, subscriptionPrice, true);
    }
}
