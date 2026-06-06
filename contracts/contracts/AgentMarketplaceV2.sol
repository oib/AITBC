// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";

/**
 * @title AgentMarketplaceV2
 * @dev Advanced marketplace with capability trading and subscriptions for AI agents.
 */
contract AgentMarketplaceV2 is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    IERC20 public aitbcToken;

    uint256 public capabilityCounter;
    uint256 public subscriptionCounter;
    uint256 public platformFeePercentage = 250; // 2.5% in basis points (10000 = 100%)
    
    struct Capability {
        uint256 capabilityId;
        address providerAgent;
        string metadataURI;       // IPFS hash containing capability description, API spec, and SLA
        uint256 pricePerCall;     // Price for a single capability use
        uint256 subscriptionPrice; // Price for a 30-day subscription
        bool isSubscriptionEnabled;
        bool isActive;
        uint256 totalCalls;
        uint256 totalRevenue;
        uint256 reputationScore;  // Automatically updated score based on verifications
    }

    struct Subscription {
        uint256 subscriptionId;
        uint256 capabilityId;
        address subscriberAgent;
        uint256 expiryTimestamp;
        bool isActive;
    }

    mapping(uint256 => Capability) public capabilities;
    mapping(uint256 => Subscription) public subscriptions;
    mapping(address => uint256[]) public providerCapabilities;
    mapping(address => uint256[]) public subscriberSubscriptions;

    // Events
    event CapabilityListed(uint256 indexed capabilityId, address indexed provider, string metadataURI, uint256 pricePerCall, uint256 subscriptionPrice);
    event CapabilityUpdated(uint256 indexed capabilityId, uint256 pricePerCall, uint256 subscriptionPrice, bool isActive);
    event CapabilityPurchased(uint256 indexed capabilityId, address indexed buyer, uint256 pricePaid);
    event SubscriptionCreated(uint256 indexed subscriptionId, uint256 indexed capabilityId, address indexed subscriber, uint256 expiryTimestamp);
    event PlatformFeeUpdated(uint256 newFeePercentage);
    event CapabilityReputationUpdated(uint256 indexed capabilityId, uint256 newScore);

    modifier capabilityExists(uint256 _capabilityId) {
        require(_capabilityId < capabilityCounter, "Capability does not exist");
        _;
    }

    constructor(address _aitbcToken) {
        require(_aitbcToken != address(0), "Invalid token address");
        aitbcToken = IERC20(_aitbcToken);
    }

    /**
     * @dev List a new agent capability on the marketplace
     */
    function listCapability(
        string calldata _metadataURI,
        uint256 _pricePerCall,
        uint256 _subscriptionPrice,
        bool _isSubscriptionEnabled
    ) external whenNotPaused returns (uint256) {
        require(bytes(_metadataURI).length > 0, "Invalid URI");

        uint256 capabilityId = capabilityCounter++;

        capabilities[capabilityId] = Capability({
            capabilityId: capabilityId,
            providerAgent: msg.sender,
            metadataURI: _metadataURI,
            pricePerCall: _pricePerCall,
            subscriptionPrice: _subscriptionPrice,
            isSubscriptionEnabled: _isSubscriptionEnabled,
            isActive: true,
            totalCalls: 0,
            totalRevenue: 0,
            reputationScore: 0
        });

        providerCapabilities[msg.sender].push(capabilityId);

        emit CapabilityListed(capabilityId, msg.sender, _metadataURI, _pricePerCall, _subscriptionPrice);
        return capabilityId;
    }

    /**
     * @dev Update an existing capability
     */
    function updateCapability(
        uint256 _capabilityId,
        uint256 _pricePerCall,
        uint256 _subscriptionPrice,
        bool _isSubscriptionEnabled,
        bool _isActive
    ) external capabilityExists(_capabilityId) {
        Capability storage cap = capabilities[_capabilityId];
        require(cap.providerAgent == msg.sender, "Not the provider");

        cap.pricePerCall = _pricePerCall;
        cap.subscriptionPrice = _subscriptionPrice;
        cap.isSubscriptionEnabled = _isSubscriptionEnabled;
        cap.isActive = _isActive;

        emit CapabilityUpdated(_capabilityId, _pricePerCall, _subscriptionPrice, _isActive);
    }

    /**
     * @dev Purchase a single call of a capability
     */
    function purchaseCall(uint256 _capabilityId) external nonReentrant whenNotPaused capabilityExists(_capabilityId) {
        Capability storage cap = capabilities[_capabilityId];
        require(cap.isActive, "Capability inactive");
        require(cap.pricePerCall > 0, "Not available for single call");

        uint256 platformFee = (cap.pricePerCall * platformFeePercentage) / 10000;
        uint256 providerAmount = cap.pricePerCall - platformFee;

        // Transfer funds
        aitbcToken.safeTransferFrom(msg.sender, address(this), cap.pricePerCall);
        
        // Pay provider
        if (providerAmount > 0) {
            aitbcToken.safeTransfer(cap.providerAgent, providerAmount);
        }

        cap.totalCalls += 1;
        cap.totalRevenue += providerAmount;

        emit CapabilityPurchased(_capabilityId, msg.sender, cap.pricePerCall);
    }

    /**
     * @dev Subscribe to an agent capability for 30 days
     */
    function subscribeToCapability(uint256 _capabilityId) external nonReentrant whenNotPaused capabilityExists(_capabilityId) returns (uint256) {
        Capability storage cap = capabilities[_capabilityId];
        require(cap.isActive, "Capability inactive");
        require(cap.isSubscriptionEnabled, "Subscriptions not enabled");

        uint256 platformFee = (cap.subscriptionPrice * platformFeePercentage) / 10000;
        uint256 providerAmount = cap.subscriptionPrice - platformFee;

        // Transfer funds
        aitbcToken.safeTransferFrom(msg.sender, address(this), cap.subscriptionPrice);
        
        // Pay provider
        if (providerAmount > 0) {
            aitbcToken.safeTransfer(cap.providerAgent, providerAmount);
        }

        cap.totalRevenue += providerAmount;

        uint256 subId = subscriptionCounter++;
        uint256 expiry = block.timestamp + 30 days;

        subscriptions[subId] = Subscription({
            subscriptionId: subId,
            capabilityId: _capabilityId,
            subscriberAgent: msg.sender,
            expiryTimestamp: expiry,
            isActive: true
        });

        subscriberSubscriptions[msg.sender].push(subId);

        emit SubscriptionCreated(subId, _capabilityId, msg.sender, expiry);
        return subId;
    }

    /**
     * @dev Check if a subscription is still active and valid
     */
    function checkSubscription(uint256 _subscriptionId) external view returns (bool) {
        Subscription memory sub = subscriptions[_subscriptionId];
        return sub.isActive && (block.timestamp < sub.expiryTimestamp);
    }

    /**
     * @dev Update the reputation score of a capability (Oracle/Owner only)
     */
    function updateCapabilityReputation(uint256 _capabilityId, uint256 _newScore) external onlyOwner capabilityExists(_capabilityId) {
        capabilities[_capabilityId].reputationScore = _newScore;
        emit CapabilityReputationUpdated(_capabilityId, _newScore);
    }

    /**
     * @dev Update platform fee percentage
     */
    function updatePlatformFee(uint256 _newFee) external onlyOwner {
        require(_newFee <= 1000, "Fee too high"); // Max 10%
        platformFeePercentage = _newFee;
        emit PlatformFeeUpdated(_newFee);
    }

    /**
     * @dev Withdraw accumulated platform fees
     */
    function withdrawPlatformFees() external onlyOwner {
        uint256 balance = aitbcToken.balanceOf(address(this));
        require(balance > 0, "No fees to withdraw");
        aitbcToken.safeTransfer(owner(), balance);
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
