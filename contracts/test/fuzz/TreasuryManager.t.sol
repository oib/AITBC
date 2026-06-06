// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/contracts/TreasuryManager.sol";
import "../../contracts/contracts/ContractRegistry.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract TreasuryManagerFuzzTest is Test {
    TreasuryManager public treasuryManager;
    ContractRegistry public registry;
    MockToken public token;
    address public owner;
    address public user1;
    address public user2;

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        user2 = address(0x2);

        token = new MockToken();
        
        registry = new ContractRegistry();
        
        treasuryManager = new TreasuryManager(address(token));
        treasuryManager.initialize(address(registry));

        token.transfer(address(treasuryManager), 100_000 * 10**18);
    }

    function testFuzz_CreateBudgetCategory(string memory category, uint256 budget) public {
        vm.assume(budget > 0);
        vm.assume(budget <= 1_000_000 * 10**18);
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        treasuryManager.createBudgetCategory(category, budget);

        (string memory name, uint256 totalBudget, uint256 allocatedAmount, uint256 spentAmount, bool isActive, , , ) = treasuryManager.budgetCategories(category);
        
        assertEq(name, category);
        assertEq(totalBudget, budget);
        assertEq(allocatedAmount, 0);
        assertEq(spentAmount, 0);
        assertTrue(isActive);
    }

    function testFuzz_RevertIfBudgetIsZero(string memory category) public {
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        vm.expectRevert("Invalid amount");
        treasuryManager.createBudgetCategory(category, 0);
    }

    function testFuzz_RevertIfCategoryExists(string memory category, uint256 budget) public {
        vm.assume(budget > 0);
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        treasuryManager.createBudgetCategory(category, budget);

        vm.prank(owner);
        vm.expectRevert("Category already exists");
        treasuryManager.createBudgetCategory(category, budget);
    }

    function testFuzz_AllocateFunds(string memory category, address recipient, uint256 amount) public {
        vm.assume(amount > 0);
        vm.assume(amount <= 10_000 * 10**18);
        vm.assume(recipient != address(0));
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        treasuryManager.createBudgetCategory(category, 10_000 * 10**18);

        vm.prank(owner);
        treasuryManager.allocateFunds(category, recipient, amount);

        (, uint256 allocatedAmount, , , , , , ) = treasuryManager.budgetCategories(category);
        assertEq(allocatedAmount, amount);
    }

    function testFuzz_RevertIfInsufficientBudget(string memory category, address recipient, uint256 amount) public {
        vm.assume(amount > 10_000 * 10**18);
        vm.assume(recipient != address(0));
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        treasuryManager.createBudgetCategory(category, 10_000 * 10**18);

        vm.prank(owner);
        vm.expectRevert("InsufficientBudget");
        treasuryManager.allocateFunds(category, recipient, amount);
    }

    function testFuzz_UpdateBudgetCategory(string memory category, uint256 newBudget) public {
        vm.assume(newBudget > 0);
        vm.assume(newBudget <= 1_000_000 * 10**18);
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        treasuryManager.createBudgetCategory(category, 5_000 * 10**18);

        vm.prank(owner);
        treasuryManager.updateBudgetCategory(category, newBudget);

        (string memory name, uint256 totalBudget, , , , , , ) = treasuryManager.budgetCategories(category);
        
        assertEq(name, category);
        assertEq(totalBudget, newBudget);
    }

    function testFuzz_DepositFunds(uint256 amount) public {
        vm.assume(amount > 0);
        vm.assume(amount <= 10_000 * 10**18);

        token.mint(user1, amount);
        vm.prank(user1);
        token.approve(address(treasuryManager), amount);

        vm.prank(user1);
        treasuryManager.depositFunds(amount);

        assertEq(token.balanceOf(address(treasuryManager)), 100_000 * 10**18 + amount);
    }

    function testFuzz_EmergencyWithdraw(uint256 amount) public {
        vm.assume(amount > 0);
        vm.assume(amount <= 100_000 * 10**18);

        uint256 ownerBalance = token.balanceOf(owner);

        vm.prank(owner);
        treasuryManager.emergencyWithdraw(address(token), amount);

        assertEq(token.balanceOf(owner), ownerBalance + amount);
    }

    function testFuzz_DeactivateCategory(string memory category) public {
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        treasuryManager.createBudgetCategory(category, 10_000 * 10**18);

        vm.prank(owner);
        treasuryManager.deactivateCategory(category);

        (, , , , bool isActive, , , ) = treasuryManager.budgetCategories(category);
        assertFalse(isActive);
    }

    function testFuzz_GetBudgetBalance(string memory category, uint256 budget, uint256 allocated) public {
        vm.assume(budget > 0);
        vm.assume(allocated > 0);
        vm.assume(allocated <= budget);
        vm.assume(budget <= 1_000_000 * 10**18);
        vm.assume(bytes(category).length > 0);
        vm.assume(bytes(category).length <= 100);

        vm.prank(owner);
        treasuryManager.createBudgetCategory(category, budget);

        vm.prank(owner);
        treasuryManager.allocateFunds(category, user1, allocated);

        uint256 balance = treasuryManager.getBudgetBalance(category);
        assertEq(balance, budget - allocated);
    }

    function testFuzz_GetTreasuryStats() public {
        vm.prank(owner);
        treasuryManager.createBudgetCategory("operations", 10_000 * 10**18);
        vm.prank(owner);
        treasuryManager.createBudgetCategory("development", 20_000 * 10**18);

        (uint256 totalBudget, uint256 allocatedAmount, uint256 spentAmount, uint256 availableBalance, uint256 activeCategories) = treasuryManager.getTreasuryStats();
        
        assertEq(totalBudget, 30_000 * 10**18);
        assertEq(allocatedAmount, 0);
        assertEq(spentAmount, 0);
        assertEq(availableBalance, 100_000 * 10**18);
        assertEq(activeCategories, 2);
    }
}
