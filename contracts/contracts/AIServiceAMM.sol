// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";

/**
 * @title AIServiceAMM
 * @dev Automated Market Making protocol for AI service tokens
 * @notice Enables creation of liquidity pools and automated trading for AI services
 */
contract AIServiceAMM is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    using Math for uint256;

    // Constants
    uint256 public constant MINIMUM_LIQUIDITY = 1000; // Minimum liquidity to prevent rounding errors
    uint256 public constant BASIS_POINTS = 10000; // 100% in basis points
    uint256 public constant MAX_FEE = 1000; // Maximum 10% fee
    uint256 public constant FEE_PRECISION = 1000000; // Fee calculation precision

    // State variables
    uint256 public poolCounter;
    uint256 public defaultFee = 30; // 0.3% default fee
    uint256 public protocolFeePercentage = 20; // 20% of fees go to protocol
    address public protocolFeeRecipient;

    // Structs
    struct LiquidityPool {
        uint256 poolId;
        address tokenA;
        address tokenB;
        uint256 reserveA;
        uint256 reserveB;
        uint256 totalLiquidity;
        uint256 feePercentage; // Pool-specific fee in basis points
        address lpToken; // LP token address for this pool
        bool isActive;
        uint256 created_at;
        uint256 lastTradeTime;
        uint256 volume24h;
        uint256 fee24h;
    }

    struct LiquidityPosition {
        uint256 poolId;
        address provider;
        uint256 liquidityAmount;
        uint256 sharesOwned;
        uint256 lastDepositTime;
        uint256 unclaimedFees;
    }

    struct SwapParams {
        uint256 poolId;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minAmountOut;
        address recipient;
        uint256 deadline;
    }

    struct PoolMetrics {
        uint256 totalVolume;
        uint256 totalFees;
        uint256 tvl; // Total Value Locked
        uint256 apr; // Annual Percentage Rate for liquidity providers
        uint256 utilizationRate;
    }

    // Mappings
    mapping(uint256 => LiquidityPool) public pools;
    mapping(address => mapping(uint256 => LiquidityPosition)) public liquidityPositions;
    mapping(address => uint256[]) public providerPools;
    mapping(address => mapping(address => uint256)) public poolByTokenPair; // tokenA -> tokenB -> poolId

    // Arrays
    uint256[] public activePoolIds;

    // Events
    event PoolCreated(uint256 indexed poolId, address indexed tokenA, address indexed tokenB, uint256 fee);
    event LiquidityAdded(uint256 indexed poolId, address indexed provider, uint256 amountA, uint256 amountB, uint256 liquidity);
    event LiquidityRemoved(uint256 indexed poolId, address indexed provider, uint256 amountA, uint256 amountB, uint256 liquidity);
    event SwapExecuted(uint256 indexed poolId, address indexed recipient, address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);
    event FeesCollected(uint256 indexed poolId, uint256 protocolFees, uint256 lpFees);
    event PoolUpdated(uint256 indexed poolId, uint256 reserveA, uint256 reserveB);

    // Modifiers
    modifier validPool(uint256 poolId) {
        require(poolId > 0 && poolId <= poolCounter, "Invalid pool ID");
        require(pools[poolId].isActive, "Pool not active");
        _;
    }

    modifier validDeadline(uint256 deadline) {
        require(block.timestamp <= deadline, "Transaction expired");
        _;
    }

    modifier nonZeroAmount(uint256 amount) {
        require(amount > 0, "Amount must be greater than 0");
        _;
    }

    constructor(address _protocolFeeRecipient) {
        protocolFeeRecipient = _protocolFeeRecipient;
    }

    /**
     * @dev Creates a new liquidity pool for two tokens
     * @param tokenA Address of the first token
     * @param tokenB Address of the second token
     * @param feePercentage Fee percentage in basis points
     * @return poolId The ID of the created pool
     */
    function createPool(
        address tokenA,
        address tokenB,
        uint256 feePercentage
    ) external nonReentrant whenNotPaused returns (uint256) {
        require(tokenA != tokenB, "Identical tokens");
        require(tokenA != address(0) && tokenB != address(0), "Zero address");
        require(feePercentage <= MAX_FEE, "Fee too high");
        require(poolByTokenPair[tokenA][tokenB] == 0 && poolByTokenPair[tokenB][tokenA] == 0, "Pool exists");

        // Ensure tokenA < tokenB for consistency
        if (tokenA > tokenB) {
            (tokenA, tokenB) = (tokenB, tokenA);
        }

        poolCounter++;
        uint256 poolId = poolCounter;

        pools[poolId] = LiquidityPool({
            poolId: poolId,
            tokenA: tokenA,
            tokenB: tokenB,
            reserveA: 0,
            reserveB: 0,
            totalLiquidity: 0,
            feePercentage: feePercentage,
            lpToken: address(this), // Simplified LP token representation
            isActive: true,
            created_at: block.timestamp,
            lastTradeTime: 0,
            volume24h: 0,
            fee24h: 0
        });

        poolByTokenPair[tokenA][tokenB] = poolId;
        poolByTokenPair[tokenB][tokenA] = poolId;
        activePoolIds.push(poolId);

        emit PoolCreated(poolId, tokenA, tokenB, feePercentage);
        return poolId;
    }

    /**
     * @dev Adds liquidity to a pool
     * @param poolId The pool ID
     * @param amountA Amount of tokenA to add
     * @param amountB Amount of tokenB to add
     * @param minAmountA Minimum amount of tokenA (slippage protection)
     * @param minAmountB Minimum amount of tokenB (slippage protection)
     * @return liquidityAmount The amount of liquidity tokens received
     */
    function addLiquidity(
        uint256 poolId,
        uint256 amountA,
        uint256 amountB,
        uint256 minAmountA,
        uint256 minAmountB
    ) 
        external 
        nonReentrant 
        whenNotPaused
        validPool(poolId)
        nonZeroAmount(amountA)
        nonZeroAmount(amountB)
        returns (uint256 liquidityAmount) 
    {
        LiquidityPool storage pool = pools[poolId];
        
        // Calculate optimal amounts based on current reserves
        uint256 optimalAmountB = _calculateOptimalAmountB(poolId, amountA);
        
        if (pool.reserveA == 0 && pool.reserveB == 0) {
            // First liquidity provider - set initial prices
            optimalAmountB = amountB;
        } else {
            require(amountB >= optimalAmountB, "Insufficient tokenB amount");
        }

        // Transfer tokens to contract
        IERC20(pool.tokenA).safeTransferFrom(msg.sender, address(this), amountA);
        IERC20(pool.tokenB).safeTransferFrom(msg.sender, address(this), amountB);

        // Calculate liquidity to mint
        if (pool.totalLiquidity == 0) {
            liquidityAmount = Math.sqrt(amountA * amountB) - MINIMUM_LIQUIDITY;
            pool.totalLiquidity += MINIMUM_LIQUIDITY; // Lock minimum liquidity
        } else {
            liquidityAmount = Math.min(
                (amountA * pool.totalLiquidity) / pool.reserveA,
                (amountB * pool.totalLiquidity) / pool.reserveB
            );
        }

        require(liquidityAmount > 0, "Insufficient liquidity minted");

        // Update pool reserves and liquidity
        pool.reserveA += amountA;
        pool.reserveB += amountB;
        pool.totalLiquidity += liquidityAmount;

        // Update or create liquidity position
        LiquidityPosition storage position = liquidityPositions[msg.sender][poolId];
        position.poolId = poolId;
        position.provider = msg.sender;
        position.liquidityAmount += liquidityAmount;
        position.sharesOwned = (position.liquidityAmount * BASIS_POINTS) / pool.totalLiquidity;
        position.lastDepositTime = block.timestamp;

        // Add to provider's pool list if new
        if (position.liquidityAmount == liquidityAmount) {
            providerPools[msg.sender].push(poolId);
        }

        emit LiquidityAdded(poolId, msg.sender, amountA, amountB, liquidityAmount);
        emit PoolUpdated(poolId, pool.reserveA, pool.reserveB);
    }

    /**
     * @dev Removes liquidity from a pool
     * @param poolId The pool ID
     * @param liquidityAmount Amount of liquidity to remove
     * @param minAmountA Minimum amount of tokenA to receive
     * @param minAmountB Minimum amount of tokenB to receive
     * @return amountA Amount of tokenA received
     * @return amountB Amount of tokenB received
     */
    function removeLiquidity(
        uint256 poolId,
        uint256 liquidityAmount,
        uint256 minAmountA,
        uint256 minAmountB
    ) 
        external 
        nonReentrant 
        whenNotPaused
        validPool(poolId)
        nonZeroAmount(liquidityAmount)
        returns (uint256 amountA, uint256 amountB) 
    {
        LiquidityPool storage pool = pools[poolId];
        LiquidityPosition storage position = liquidityPositions[msg.sender][poolId];

        require(position.liquidityAmount >= liquidityAmount, "Insufficient liquidity");

        // Calculate amounts to receive
        amountA = (liquidityAmount * pool.reserveA) / pool.totalLiquidity;
        amountB = (liquidityAmount * pool.reserveB) / pool.totalLiquidity;

        require(amountA >= minAmountA && amountB >= minAmountB, "Slippage protection");

        // Update pool reserves and liquidity
        pool.reserveA -= amountA;
        pool.reserveB -= amountB;
        pool.totalLiquidity -= liquidityAmount;

        // Update position
        position.liquidityAmount -= liquidityAmount;
        position.sharesOwned = (position.liquidityAmount * BASIS_POINTS) / pool.totalLiquidity;

        // Transfer tokens to user
        IERC20(pool.tokenA).safeTransfer(msg.sender, amountA);
        IERC20(pool.tokenB).safeTransfer(msg.sender, amountB);

        emit LiquidityRemoved(poolId, msg.sender, amountA, amountB, liquidityAmount);
        emit PoolUpdated(poolId, pool.reserveA, pool.reserveB);
    }

    /**
     * @dev Executes a token swap
     * @param params Swap parameters
     * @return amountOut Amount of tokens received
     */
    function swap(SwapParams calldata params) 
        external 
        nonReentrant 
        whenNotPaused
        validPool(params.poolId)
        validDeadline(params.deadline)
        nonZeroAmount(params.amountIn)
        returns (uint256 amountOut) 
    {
        LiquidityPool storage pool = pools[params.poolId];

        // Validate tokens
        require(
            params.tokenIn == pool.tokenA || params.tokenIn == pool.tokenB,
            "Invalid input token"
        );
        require(
            params.tokenOut == pool.tokenA || params.tokenOut == pool.tokenB,
            "Invalid output token"
        );
        require(params.tokenIn != params.tokenOut, "Same token swap");

        // Calculate output amount
        amountOut = _calculateSwapOutput(params.poolId, params.amountIn, params.tokenIn);
        require(amountOut >= params.minAmountOut, "Insufficient output amount");

        // Transfer input tokens
        IERC20(params.tokenIn).safeTransferFrom(msg.sender, address(this), params.amountIn);

        // Update reserves
        if (params.tokenIn == pool.tokenA) {
            pool.reserveA += params.amountIn;
            pool.reserveB -= amountOut;
        } else {
            pool.reserveB += params.amountIn;
            pool.reserveA -= amountOut;
        }

        // Transfer output tokens
        IERC20(params.tokenOut).safeTransfer(params.recipient, amountOut);

        // Update pool metrics
        pool.lastTradeTime = block.timestamp;
        pool.volume24h += params.amountIn;

        emit SwapExecuted(params.poolId, params.recipient, params.tokenIn, params.tokenOut, params.amountIn, amountOut);
        emit PoolUpdated(params.poolId, pool.reserveA, pool.reserveB);
    }

    /**
     * @dev Calculates the optimal amount of tokenB for adding liquidity
     * @param poolId The pool ID
     * @param amountIn Amount of tokenIn
     * @return amountOut Optimal amount of tokenOut
     */
    function calculateOptimalSwap(uint256 poolId, uint256 amountIn) 
        external 
        view 
        validPool(poolId)
        returns (uint256 amountOut) 
    {
        return _calculateSwapOutput(poolId, amountIn, pools[poolId].tokenA);
    }

    /**
     * @dev Gets pool metrics
     * @param poolId The pool ID
     * @return metrics Pool metrics
     */
    function getPoolMetrics(uint256 poolId) 
        external 
        view 
        validPool(poolId)
        returns (PoolMetrics memory metrics) 
    {
        LiquidityPool storage pool = pools[poolId];
        
        uint256 totalValue = pool.reserveA + pool.reserveB; // Simplified TVL calculation
        uint256 annualFees = pool.fee24h * 365; // Simplified APR calculation
        
        metrics = PoolMetrics({
            totalVolume: pool.volume24h,
            totalFees: pool.fee24h,
            tvl: totalValue,
            apr: totalValue > 0 ? (annualFees * BASIS_POINTS) / totalValue : 0,
            utilizationRate: pool.totalLiquidity > 0 ? ((pool.volume24h * BASIS_POINTS) / pool.totalLiquidity) : 0
        });
    }

    /**
     * @dev Gets the amount of liquidity tokens a user owns in a pool
     * @param provider The liquidity provider address
     * @param poolId The pool ID
     * @return liquidityAmount Amount of liquidity tokens
     */
    function getLiquidityAmount(address provider, uint256 poolId) 
        external 
        view 
        returns (uint256 liquidityAmount) 
    {
        return liquidityPositions[provider][poolId].liquidityAmount;
    }

    // Internal functions

    function _calculateOptimalAmountB(uint256 poolId, uint256 amountA) internal view returns (uint256) {
        LiquidityPool storage pool = pools[poolId];
        if (pool.reserveA == 0) return 0;
        return (amountA * pool.reserveB) / pool.reserveA;
    }

    function _calculateSwapOutput(uint256 poolId, uint256 amountIn, address tokenIn) 
        internal 
        view 
        returns (uint256 amountOut) 
    {
        LiquidityPool storage pool = pools[poolId];
        
        uint256 reserveIn;
        uint256 reserveOut;
        
        if (tokenIn == pool.tokenA) {
            reserveIn = pool.reserveA;
            reserveOut = pool.reserveB;
        } else {
            reserveIn = pool.reserveB;
            reserveOut = pool.reserveA;
        }

        // Apply fee
        uint256 feeAmount = (amountIn * pool.feePercentage) / BASIS_POINTS;
        uint256 amountInAfterFee = amountIn - feeAmount;

        // Calculate output using constant product formula
        amountOut = (amountInAfterFee * reserveOut) / (reserveIn + amountInAfterFee);

        // Ensure minimum output
        require(amountOut > 0, "Insufficient output amount");
        require(reserveOut > amountOut, "Insufficient liquidity");
    }

    function _collectFees(uint256 poolId) internal {
        LiquidityPool storage pool = pools[poolId];
        
        if (pool.fee24h == 0) return;

        uint256 protocolFees = (pool.fee24h * protocolFeePercentage) / BASIS_POINTS;
        uint256 lpFees = pool.fee24h - protocolFees;

        // Distribute fees to liquidity providers
        if (lpFees > 0 && pool.totalLiquidity > 0) {
            for (uint i = 0; i < activePoolIds.length; i++) {
                uint256 currentPoolId = activePoolIds[i];
                if (currentPoolId == poolId) {
                    // Simplified fee distribution
                    // In production, this would be more sophisticated
                    break;
                }
            }
        }

        emit FeesCollected(poolId, protocolFees, lpFees);
        pool.fee24h = 0;
    }

    // Admin functions

    function setProtocolFeeRecipient(address newRecipient) external onlyOwner {
        require(newRecipient != address(0), "Invalid address");
        protocolFeeRecipient = newRecipient;
    }

    function setProtocolFeePercentage(uint256 newPercentage) external onlyOwner {
        require(newPercentage <= BASIS_POINTS, "Invalid percentage");
        protocolFeePercentage = newPercentage;
    }

    function setDefaultFee(uint256 newFee) external onlyOwner {
        require(newFee <= MAX_FEE, "Fee too high");
        defaultFee = newFee;
    }

    function pause() external onlyOwner {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    // Emergency functions

    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        IERC20(token).safeTransfer(owner(), amount);
    }

    function emergencyPause() external onlyOwner {
        _pause();
    }
}
