// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";

/**
 * @title AgentServiceMarketplace
 * @dev Advanced marketplace for AI agents to discover, offer, and monetize their capabilities and services.
 */
contract AgentServiceMarketplace is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    IERC20 public aitbcToken;

    uint256 public serviceCounter;
    uint256 public subscriptionCounter;
    uint256 public platformFeePercentage = 250; // 2.5% in basis points (10000 = 100%)
    
    struct ServiceOffering {
        uint256 serviceId;
        address providerAgent;
        string capabilityURI;     // IPFS hash containing service metadata (inputs, outputs, SLA)
        uint256 pricePerUse;
        uint256 subscriptionPricePerMonth;
        bool isSubscriptionAvailable;
        bool isActive;
        uint256 totalUses;
        uint256 totalRevenue;
        uint256 reputationScore;  // Updated via cross-chain reputation or oracle
    }

    struct Subscription {
        uint256 subscriptionId;
        uint256 serviceId;
        address subscriberAgent;
        uint256 expiryTimestamp;
        bool isActive;
    }

    mapping(uint256 => ServiceOffering) public services;
    mapping(uint256 => Subscription) public subscriptions;
    mapping(address => uint256[]) public providerServices;
    mapping(address => uint256[]) public subscriberSubscriptions;

    // Events
    event ServiceRegistered(uint256 indexed serviceId, address indexed provider, string capabilityURI, uint256 pricePerUse);
    event ServiceUpdated(uint256 indexed serviceId, uint256 pricePerUse, bool isActive);
    event ServicePurchased(uint256 indexed serviceId, address indexed buyer, uint256 pricePaid);
    event SubscriptionCreated(uint256 indexed subscriptionId, uint256 indexed serviceId, address indexed subscriber, uint256 expiryTimestamp);
    event SubscriptionRenewed(uint256 indexed subscriptionId, uint256 newExpiryTimestamp);
    event PlatformFeeUpdated(uint256 newFeePercentage);
    event ServiceReputationUpdated(uint256 indexed serviceId, uint256 newScore);

    modifier serviceExists(uint256 _serviceId) {
        require(_serviceId < serviceCounter, "Service does not exist");
        _;
    }

    constructor(address _aitbcToken) {
        require(_aitbcToken != address(0), "Invalid token address");
        aitbcToken = IERC20(_aitbcToken);
    }

    /**
     * @dev Register a new agent capability/service
     * @param _capabilityURI IPFS hash for service metadata
     * @param _pricePerUse Price to pay per individual API/capability call
     * @param _subscriptionPricePerMonth Price for unlimited/tiered monthly access
     * @param _isSubscriptionAvailable Boolean flag enabling subscriptions
     */
    function registerService(
        string calldata _capabilityURI,
        uint256 _pricePerUse,
        uint256 _subscriptionPricePerMonth,
        bool _isSubscriptionAvailable
    ) external whenNotPaused returns (uint256) {
        require(bytes(_capabilityURI).length > 0, "Invalid URI");

        uint256 serviceId = serviceCounter++;

        services[serviceId] = ServiceOffering({
            serviceId: serviceId,
            providerAgent: msg.sender,
            capabilityURI: _capabilityURI,
            pricePerUse: _pricePerUse,
            subscriptionPricePerMonth: _subscriptionPricePerMonth,
            isSubscriptionAvailable: _isSubscriptionAvailable,
            isActive: true,
            totalUses: 0,
            totalRevenue: 0,
            reputationScore: 0
        });

        providerServices[msg.sender].push(serviceId);

        emit ServiceRegistered(serviceId, msg.sender, _capabilityURI, _pricePerUse);
        return serviceId;
    }

    /**
     * @dev Update an existing service offering
     */
    function updateService(
        uint256 _serviceId,
        uint256 _pricePerUse,
        uint256 _subscriptionPricePerMonth,
        bool _isSubscriptionAvailable,
        bool _isActive
    ) external serviceExists(_serviceId) {
        ServiceOffering storage service = services[_serviceId];
        require(service.providerAgent == msg.sender, "Not service provider");

        service.pricePerUse = _pricePerUse;
        service.subscriptionPricePerMonth = _subscriptionPricePerMonth;
        service.isSubscriptionAvailable = _isSubscriptionAvailable;
        service.isActive = _isActive;

        emit ServiceUpdated(_serviceId, _pricePerUse, _isActive);
    }

    /**
     * @dev Purchase a single use of an agent service
     */
    function purchaseService(uint256 _serviceId) external nonReentrant whenNotPaused serviceExists(_serviceId) {
        ServiceOffering storage service = services[_serviceId];
        require(service.isActive, "Service inactive");
        require(service.pricePerUse > 0, "Not available for single use");

        uint256 platformFee = (service.pricePerUse * platformFeePercentage) / 10000;
        uint256 providerAmount = service.pricePerUse - platformFee;

        // Transfer funds
        aitbcToken.safeTransferFrom(msg.sender, address(this), service.pricePerUse);
        
        // Pay provider
        if (providerAmount > 0) {
            aitbcToken.safeTransfer(service.providerAgent, providerAmount);
        }
        
        // Retain platform fee in contract (owner can withdraw)

        service.totalUses += 1;
        service.totalRevenue += providerAmount;

        emit ServicePurchased(_serviceId, msg.sender, service.pricePerUse);
    }

    /**
     * @dev Subscribe to an agent service for 30 days
     */
    function subscribeToService(uint256 _serviceId) external nonReentrant whenNotPaused serviceExists(_serviceId) returns (uint256) {
        ServiceOffering storage service = services[_serviceId];
        require(service.isActive, "Service inactive");
        require(service.isSubscriptionAvailable, "Subscriptions not enabled");

        uint256 platformFee = (service.subscriptionPricePerMonth * platformFeePercentage) / 10000;
        uint256 providerAmount = service.subscriptionPricePerMonth - platformFee;

        // Transfer funds
        aitbcToken.safeTransferFrom(msg.sender, address(this), service.subscriptionPricePerMonth);
        
        // Pay provider
        if (providerAmount > 0) {
            aitbcToken.safeTransfer(service.providerAgent, providerAmount);
        }

        service.totalRevenue += providerAmount;

        uint256 subId = subscriptionCounter++;
        uint256 expiry = block.timestamp + 30 days;

        subscriptions[subId] = Subscription({
            subscriptionId: subId,
            serviceId: _serviceId,
            subscriberAgent: msg.sender,
            expiryTimestamp: expiry,
            isActive: true
        });

        subscriberSubscriptions[msg.sender].push(subId);

        emit SubscriptionCreated(subId, _serviceId, msg.sender, expiry);
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
     * @dev Update the reputation score of a service (Oracle/Owner only)
     */
    function updateServiceReputation(uint256 _serviceId, uint256 _newScore) external onlyOwner serviceExists(_serviceId) {
        services[_serviceId].reputationScore = _newScore;
        emit ServiceReputationUpdated(_serviceId, _newScore);
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
