// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "../interfaces/IModularContracts.sol";
import "./ContractRegistry.sol";

/**
 * @title TreasuryManager
 * @dev Modular treasury management with budget categories and automated allocation
 * @notice Integrates with DAOGovernance for automated execution and RewardDistributor for rewards
 */
contract TreasuryManager is ITreasuryManager, Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;
    
    // State variables
    uint256 public version = 1;
    IERC20 public treasuryToken;
    ContractRegistry public registry;
    address public daoGovernance;
    
    // Budget categories
    struct BudgetCategory {
        string name;
        uint256 totalBudget;
        uint256 allocatedAmount;
        uint256 spentAmount;
        bool isActive;
        uint256 createdAt;
        address creator;
    }
    
    // Fund allocation
    struct FundAllocation {
        uint256 allocationId;
        string category;
        address recipient;
        uint256 totalAmount;
        uint256 releasedAmount;
        uint256 vestingPeriod;
        uint256 vestingStart;
        uint256 lastRelease;
        bool isCompleted;
        bool isActive;
        address allocatedBy;
        uint256 createdAt;
    }
    
    // Mappings
    mapping(string => BudgetCategory) public budgetCategories;
    mapping(uint256 => FundAllocation) public allocations;
    mapping(string => uint256[]) public categoryAllocations;
    mapping(address => uint256[]) public recipientAllocations;
    
    // Counters
    uint256 public categoryCounter;
    uint256 public allocationCounter;
    string[] public categoryNames;
    
    // Constants
    uint256 public constant MIN_ALLOCATION = 100 * 10**18; // 100 tokens minimum
    uint256 public constant MAX_VESTING_PERIOD = 365 days; // 1 year maximum
    uint256 public constant DEFAULT_VESTING_PERIOD = 30 days; // 30 days default
    
    // Events
    event BudgetCategoryCreated(string indexed category, uint256 budget, address indexed creator);
    event BudgetCategoryUpdated(string indexed category, uint256 newBudget);
    event FundsAllocated(uint256 indexed allocationId, string indexed category, address indexed recipient, uint256 amount);
    event FundsReleased(uint256 indexed allocationId, address indexed recipient, uint256 amount);
    event AllocationCompletedEvent(uint256 indexed allocationId);
    event TreasuryDeposited(address indexed depositor, uint256 amount);
    event TreasuryWithdrawn(address indexed recipient, uint256 amount);
    event CategoryDeactivated(string indexed category);
    
    // Errors
    error InvalidAmount(uint256 amount);
    error InvalidCategory(string category);
    error InsufficientBudget(string category, uint256 requested, uint256 available);
    error AllocationNotFound(uint256 allocationId);
    error AllocationCompletedError(uint256 allocationId);
    error InvalidVestingPeriod(uint256 period);
    error InsufficientBalance(uint256 requested, uint256 available);
    error NotAuthorized();
    error RegistryNotSet();
    
    modifier validAmount(uint256 amount) {
        if (amount == 0) revert InvalidAmount(amount);
        _;
    }
    
    modifier validCategory(string memory category) {
        if (bytes(category).length == 0 || !budgetCategories[category].isActive) {
            revert InvalidCategory(category);
        }
        _;
    }
    
    modifier onlyAuthorized() {
        if (msg.sender != owner() && msg.sender != daoGovernance) revert NotAuthorized();
        _;
    }
    
    modifier registrySet() {
        if (address(registry) == address(0)) revert RegistryNotSet();
        _;
    }
    
    constructor(address _treasuryToken) {
        treasuryToken = IERC20(_treasuryToken);
    }
    
    /**
     * @dev Initialize the treasury manager (implements IModularContract)
     */
    function initialize(address _registry) external override {
        require(address(registry) == address(0), "Already initialized");
        registry = ContractRegistry(_registry);
        
        // Register this contract if not already registered
        bytes32 contractId = keccak256(abi.encodePacked("TreasuryManager"));
        try registry.getContract(contractId) returns (address) {
            // Already registered, skip
        } catch {
            // Not registered, register now
            registry.registerContract(contractId, address(this));
        }
        
        // Get DAO governance address from registry
        try registry.getContract(keccak256(abi.encodePacked("DAOGovernance"))) returns (address govAddress) {
            daoGovernance = govAddress;
        } catch {
            // DAO governance not found, keep as zero address
        }
    }
    
    /**
     * @dev Upgrade the contract
     */
    function upgrade(address newImplementation) external override onlyOwner {
        version++;
        // Implementation upgrade logic would go here
    }
    
    /**
     * @dev Pause the contract
     */
    function pause() external override onlyOwner {
        _pause();
    }
    
    /**
     * @dev Unpause the contract
     */
    function unpause() external override onlyOwner {
        _unpause();
    }
    
    /**
     * @dev Get current version
     */
    function getVersion() external view override returns (uint256) {
        return version;
    }
    
    /**
     * @dev Create a budget category
     */
    function createBudgetCategory(string memory category, uint256 budget) 
        external 
        override 
        onlyAuthorized 
        whenNotPaused 
        validAmount(budget)
        nonReentrant 
    {
        require(budgetCategories[category].createdAt == 0, "Category already exists");
        
        budgetCategories[category] = BudgetCategory({
            name: category,
            totalBudget: budget,
            allocatedAmount: 0,
            spentAmount: 0,
            isActive: true,
            createdAt: block.timestamp,
            creator: msg.sender
        });
        
        categoryNames.push(category);
        categoryCounter++;
        
        emit BudgetCategoryCreated(category, budget, msg.sender);
    }
    
    /**
     * @dev Update budget category
     */
    function updateBudgetCategory(string memory category, uint256 newBudget) 
        external 
        onlyAuthorized 
        whenNotPaused 
        validAmount(newBudget)
        validCategory(category)
        nonReentrant 
    {
        BudgetCategory storage budgetCategory = budgetCategories[category];
        
        // Ensure new budget is not less than allocated amount
        require(newBudget >= budgetCategory.allocatedAmount, "Budget below allocated amount");
        
        budgetCategory.totalBudget = newBudget;
        
        emit BudgetCategoryUpdated(category, newBudget);
    }
    
    /**
     * @dev Allocate funds to a recipient
     */
    function allocateFunds(string memory category, address recipient, uint256 amount) 
        external 
        override 
        onlyAuthorized 
        whenNotPaused 
        validAmount(amount)
        validCategory(category)
        nonReentrant 
    {
        BudgetCategory storage budgetCategory = budgetCategories[category];
        
        // Check budget availability
        uint256 availableBudget = budgetCategory.totalBudget - budgetCategory.allocatedAmount;
        if (amount > availableBudget) {
            revert InsufficientBudget(category, amount, availableBudget);
        }
        
        // Check treasury balance
        uint256 treasuryBalance = treasuryToken.balanceOf(address(this));
        if (amount > treasuryBalance) {
            revert InsufficientBalance(amount, treasuryBalance);
        }
        
        // Create allocation
        uint256 allocationId = ++allocationCounter;
        allocations[allocationId] = FundAllocation({
            allocationId: allocationId,
            category: category,
            recipient: recipient,
            totalAmount: amount,
            releasedAmount: 0,
            vestingPeriod: DEFAULT_VESTING_PERIOD,
            vestingStart: block.timestamp,
            lastRelease: block.timestamp,
            isCompleted: false,
            isActive: true,
            allocatedBy: msg.sender,
            createdAt: block.timestamp
        });
        
        // Update budget category
        budgetCategory.allocatedAmount += amount;
        categoryAllocations[category].push(allocationId);
        recipientAllocations[recipient].push(allocationId);
        
        emit FundsAllocated(allocationId, category, recipient, amount);
    }
    
    /**
     * @dev Allocate funds with custom vesting period
     */
    function allocateFundsWithVesting(
        string memory category, 
        address recipient, 
        uint256 amount, 
        uint256 vestingPeriod
    ) 
        external 
        onlyAuthorized 
        whenNotPaused 
        validAmount(amount)
        validCategory(category)
        nonReentrant 
    {
        if (vestingPeriod > MAX_VESTING_PERIOD) {
            revert InvalidVestingPeriod(vestingPeriod);
        }
        
        BudgetCategory storage budgetCategory = budgetCategories[category];
        
        // Check budget availability
        uint256 availableBudget = budgetCategory.totalBudget - budgetCategory.allocatedAmount;
        if (amount > availableBudget) {
            revert InsufficientBudget(category, amount, availableBudget);
        }
        
        // Check treasury balance
        uint256 treasuryBalance = treasuryToken.balanceOf(address(this));
        if (amount > treasuryBalance) {
            revert InsufficientBalance(amount, treasuryBalance);
        }
        
        // Create allocation with custom vesting
        uint256 allocationId = ++allocationCounter;
        allocations[allocationId] = FundAllocation({
            allocationId: allocationId,
            category: category,
            recipient: recipient,
            totalAmount: amount,
            releasedAmount: 0,
            vestingPeriod: vestingPeriod,
            vestingStart: block.timestamp,
            lastRelease: block.timestamp,
            isCompleted: false,
            isActive: true,
            allocatedBy: msg.sender,
            createdAt: block.timestamp
        });
        
        // Update budget category
        budgetCategory.allocatedAmount += amount;
        categoryAllocations[category].push(allocationId);
        recipientAllocations[recipient].push(allocationId);
        
        emit FundsAllocated(allocationId, category, recipient, amount);
    }
    
    /**
     * @dev Release vested funds
     */
    function releaseVestedFunds(uint256 allocationId) 
        external 
        override 
        whenNotPaused 
        nonReentrant 
    {
        FundAllocation storage allocation = allocations[allocationId];
        
        if (allocation.allocationId == 0) {
            revert AllocationNotFound(allocationId);
        }
        
        if (allocation.isCompleted) {
            revert AllocationCompletedError(allocationId);
        }
        
        if (msg.sender != allocation.recipient && msg.sender != owner() && msg.sender != daoGovernance) {
            revert NotAuthorized();
        }
        
        // Calculate vested amount
        uint256 vestedAmount = calculateVestedAmount(allocation);
        uint256 releasableAmount = vestedAmount - allocation.releasedAmount;
        
        if (releasableAmount == 0) {
            return; // Nothing to release
        }
        
        // Update allocation
        allocation.releasedAmount += releasableAmount;
        allocation.lastRelease = block.timestamp;
        
        // Update budget category spent amount
        budgetCategories[allocation.category].spentAmount += releasableAmount;
        
        // Check if allocation is completed
        if (allocation.releasedAmount >= allocation.totalAmount) {
            allocation.isCompleted = true;
            emit AllocationCompletedEvent(allocationId);
        }
        
        // Transfer tokens
        treasuryToken.safeTransfer(allocation.recipient, releasableAmount);
        
        emit FundsReleased(allocationId, allocation.recipient, releasableAmount);
    }
    
    /**
     * @dev Calculate vested amount for an allocation
     */
    function calculateVestedAmount(FundAllocation memory allocation) public view returns (uint256) {
        if (block.timestamp < allocation.vestingStart) {
            return 0;
        }
        
        uint256 timePassed = block.timestamp - allocation.vestingStart;
        if (timePassed >= allocation.vestingPeriod) {
            return allocation.totalAmount;
        }
        
        return (allocation.totalAmount * timePassed) / allocation.vestingPeriod;
    }
    
    /**
     * @dev Get budget balance for a category
     */
    function getBudgetBalance(string memory category) external view override returns (uint256) {
        BudgetCategory memory budgetCategory = budgetCategories[category];
        return budgetCategory.totalBudget - budgetCategory.allocatedAmount;
    }
    
    /**
     * @dev Get allocation details
     */
    function getAllocation(uint256 allocationId) external view override returns (address, uint256, uint256) {
        FundAllocation memory allocation = allocations[allocationId];
        return (allocation.recipient, allocation.totalAmount, allocation.releasedAmount);
    }
    
    /**
     * @dev Get vested amount for an allocation
     */
    function getVestedAmount(uint256 allocationId) external view returns (uint256) {
        FundAllocation memory allocation = allocations[allocationId];
        return calculateVestedAmount(allocation);
    }
    
    /**
     * @dev Get all allocations for a recipient
     */
    function getRecipientAllocations(address recipient) external view returns (uint256[] memory) {
        return recipientAllocations[recipient];
    }
    
    /**
     * @dev Get all allocations for a category
     */
    function getCategoryAllocations(string memory category) external view returns (uint256[] memory) {
        return categoryAllocations[category];
    }
    
    /**
     * @dev Get all budget categories
     */
    function getBudgetCategories() external view returns (string[] memory) {
        return categoryNames;
    }
    
    /**
     * @dev Get treasury statistics
     */
    function getTreasuryStats() external view returns (
        uint256 totalBudget,
        uint256 allocatedAmount,
        uint256 spentAmount,
        uint256 availableBalance,
        uint256 activeCategories
    ) {
        uint256 _totalBudget = 0;
        uint256 _allocatedAmount = 0;
        uint256 _spentAmount = 0;
        uint256 _activeCategories = 0;
        
        for (uint256 i = 0; i < categoryNames.length; i++) {
            BudgetCategory memory category = budgetCategories[categoryNames[i]];
            if (category.isActive) {
                _totalBudget += category.totalBudget;
                _allocatedAmount += category.allocatedAmount;
                _spentAmount += category.spentAmount;
                _activeCategories++;
            }
        }
        
        return (
            _totalBudget,
            _allocatedAmount,
            _spentAmount,
            treasuryToken.balanceOf(address(this)),
            _activeCategories
        );
    }
    
    /**
     * @dev Deposit funds into treasury
     */
    function depositFunds(uint256 amount) external whenNotPaused validAmount(amount) nonReentrant {
        treasuryToken.safeTransferFrom(msg.sender, address(this), amount);
        emit TreasuryDeposited(msg.sender, amount);
    }
    
    /**
     * @dev Emergency withdraw from treasury
     */
    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(treasuryToken)) {
            treasuryToken.safeTransfer(msg.sender, amount);
        } else {
            IERC20(token).safeTransfer(msg.sender, amount);
        }
        emit TreasuryWithdrawn(msg.sender, amount);
    }
    
    /**
     * @dev Deactivate a budget category
     */
    function deactivateCategory(string memory category) external onlyAuthorized validCategory(category) {
        budgetCategories[category].isActive = false;
        emit CategoryDeactivated(category);
    }
}
