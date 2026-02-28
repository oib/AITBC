// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";

/**
 * @title AgentPortfolioManager
 * @dev Advanced portfolio management protocol for autonomous AI agents
 * @notice Enables agents to manage portfolios, execute trades, and automate rebalancing
 */
contract AgentPortfolioManager is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    using Math for uint256;

    // State variables
    IERC20 public aitbcToken;
    uint256 public portfolioCounter;
    uint256 public strategyCounter;
    uint256 public rebalanceThreshold = 500; // 5% threshold for rebalancing (in basis points)
    uint256 public maxRiskScore = 10000; // Maximum risk score (100% in basis points)
    uint256 public platformFeePercentage = 50; // 0.5% platform fee
    
    // Enums
    enum StrategyType { CONSERVATIVE, BALANCED, AGGRESSIVE, DYNAMIC }
    enum TradeStatus { PENDING, EXECUTED, FAILED, CANCELLED }
    enum RiskLevel { LOW, MEDIUM, HIGH, CRITICAL }

    // Structs
    struct Asset {
        address tokenAddress;
        string symbol;
        bool isActive;
        uint256 decimals;
        uint256 priceOracle; // Price in USD (scaled by 1e8)
    }

    struct AgentPortfolio {
        uint256 portfolioId;
        address agentAddress;
        mapping(string => uint256) assetBalances; // Token symbol -> balance (in wei)
        mapping(string => uint256) targetAllocations; // Token symbol -> target allocation (in basis points)
        uint256 totalValue; // Total portfolio value in USD (scaled by 1e8)
        uint256 riskScore; // Risk score (0-10000 basis points)
        uint256 lastRebalance;
        StrategyType strategy;
        bool isActive;
        uint256 created_at;
    }

    struct TradingStrategy {
        uint256 strategyId;
        string name;
        StrategyType strategyType;
        mapping(string => uint256) targetAllocations; // Token symbol -> target allocation
        uint256 maxDrawdown;
        uint256 rebalanceFrequency;
        bool isActive;
    }

    struct Trade {
        uint256 tradeId;
        uint256 portfolioId;
        string sellToken;
        string buyToken;
        uint256 sellAmount;
        uint256 buyAmount;
        uint256 price;
        TradeStatus status;
        uint256 timestamp;
        bytes32 executionHash;
    }

    struct RiskMetrics {
        uint256 volatility;
        uint256 maxDrawdown;
        uint256 sharpeRatio;
        uint256 beta;
        uint256 alpha;
        uint256 var95; // Value at Risk at 95% confidence
        RiskLevel riskLevel;
    }

    // Mappings
    mapping(uint256 => AgentPortfolio) public portfolios;
    mapping(address => uint256) public agentPortfolio;
    mapping(string => Asset) public supportedAssets;
    mapping(uint256 => TradingStrategy) public strategies;
    mapping(uint256 => Trade) public trades;
    mapping(uint256 => uint256[]) public portfolioTrades;
    mapping(uint256 => RiskMetrics) public portfolioRiskMetrics;

    // Arrays
    address[] public supportedAssetAddresses;
    string[] public supportedAssetSymbols;
    uint256[] public activePortfolioIds;

    // Events
    event PortfolioCreated(uint256 indexed portfolioId, address indexed agent, StrategyType strategy);
    event PortfolioRebalanced(uint256 indexed portfolioId, uint256 totalValue, uint256 riskScore);
    event TradeExecuted(uint256 indexed tradeId, uint256 indexed portfolioId, string sellToken, string buyToken, uint256 amount);
    event StrategyCreated(uint256 indexed strategyId, string name, StrategyType strategyType);
    event RiskAssessment(uint256 indexed portfolioId, uint256 riskScore, RiskLevel riskLevel);
    event AssetAdded(address indexed tokenAddress, string symbol, uint256 price);

    // Modifiers
    modifier onlyPortfolioOwner(uint256 portfolioId) {
        require(portfolios[portfolioId].agentAddress == msg.sender, "Not portfolio owner");
        _;
    }

    modifier validAsset(string memory symbol) {
        require(supportedAssets[symbol].isActive, "Asset not supported");
        _;
    }

    modifier validPortfolio(uint256 portfolioId) {
        require(portfolioId > 0 && portfolioId <= portfolioCounter, "Invalid portfolio ID");
        require(portfolios[portfolioId].isActive, "Portfolio not active");
        _;
    }

    constructor(address _aitbcToken) {
        aitbcToken = IERC20(_aitbcToken);
        
        // Initialize with basic assets
        _addAsset(address(aitbcToken), "AITBC", 18, 100000000); // $1.00 USD
    }

    /**
     * @dev Creates a new portfolio for an agent
     * @param agentAddress The address of the agent
     * @param strategyId The strategy ID to use
     * @return portfolioId The ID of the created portfolio
     */
    function createPortfolio(address agentAddress, uint256 strategyId) 
        external 
        nonReentrant 
        whenNotPaused 
        returns (uint256) 
    {
        require(agentAddress != address(0), "Invalid agent address");
        require(strategies[strategyId].isActive, "Strategy not active");
        require(agentPortfolio[agentAddress] == 0, "Portfolio already exists");

        portfolioCounter++;
        uint256 portfolioId = portfolioCounter;

        AgentPortfolio storage portfolio = portfolios[portfolioId];
        portfolio.portfolioId = portfolioId;
        portfolio.agentAddress = agentAddress;
        portfolio.strategy = strategies[strategyId].strategyType;
        portfolio.lastRebalance = block.timestamp;
        portfolio.isActive = true;
        portfolio.created_at = block.timestamp;

        // Copy target allocations from strategy
        TradingStrategy storage strategy = strategies[strategyId];
        for (uint i = 0; i < supportedAssetSymbols.length; i++) {
            string memory symbol = supportedAssetSymbols[i];
            portfolio.targetAllocations[symbol] = strategy.targetAllocations[symbol];
        }

        agentPortfolio[agentAddress] = portfolioId;
        activePortfolioIds.push(portfolioId);

        emit PortfolioCreated(portfolioId, agentAddress, portfolio.strategy);
        return portfolioId;
    }

    /**
     * @dev Executes a trade within a portfolio
     * @param portfolioId The portfolio ID
     * @param sellToken The token symbol to sell
     * @param buyToken The token symbol to buy
     * @param sellAmount The amount to sell (in wei)
     * @param minBuyAmount The minimum amount to buy (slippage protection)
     * @return tradeId The ID of the executed trade
     */
    function executeTrade(
        uint256 portfolioId,
        string memory sellToken,
        string memory buyToken,
        uint256 sellAmount,
        uint256 minBuyAmount
    ) 
        external 
        nonReentrant 
        whenNotPaused
        validPortfolio(portfolioId)
        onlyPortfolioOwner(portfolioId)
        validAsset(sellToken)
        validAsset(buyToken)
        returns (uint256) 
    {
        require(sellAmount > 0, "Invalid sell amount");
        require(portfolios[portfolioId].assetBalances[sellToken] >= sellAmount, "Insufficient balance");

        // Calculate buy amount based on current prices
        uint256 sellPrice = supportedAssets[sellToken].priceOracle;
        uint256 buyPrice = supportedAssets[buyToken].priceOracle;
        uint256 sellValue = (sellAmount * sellPrice) / (10 ** supportedAssets[sellToken].decimals);
        uint256 buyAmount = (sellValue * (10 ** supportedAssets[buyToken].decimals)) / buyPrice;

        require(buyAmount >= minBuyAmount, "Insufficient buy amount (slippage)");

        // Update portfolio balances
        portfolios[portfolioId].assetBalances[sellToken] -= sellAmount;
        portfolios[portfolioId].assetBalances[buyToken] += buyAmount;

        // Create trade record
        uint256 tradeId = _createTradeRecord(portfolioId, sellToken, buyToken, sellAmount, buyAmount, buyPrice);

        // Update portfolio value and risk
        _updatePortfolioValue(portfolioId);
        _calculateRiskScore(portfolioId);

        emit TradeExecuted(tradeId, portfolioId, sellToken, buyToken, sellAmount);
        return tradeId;
    }

    /**
     * @dev Automatically rebalances a portfolio based on target allocations
     * @param portfolioId The portfolio ID to rebalance
     * @return success Whether the rebalancing was successful
     */
    function rebalancePortfolio(uint256 portfolioId) 
        external 
        nonReentrant 
        whenNotPaused
        validPortfolio(portfolioId)
        returns (bool success) 
    {
        AgentPortfolio storage portfolio = portfolios[portfolioId];
        
        // Check if rebalancing is needed
        if (!_needsRebalancing(portfolioId)) {
            return false;
        }

        // Get current allocations
        mapping(string => uint256) storage currentAllocations = portfolio.assetBalances;
        uint256 totalValue = portfolio.totalValue;

        // Calculate required trades
        for (uint i = 0; i < supportedAssetSymbols.length; i++) {
            string memory symbol = supportedAssetSymbols[i];
            uint256 targetAllocation = portfolio.targetAllocations[symbol];
            uint256 targetValue = (totalValue * targetAllocation) / 10000;
            
            uint256 currentBalance = currentAllocations[symbol];
            uint256 currentValue = (currentBalance * supportedAssets[symbol].priceOracle) / 
                                  (10 ** supportedAssets[symbol].decimals);

            if (currentValue > targetValue) {
                // Sell excess
                uint256 excessValue = currentValue - targetValue;
                uint256 sellAmount = (excessValue * (10 ** supportedAssets[symbol].decimals)) / 
                                   supportedAssets[symbol].priceOracle;
                
                // Find underweight asset to buy
                for (uint j = 0; j < supportedAssetSymbols.length; j++) {
                    string memory buySymbol = supportedAssetSymbols[j];
                    uint256 buyTargetValue = (totalValue * portfolio.targetAllocations[buySymbol]) / 10000;
                    uint256 buyCurrentValue = (currentAllocations[buySymbol] * supportedAssets[buySymbol].priceOracle) / 
                                            (10 ** supportedAssets[buySymbol].decimals);
                    
                    if (buyCurrentValue < buyTargetValue) {
                        // Execute rebalancing trade
                        _executeRebalancingTrade(portfolioId, symbol, buySymbol, sellAmount);
                        break;
                    }
                }
            }
        }

        portfolio.lastRebalance = block.timestamp;
        _calculateRiskScore(portfolioId);

        emit PortfolioRebalanced(portfolioId, portfolio.totalValue, portfolio.riskScore);
        return true;
    }

    /**
     * @dev Creates a new trading strategy
     * @param name The strategy name
     * @param strategyType The strategy type
     * @param allocations Target allocations for each supported asset
     * @param maxDrawdown Maximum allowed drawdown
     * @param rebalanceFrequency Rebalancing frequency in seconds
     * @return strategyId The ID of the created strategy
     */
    function createStrategy(
        string memory name,
        StrategyType strategyType,
        mapping(string => uint256) storage allocations,
        uint256 maxDrawdown,
        uint256 rebalanceFrequency
    ) 
        external 
        onlyOwner 
        returns (uint256) 
    {
        strategyCounter++;
        uint256 strategyId = strategyCounter;

        TradingStrategy storage strategy = strategies[strategyId];
        strategy.strategyId = strategyId;
        strategy.name = name;
        strategy.strategyType = strategyType;
        strategy.maxDrawdown = maxDrawdown;
        strategy.rebalanceFrequency = rebalanceFrequency;
        strategy.isActive = true;

        // Copy allocations
        uint256 totalAllocation = 0;
        for (uint i = 0; i < supportedAssetSymbols.length; i++) {
            string memory symbol = supportedAssetSymbols[i];
            strategy.targetAllocations[symbol] = allocations[symbol];
            totalAllocation += allocations[symbol];
        }

        require(totalAllocation == 10000, "Allocations must sum to 100%");

        emit StrategyCreated(strategyId, name, strategyType);
        return strategyId;
    }

    /**
     * @dev Calculates the risk score for a portfolio
     * @param portfolioId The portfolio ID
     * @return riskScore The calculated risk score (0-10000)
     */
    function calculateRiskScore(uint256 portfolioId) 
        external 
        view 
        returns (uint256 riskScore) 
    {
        if (!portfolios[portfolioId].isActive) {
            return 0;
        }

        AgentPortfolio storage portfolio = portfolios[portfolioId];
        uint256 totalRisk = 0;

        // Calculate risk based on asset volatility and allocation
        for (uint i = 0; i < supportedAssetSymbols.length; i++) {
            string memory symbol = supportedAssetSymbols[i];
            uint256 balance = portfolio.assetBalances[symbol];
            if (balance > 0) {
                uint256 value = (balance * supportedAssets[symbol].priceOracle) / 
                               (10 ** supportedAssets[symbol].decimals);
                uint256 allocation = (value * 10000) / portfolio.totalValue;
                
                // Risk contribution based on asset type and allocation
                uint256 assetRisk = _getAssetRisk(symbol);
                totalRisk += (allocation * assetRisk) / 10000;
            }
        }

        // Adjust for strategy type
        uint256 strategyMultiplier = _getStrategyRiskMultiplier(portfolio.strategy);
        riskScore = (totalRisk * strategyMultiplier) / 10000;

        return Math.min(riskScore, maxRiskScore);
    }

    /**
     * @dev Gets the current portfolio value in USD
     * @param portfolioId The portfolio ID
     * @return totalValue The total portfolio value (scaled by 1e8)
     */
    function getPortfolioValue(uint256 portfolioId) 
        external 
        view 
        returns (uint256 totalValue) 
    {
        if (!portfolios[portfolioId].isActive) {
            return 0;
        }

        AgentPortfolio storage portfolio = portfolios[portfolioId];
        totalValue = 0;

        for (uint i = 0; i < supportedAssetSymbols.length; i++) {
            string memory symbol = supportedAssetSymbols[i];
            uint256 balance = portfolio.assetBalances[symbol];
            if (balance > 0) {
                uint256 value = (balance * supportedAssets[symbol].priceOracle) / 
                               (10 ** supportedAssets[symbol].decimals);
                totalValue += value;
            }
        }
    }

    // Internal functions

    function _addAsset(address tokenAddress, string memory symbol, uint256 decimals, uint256 price) internal {
        supportedAssets[symbol] = Asset({
            tokenAddress: tokenAddress,
            symbol: symbol,
            isActive: true,
            decimals: decimals,
            priceOracle: price
        });

        supportedAssetAddresses.push(tokenAddress);
        supportedAssetSymbols.push(symbol);

        emit AssetAdded(tokenAddress, symbol, price);
    }

    function _createTradeRecord(
        uint256 portfolioId,
        string memory sellToken,
        string memory buyToken,
        uint256 sellAmount,
        uint256 buyAmount,
        uint256 price
    ) internal returns (uint256) {
        uint256 tradeId = portfolioTrades[portfolioId].length + 1;
        
        trades[tradeId] = Trade({
            tradeId: tradeId,
            portfolioId: portfolioId,
            sellToken: sellToken,
            buyToken: buyToken,
            sellAmount: sellAmount,
            buyAmount: buyAmount,
            price: price,
            status: TradeStatus.EXECUTED,
            timestamp: block.timestamp,
            executionHash: keccak256(abi.encodePacked(portfolioId, sellToken, buyToken, sellAmount, block.timestamp))
        });

        portfolioTrades[portfolioId].push(tradeId);
        return tradeId;
    }

    function _updatePortfolioValue(uint256 portfolioId) internal {
        uint256 totalValue = 0;
        AgentPortfolio storage portfolio = portfolios[portfolioId];

        for (uint i = 0; i < supportedAssetSymbols.length; i++) {
            string memory symbol = supportedAssetSymbols[i];
            uint256 balance = portfolio.assetBalances[symbol];
            if (balance > 0) {
                uint256 value = (balance * supportedAssets[symbol].priceOracle) / 
                               (10 ** supportedAssets[symbol].decimals);
                totalValue += value;
            }
        }

        portfolio.totalValue = totalValue;
    }

    function _calculateRiskScore(uint256 portfolioId) internal {
        uint256 riskScore = this.calculateRiskScore(portfolioId);
        portfolios[portfolioId].riskScore = riskScore;

        // Determine risk level
        RiskLevel riskLevel;
        if (riskScore < 2500) riskLevel = RiskLevel.LOW;
        else if (riskScore < 5000) riskLevel = RiskLevel.MEDIUM;
        else if (riskScore < 7500) riskLevel = RiskLevel.HIGH;
        else riskLevel = RiskLevel.CRITICAL;

        portfolioRiskMetrics[portfolioId].riskLevel = riskLevel;
        emit RiskAssessment(portfolioId, riskScore, riskLevel);
    }

    function _needsRebalancing(uint256 portfolioId) internal view returns (bool) {
        AgentPortfolio storage portfolio = portfolios[portfolioId];
        
        // Check time-based rebalancing
        if (block.timestamp - portfolio.lastRebalance > strategies[1].rebalanceFrequency) {
            return true;
        }

        // Check threshold-based rebalancing
        uint256 totalValue = portfolio.totalValue;
        for (uint i = 0; i < supportedAssetSymbols.length; i++) {
            string memory symbol = supportedAssetSymbols[i];
            uint256 targetAllocation = portfolio.targetAllocations[symbol];
            uint256 targetValue = (totalValue * targetAllocation) / 10000;
            
            uint256 currentBalance = portfolio.assetBalances[symbol];
            uint256 currentValue = (currentBalance * supportedAssets[symbol].priceOracle) / 
                                  (10 ** supportedAssets[symbol].decimals);

            uint256 deviation = currentValue > targetValue ? 
                ((currentValue - targetValue) * 10000) / targetValue :
                ((targetValue - currentValue) * 10000) / targetValue;

            if (deviation > rebalanceThreshold) {
                return true;
            }
        }

        return false;
    }

    function _executeRebalancingTrade(
        uint256 portfolioId,
        string memory sellToken,
        string memory buyToken,
        uint256 sellAmount
    ) internal {
        // Calculate buy amount
        uint256 sellPrice = supportedAssets[sellToken].priceOracle;
        uint256 buyPrice = supportedAssets[buyToken].priceOracle;
        uint256 sellValue = (sellAmount * sellPrice) / (10 ** supportedAssets[sellToken].decimals);
        uint256 buyAmount = (sellValue * (10 ** supportedAssets[buyToken].decimals)) / buyPrice;

        // Update balances
        portfolios[portfolioId].assetBalances[sellToken] -= sellAmount;
        portfolios[portfolioId].assetBalances[buyToken] += buyAmount;

        // Create trade record
        _createTradeRecord(portfolioId, sellToken, buyToken, sellAmount, buyAmount, buyPrice);
    }

    function _getAssetRisk(string memory symbol) internal pure returns (uint256) {
        // Return risk score for different asset types (in basis points)
        if (keccak256(bytes(symbol)) == keccak256(bytes("AITBC"))) return 3000; // Medium risk
        if (keccak256(bytes(symbol)) == keccak256(bytes("USDC"))) return 500;   // Low risk
        if (keccak256(bytes(symbol)) == keccak256(bytes("ETH"))) return 6000;  // High risk
        return 4000; // Default medium risk
    }

    function _getStrategyRiskMultiplier(StrategyType strategyType) internal pure returns (uint256) {
        if (strategyType == StrategyType.CONSERVATIVE) return 5000;  // 0.5x
        if (strategyType == StrategyType.BALANCED) return 10000;   // 1.0x
        if (strategyType == StrategyType.AGGRESSIVE) return 15000; // 1.5x
        if (strategyType == StrategyType.DYNAMIC) return 12000;    // 1.2x
        return 10000; // Default 1.0x
    }

    // Admin functions

    function updateAssetPrice(string memory symbol, uint256 newPrice) external onlyOwner {
        require(supportedAssets[symbol].isActive, "Asset not supported");
        supportedAssets[symbol].priceOracle = newPrice;
    }

    function setRebalanceThreshold(uint256 newThreshold) external onlyOwner {
        require(newThreshold <= 10000, "Invalid threshold");
        rebalanceThreshold = newThreshold;
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }
}
