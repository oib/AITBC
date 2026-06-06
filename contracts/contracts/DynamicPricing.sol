// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./AIPowerRental.sol";
import "./PerformanceVerifier.sol";

/**
 * @title Dynamic Pricing
 * @dev Advanced dynamic pricing contract with supply/demand analysis and automated price adjustment
 * @notice Implements data-driven pricing for AI power marketplace with ZK-based verification
 */
contract DynamicPricing is Ownable, ReentrancyGuard, Pausable {
    
    // State variables
    AIPowerRental public aiPowerRental;
    PerformanceVerifier public performanceVerifier;
    IERC20 public aitbcToken;
    
    uint256 public priceUpdateCounter;
    uint256 public basePricePerHour = 1e16; // 0.01 AITBC per hour
    uint256 public minPricePerHour = 1e15; // 0.001 AITBC minimum
    uint256 public maxPricePerHour = 1e18; // 0.1 AITBC maximum
    uint256 public priceVolatilityThreshold = 2000; // 20% in basis points
    uint256 public priceUpdateInterval = 3600; // 1 hour
    uint256 public marketDataRetentionPeriod = 7 days;
    uint256 public smoothingFactor = 50; // 50% smoothing in basis points
    uint256 public surgeMultiplier = 300; // 3x surge pricing max
    uint256 public discountMultiplier = 50; // 50% minimum price
    
    // Structs
    struct MarketData {
        uint256 totalSupply;
        uint256 totalDemand;
        uint256 activeProviders;
        uint256 activeConsumers;
        uint256 averagePrice;
        uint256 priceVolatility;
        uint256 utilizationRate;
        uint256 lastUpdateTime;
        uint256 totalVolume;
        uint256 transactionCount;
        uint256 averageResponseTime;
        uint256 averageAccuracy;
        uint256 marketSentiment;
        bool isMarketActive;
    }
    
    struct PriceHistory {
        uint256 timestamp;
        uint256 price;
        uint256 supply;
        uint256 demand;
        uint256 volume;
        PriceChangeType changeType;
        uint256 changePercentage;
    }
    
    struct ProviderPricing {
        address provider;
        uint256 currentPrice;
        uint256 basePrice;
        uint256 reputationScore;
        uint256 utilizationRate;
        uint256 performanceScore;
        uint256 demandScore;
        uint256 supplyScore;
        uint256 lastUpdateTime;
        PricingStrategy strategy;
        uint256 priceAdjustmentFactor;
    }
    
    struct RegionalPricing {
        string region;
        uint256 regionalMultiplier;
        uint256 localSupply;
        uint256 localDemand;
        uint256 averagePrice;
        uint256 lastUpdateTime;
        uint256 competitionLevel;
        uint256 infrastructureCost;
    }
    
    struct DemandForecast {
        uint256 forecastPeriod;
        uint256 predictedDemand;
        uint256 confidence;
        uint256 forecastTime;
        uint256 actualDemand;
        uint256 forecastAccuracy;
    }
    
    struct PriceAlert {
        uint256 alertId;
        address subscriber;
        PriceAlertType alertType;
        uint256 thresholdPrice;
        uint256 currentPrice;
        bool isActive;
        uint256 lastTriggered;
        string notificationMethod;
    }
    
    // Enums
    enum PriceChangeType {
        Increase,
        Decrease,
        Stable,
        Surge,
        Discount
    }
    
    enum PricingStrategy {
        Fixed,
        Dynamic,
        Competitive,
        PerformanceBased,
        TimeBased,
        DemandBased
    }
    
    enum MarketCondition {
        Oversupply,
        Balanced,
        Undersupply,
        Surge,
        Crash
    }
    
    enum PriceAlertType {
        PriceAbove,
        PriceBelow,
        VolatilityHigh,
        TrendChange
    }
    
    // Mappings
    mapping(uint256 => MarketData) public marketDataHistory;
    mapping(uint256 => PriceHistory[]) public priceHistory;
    mapping(address => ProviderPricing) public providerPricing;
    mapping(string => RegionalPricing) public regionalPricing;
    mapping(uint256 => DemandForecast) public demandForecasts;
    mapping(uint256 => PriceAlert) public priceAlerts;
    mapping(address => uint256[]) public providerPriceHistory;
    mapping(string => uint256[]) public regionalPriceHistory;
    mapping(address => bool) public authorizedPriceOracles;
    mapping(uint256 => bool) public isValidPriceUpdate;
    
    // Arrays for tracking
    string[] public supportedRegions;
    uint256[] public activePriceAlerts;
    uint256[] public recentPriceUpdates;
    
    // Events
    event MarketDataUpdated(
        uint256 indexed timestamp,
        uint256 totalSupply,
        uint256 totalDemand,
        uint256 averagePrice,
        MarketCondition marketCondition
    );
    
    event PriceCalculated(
        uint256 indexed timestamp,
        uint256 newPrice,
        uint256 oldPrice,
        PriceChangeType changeType,
        uint256 changePercentage
    );
    
    event ProviderPriceUpdated(
        address indexed provider,
        uint256 newPrice,
        PricingStrategy strategy,
        uint256 adjustmentFactor
    );
    
    event RegionalPriceUpdated(
        string indexed region,
        uint256 newMultiplier,
        uint256 localSupply,
        uint256 localDemand
    );
    
    event DemandForecastCreated(
        uint256 indexed forecastPeriod,
        uint256 predictedDemand,
        uint256 confidence,
        uint256 forecastTime
    );
    
    event PriceAlertTriggered(
        uint256 indexed alertId,
        address indexed subscriber,
        PriceAlertType alertType,
        uint256 currentPrice,
        uint256 thresholdPrice
    );
    
    event SurgePricingActivated(
        uint256 surgeMultiplier,
        uint256 duration,
        string reason
    );
    
    event DiscountPricingActivated(
        uint256 discountMultiplier,
        uint256 duration,
        string reason
    );
    
    event MarketConditionChanged(
        MarketCondition oldCondition,
        MarketCondition newCondition,
        uint256 timestamp
    );
    
    event PriceOracleAuthorized(
        address indexed oracle,
        uint256 reputationScore
    );
    
    event PriceOracleRevoked(
        address indexed oracle,
        string reason
    );
    
    // Modifiers
    modifier onlyAuthorizedPriceOracle() {
        require(authorizedPriceOracles[msg.sender], "Not authorized price oracle");
        _;
    }
    
    modifier validPriceUpdate(uint256 _timestamp) {
        require(block.timestamp - _timestamp <= priceUpdateInterval, "Price update too old");
        _;
    }
    
    modifier validProvider(address _provider) {
        require(_provider != address(0), "Invalid provider address");
        _;
    }
    
    modifier validRegion(string memory _region) {
        require(bytes(_region).length > 0, "Invalid region");
        _;
    }
    
    // Constructor
    constructor(
        address _aiPowerRental,
        address _performanceVerifier,
        address _aitbcToken
    ) {
        aiPowerRental = AIPowerRental(_aiPowerRental);
        performanceVerifier = PerformanceVerifier(_performanceVerifier);
        aitbcToken = IERC20(_aitbcToken);
        priceUpdateCounter = 0;
        
        // Initialize supported regions
        supportedRegions.push("us-east");
        supportedRegions.push("us-west");
        supportedRegions.push("eu-central");
        supportedRegions.push("eu-west");
        supportedRegions.push("ap-southeast");
        supportedRegions.push("ap-northeast");
    }
    
    /**
     * @dev Updates market data and recalculates prices
     * @param _totalSupply Total compute power supply
     * @param _totalDemand Total compute power demand
     * @param _activeProviders Number of active providers
     * @param _activeConsumers Number of active consumers
     * @param _totalVolume Total transaction volume
     * @param _transactionCount Number of transactions
     * @param _averageResponseTime Average response time
     * @param _averageAccuracy Average accuracy
     * @param _marketSentiment Market sentiment score (0-100)
     */
    function updateMarketData(
        uint256 _totalSupply,
        uint256 _totalDemand,
        uint256 _activeProviders,
        uint256 _activeConsumers,
        uint256 _totalVolume,
        uint256 _transactionCount,
        uint256 _averageResponseTime,
        uint256 _averageAccuracy,
        uint256 _marketSentiment
    ) external onlyAuthorizedPriceOracle nonReentrant whenNotPaused {
        require(_totalSupply > 0, "Invalid supply");
        require(_totalDemand > 0, "Invalid demand");
        
        uint256 timestamp = block.timestamp;
        uint256 priceUpdateId = priceUpdateCounter++;
        
        // Calculate utilization rate
        uint256 utilizationRate = (_totalDemand * 10000) / _totalSupply;
        
        // Get previous market data for comparison
        MarketData storage previousData = marketDataHistory[priceUpdateId > 0 ? priceUpdateId - 1 : 0];
        
        // Calculate new average price
        uint256 newAveragePrice = _calculateDynamicPrice(
            _totalSupply,
            _totalDemand,
            utilizationRate,
            _marketSentiment,
            previousData.averagePrice
        );
        
        // Calculate price volatility
        uint256 priceVolatility = 0;
        if (previousData.averagePrice > 0) {
            if (newAveragePrice > previousData.averagePrice) {
                priceVolatility = ((newAveragePrice - previousData.averagePrice) * 10000) / previousData.averagePrice;
            } else {
                priceVolatility = ((previousData.averagePrice - newAveragePrice) * 10000) / previousData.averagePrice;
            }
        }
        
        // Store market data
        marketDataHistory[priceUpdateId] = MarketData({
            totalSupply: _totalSupply,
            totalDemand: _totalDemand,
            activeProviders: _activeProviders,
            activeConsumers: _activeConsumers,
            averagePrice: newAveragePrice,
            priceVolatility: priceVolatility,
            utilizationRate: utilizationRate,
            lastUpdateTime: timestamp,
            totalVolume: _totalVolume,
            transactionCount: _transactionCount,
            averageResponseTime: _averageResponseTime,
            averageAccuracy: _averageAccuracy,
            marketSentiment: _marketSentiment,
            isMarketActive: _activeProviders > 0 && _activeConsumers > 0
        });
        
        // Determine market condition
        MarketCondition currentCondition = _determineMarketCondition(utilizationRate, priceVolatility);
        
        // Store price history
        PriceChangeType changeType = _determinePriceChangeType(previousData.averagePrice, newAveragePrice);
        uint256 changePercentage = previousData.averagePrice > 0 ? 
            ((newAveragePrice - previousData.averagePrice) * 10000) / previousData.averagePrice : 0;
        
        priceHistory[priceUpdateId].push(PriceHistory({
            timestamp: timestamp,
            price: newAveragePrice,
            supply: _totalSupply,
            demand: _totalDemand,
            volume: _totalVolume,
            changeType: changeType,
            changePercentage: changePercentage
        }));
        
        // Update provider prices
        _updateProviderPrices(newAveragePrice, utilizationRate);
        
        // Update regional prices
        _updateRegionalPrices(_totalSupply, _totalDemand);
        
        // Check price alerts
        _checkPriceAlerts(newAveragePrice);
        
        // Apply surge or discount pricing if needed
        _applySpecialPricing(currentCondition, priceVolatility);
        
        isValidPriceUpdate[priceUpdateId] = true;
        recentPriceUpdates.push(priceUpdateId);
        
        emit MarketDataUpdated(timestamp, _totalSupply, _totalDemand, newAveragePrice, currentCondition);
        emit PriceCalculated(timestamp, newAveragePrice, previousData.averagePrice, changeType, changePercentage);
    }
    
    /**
     * @dev Calculates dynamic price based on market conditions
     * @param _supply Total supply
     * @param _demand Total demand
     * @param _utilizationRate Utilization rate in basis points
     * @param _marketSentiment Market sentiment (0-100)
     * @param _previousPrice Previous average price
     */
    function _calculateDynamicPrice(
        uint256 _supply,
        uint256 _demand,
        uint256 _utilizationRate,
        uint256 _marketSentiment,
        uint256 _previousPrice
    ) internal view returns (uint256) {
        // Base price calculation
        uint256 newPrice = basePricePerHour;
        
        // Supply/demand adjustment
        if (_demand > _supply) {
            uint256 demandPremium = ((_demand - _supply) * 10000) / _supply;
            newPrice = (newPrice * (10000 + demandPremium)) / 10000;
        } else if (_supply > _demand) {
            uint256 supplyDiscount = ((_supply - _demand) * 10000) / _supply;
            newPrice = (newPrice * (10000 - supplyDiscount)) / 10000;
        }
        
        // Utilization rate adjustment
        if (_utilizationRate > 8000) { // > 80% utilization
            uint256 utilizationPremium = (_utilizationRate - 8000) / 2;
            newPrice = (newPrice * (10000 + utilizationPremium)) / 10000;
        } else if (_utilizationRate < 2000) { // < 20% utilization
            uint256 utilizationDiscount = (2000 - _utilizationRate) / 4;
            newPrice = (newPrice * (10000 - utilizationDiscount)) / 10000;
        }
        
        // Market sentiment adjustment
        if (_marketSentiment > 70) { // High sentiment
            newPrice = (newPrice * 10500) / 10000; // 5% premium
        } else if (_marketSentiment < 30) { // Low sentiment
            newPrice = (newPrice * 9500) / 10000; // 5% discount
        }
        
        // Smoothing with previous price
        if (_previousPrice > 0) {
            newPrice = (newPrice * (10000 - smoothingFactor) + _previousPrice * smoothingFactor) / 10000;
        }
        
        // Apply price bounds
        if (newPrice < minPricePerHour) {
            newPrice = minPricePerHour;
        } else if (newPrice > maxPricePerHour) {
            newPrice = maxPricePerHour;
        }
        
        return newPrice;
    }
    
    /**
     * @dev Updates provider-specific pricing
     * @param _marketAveragePrice Current market average price
     * @param _marketUtilizationRate Market utilization rate
     */
    function _updateProviderPrices(uint256 _marketAveragePrice, uint256 _marketUtilizationRate) internal {
        // This would typically iterate through all active providers
        // For now, we'll update based on provider performance and reputation
        
        // Implementation would include:
        // 1. Get provider performance metrics
        // 2. Calculate provider-specific adjustments
        // 3. Update provider pricing based on strategy
        // 4. Emit ProviderPriceUpdated events
    }
    
    /**
     * @dev Updates regional pricing
     * @param _totalSupply Total supply
     * @param _totalDemand Total demand
     */
    function _updateRegionalPrices(uint256 _totalSupply, uint256 _totalDemand) internal {
        for (uint256 i = 0; i < supportedRegions.length; i++) {
            string memory region = supportedRegions[i];
            RegionalPricing storage regional = regionalPricing[region];
            
            // Calculate regional supply/demand (simplified)
            uint256 regionalSupply = (_totalSupply * regionalPricing[region].localSupply) / 100;
            uint256 regionalDemand = (_totalDemand * regionalPricing[region].localDemand) / 100;
            
            // Calculate regional multiplier
            uint256 newMultiplier = 10000; // Base multiplier
            if (regionalDemand > regionalSupply) {
                newMultiplier = (newMultiplier * 11000) / 10000; // 10% premium
            } else if (regionalSupply > regionalDemand) {
                newMultiplier = (newMultiplier * 9500) / 10000; // 5% discount
            }
            
            regional.regionalMultiplier = newMultiplier;
            regional.lastUpdateTime = block.timestamp;
            
            emit RegionalPriceUpdated(region, newMultiplier, regionalSupply, regionalDemand);
        }
    }
    
    /**
     * @dev Determines market condition based on utilization and volatility
     * @param _utilizationRate Utilization rate in basis points
     * @param _priceVolatility Price volatility in basis points
     */
    function _determineMarketCondition(uint256 _utilizationRate, uint256 _priceVolatility) internal pure returns (MarketCondition) {
        if (_utilizationRate > 9000) {
            return MarketCondition.Surge;
        } else if (_utilizationRate > 7000) {
            return MarketCondition.Undersupply;
        } else if (_utilizationRate > 3000) {
            return MarketCondition.Balanced;
        } else if (_utilizationRate > 1000) {
            return MarketCondition.Oversupply;
        } else {
            return MarketCondition.Crash;
        }
    }
    
    /**
     * @dev Determines price change type
     * @param _oldPrice Previous price
     * @param _newPrice New price
     */
    function _determinePriceChangeType(uint256 _oldPrice, uint256 _newPrice) internal pure returns (PriceChangeType) {
        if (_oldPrice == 0) {
            return PriceChangeType.Stable;
        }
        
        uint256 changePercentage = 0;
        if (_newPrice > _oldPrice) {
            changePercentage = ((_newPrice - _oldPrice) * 10000) / _oldPrice;
        } else {
            changePercentage = ((_oldPrice - _newPrice) * 10000) / _oldPrice;
        }
        
        if (changePercentage < 500) { // < 5%
            return PriceChangeType.Stable;
        } else if (changePercentage > 2000) { // > 20%
            return _newPrice > _oldPrice ? PriceChangeType.Surge : PriceChangeType.Discount;
        } else {
            return _newPrice > _oldPrice ? PriceChangeType.Increase : PriceChangeType.Decrease;
        }
    }
    
    /**
     * @dev Applies special pricing based on market conditions
     * @param _condition Current market condition
     * @param _volatility Price volatility
     */
    function _applySpecialPricing(MarketCondition _condition, uint256 _volatility) internal {
        if (_condition == MarketCondition.Surge) {
            emit SurgePricingActivated(surgeMultiplier, 3600, "High demand detected");
        } else if (_condition == MarketCondition.Crash) {
            emit DiscountPricingActivated(discountMultiplier, 3600, "Low demand detected");
        }
    }
    
    /**
     * @dev Creates demand forecast
     * @param _forecastPeriod Period to forecast (in seconds)
     * @param _predictedDemand Predicted demand
     * @param _confidence Confidence level (0-100)
     */
    function createDemandForecast(
        uint256 _forecastPeriod,
        uint256 _predictedDemand,
        uint256 _confidence
    ) external onlyAuthorizedPriceOracle nonReentrant whenNotPaused {
        require(_forecastPeriod > 0, "Invalid forecast period");
        require(_predictedDemand > 0, "Invalid predicted demand");
        require(_confidence <= 100, "Invalid confidence");
        
        uint256 forecastId = priceUpdateCounter++;
        
        demandForecasts[forecastId] = DemandForecast({
            forecastPeriod: _forecastPeriod,
            predictedDemand: _predictedDemand,
            confidence: _confidence,
            forecastTime: block.timestamp,
            actualDemand: 0,
            forecastAccuracy: 0
        });
        
        emit DemandForecastCreated(_forecastPeriod, _predictedDemand, _confidence, block.timestamp);
    }
    
    /**
     * @dev Creates price alert
     * @param _subscriber Address to notify
     * @param _alertType Type of alert
     * @param _thresholdPrice Threshold price
     * @param _notificationMethod Notification method
     */
    function createPriceAlert(
        address _subscriber,
        PriceAlertType _alertType,
        uint256 _thresholdPrice,
        string memory _notificationMethod
    ) external nonReentrant whenNotPaused returns (uint256) {
        require(_subscriber != address(0), "Invalid subscriber");
        require(_thresholdPrice > 0, "Invalid threshold price");
        
        uint256 alertId = priceUpdateCounter++;
        
        priceAlerts[alertId] = PriceAlert({
            alertId: alertId,
            subscriber: _subscriber,
            alertType: _alertType,
            thresholdPrice: _thresholdPrice,
            currentPrice: 0,
            isActive: true,
            lastTriggered: 0,
            notificationMethod: _notificationMethod
        });
        
        activePriceAlerts.push(alertId);
        
        return alertId;
    }
    
    /**
     * @dev Gets current market price
     * @param _provider Provider address (optional, for provider-specific pricing)
     * @param _region Region (optional, for regional pricing)
     */
    function getMarketPrice(address _provider, string memory _region) 
        external 
        view 
        returns (uint256) 
    {
        uint256 basePrice = basePricePerHour;
        
        // Get latest market data
        if (priceUpdateCounter > 0) {
            basePrice = marketDataHistory[priceUpdateCounter - 1].averagePrice;
        }
        
        // Apply regional multiplier if specified
        if (bytes(_region).length > 0) {
            RegionalPricing storage regional = regionalPricing[_region];
            basePrice = (basePrice * regional.regionalMultiplier) / 10000;
        }
        
        // Apply provider-specific pricing if specified
        if (_provider != address(0)) {
            ProviderPricing storage provider = providerPricing[_provider];
            if (provider.currentPrice > 0) {
                basePrice = provider.currentPrice;
            }
        }
        
        return basePrice;
    }
    
    /**
     * @dev Gets market data
     * @param _timestamp Timestamp to get data for (0 for latest)
     */
    function getMarketData(uint256 _timestamp) 
        external 
        view 
        returns (MarketData memory) 
    {
        if (_timestamp == 0 && priceUpdateCounter > 0) {
            return marketDataHistory[priceUpdateCounter - 1];
        }
        
        // Find closest timestamp
        for (uint256 i = priceUpdateCounter; i > 0; i--) {
            if (marketDataHistory[i - 1].lastUpdateTime <= _timestamp) {
                return marketDataHistory[i - 1];
            }
        }
        
        revert("No market data found for timestamp");
    }
    
    /**
     * @dev Gets price history
     * @param _count Number of historical entries to return
     */
    function getPriceHistory(uint256 _count) 
        external 
        view 
        returns (PriceHistory[] memory) 
    {
        uint256 startIndex = priceUpdateCounter > _count ? priceUpdateCounter - _count : 0;
        uint256 length = priceUpdateCounter - startIndex;
        
        PriceHistory[] memory history = new PriceHistory[](length);
        
        for (uint256 i = 0; i < length; i++) {
            history[i] = priceHistory[startIndex + i][0];
        }
        
        return history;
    }
    
    /**
     * @dev Authorizes a price oracle
     * @param _oracle Address of the oracle
     */
    function authorizePriceOracle(address _oracle) external onlyOwner {
        require(_oracle != address(0), "Invalid oracle address");
        authorizedPriceOracles[_oracle] = true;
        emit PriceOracleAuthorized(_oracle, 0);
    }
    
    /**
     * @dev Revokes price oracle authorization
     * @param _oracle Address of the oracle
     */
    function revokePriceOracle(address _oracle) external onlyOwner {
        authorizedPriceOracles[_oracle] = false;
        emit PriceOracleRevoked(_oracle, "Authorization revoked");
    }
    
    /**
     * @dev Updates base pricing parameters
     * @param _basePrice New base price
     * @param _minPrice New minimum price
     * @param _maxPrice New maximum price
     */
    function updateBasePricing(
        uint256 _basePrice,
        uint256 _minPrice,
        uint256 _maxPrice
    ) external onlyOwner {
        require(_minPrice > 0 && _maxPrice > _minPrice, "Invalid price bounds");
        require(_basePrice >= _minPrice && _basePrice <= _maxPrice, "Base price out of bounds");
        
        basePricePerHour = _basePrice;
        minPricePerHour = _minPrice;
        maxPricePerHour = _maxPrice;
    }
    
    /**
     * @dev Emergency pause function
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @dev Unpause function
     */
    function unpause() external onlyOwner {
        _unpause();
    }
    
    // Internal function to check price alerts
    function _checkPriceAlerts(uint256 _currentPrice) internal {
        for (uint256 i = 0; i < activePriceAlerts.length; i++) {
            uint256 alertId = activePriceAlerts[i];
            PriceAlert storage alert = priceAlerts[alertId];
            
            if (!alert.isActive) continue;
            
            bool shouldTrigger = false;
            
            if (alert.alertType == PriceAlertType.PriceAbove && _currentPrice > alert.thresholdPrice) {
                shouldTrigger = true;
            } else if (alert.alertType == PriceAlertType.PriceBelow && _currentPrice < alert.thresholdPrice) {
                shouldTrigger = true;
            }
            
            if (shouldTrigger) {
                alert.lastTriggered = block.timestamp;
                emit PriceAlertTriggered(alertId, alert.subscriber, alert.alertType, _currentPrice, alert.thresholdPrice);
            }
        }
    }
}
