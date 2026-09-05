// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/AgentPortfolioManager.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract AgentPortfolioManagerFuzzTest is Test {
    AgentPortfolioManager public manager;
    MockToken public token;
    address public owner;
    address public agent;

    function setUp() public {
        owner = address(this);
        agent = address(0x1);

        token = new MockToken();
        manager = new AgentPortfolioManager(address(token));
    }

    function _createStrategy() internal returns (uint256 strategyId) {
        string[] memory symbols = new string[](1);
        symbols[0] = "AITBC";
        uint256[] memory allocs = new uint256[](1);
        allocs[0] = 10_000;
        strategyId = manager.createStrategy("balanced", AgentPortfolioManager.StrategyType.BALANCED, 2000, 1 days);
        manager.setStrategyAllocations(strategyId, symbols, allocs);
    }

    function testFuzz_CreateStrategyOnlyOwner(address caller) public {
        vm.assume(caller != owner);

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        manager.createStrategy("s", AgentPortfolioManager.StrategyType.BALANCED, 1000, 1 days);
    }

    function testFuzz_CreateStrategy(string calldata name, uint256 maxDrawdown, uint256 freq) public {
        vm.assume(bytes(name).length <= 64);

        uint256 strategyId = manager.createStrategy(name, AgentPortfolioManager.StrategyType.AGGRESSIVE, maxDrawdown, freq);
        assertEq(strategyId, 1);

        (uint256 id, string memory storedName, AgentPortfolioManager.StrategyType st, uint256 dd, uint256 f, bool isActive) =
            manager.strategies(strategyId);
        assertEq(id, strategyId);
        assertEq(storedName, name);
        assertEq(uint256(st), uint256(AgentPortfolioManager.StrategyType.AGGRESSIVE));
        assertEq(dd, maxDrawdown);
        assertEq(f, freq);
        assertTrue(isActive);
    }

    function testFuzz_SetAllocationsMustSumTo100(uint256 alloc) public {
        vm.assume(alloc != 10_000);
        vm.assume(alloc <= 20_000);

        uint256 strategyId = _createStrategy();

        string[] memory symbols = new string[](1);
        symbols[0] = "AITBC";
        uint256[] memory allocs = new uint256[](1);
        allocs[0] = alloc;

        vm.expectRevert("Allocations must sum to 100%");
        manager.setStrategyAllocations(strategyId, symbols, allocs);
    }

    function testFuzz_SetAllocationsRejectsLengthMismatch() public {
        uint256 strategyId = _createStrategy();

        string[] memory symbols = new string[](2);
        symbols[0] = "AITBC";
        symbols[1] = "AITBC";
        uint256[] memory allocs = new uint256[](1);
        allocs[0] = 10_000;

        vm.expectRevert("Arrays must have same length");
        manager.setStrategyAllocations(strategyId, symbols, allocs);
    }

    function testFuzz_CreatePortfolio(address agentAddr) public {
        vm.assume(agentAddr != address(0));
        uint256 strategyId = _createStrategy();

        uint256 portfolioId = manager.createPortfolio(agentAddr, strategyId);

        assertEq(portfolioId, 1);
        (uint256 id, address portfolioAgent, , , , , bool isActive, ) = manager.portfolios(portfolioId);
        assertEq(id, portfolioId);
        assertEq(portfolioAgent, agentAddr);
        assertTrue(isActive);
        assertEq(manager.agentPortfolio(agentAddr), portfolioId);
    }

    function testFuzz_CreatePortfolioRejectsZeroAgent() public {
        uint256 strategyId = _createStrategy();

        vm.expectRevert("Invalid agent address");
        manager.createPortfolio(address(0), strategyId);
    }

    function testFuzz_CreatePortfolioRejectsInactiveStrategy(uint256 strategyId) public {
        vm.assume(strategyId == 0 || strategyId > manager.strategyCounter());

        vm.expectRevert("Strategy not active");
        manager.createPortfolio(agent, strategyId);
    }

    function testFuzz_CreatePortfolioRejectsDuplicate() public {
        uint256 strategyId = _createStrategy();
        manager.createPortfolio(agent, strategyId);

        vm.expectRevert("Portfolio already exists");
        manager.createPortfolio(agent, strategyId);
    }

    /**
     * @dev The contract has no deposit/fund path: assetBalances are only mutated
     *      inside executeTrade/_executeRebalancingTrade, so every trade reverts
     *      with "Insufficient balance". This test documents the unreachable
     *      trading engine.
     */
    function testFuzz_ExecuteTradeAlwaysReverts(uint256 amount) public {
        amount = bound(amount, 1, 1_000_000 * 10**18);
        uint256 strategyId = _createStrategy();
        uint256 portfolioId = manager.createPortfolio(agent, strategyId);

        vm.prank(agent);
        vm.expectRevert("Insufficient balance");
        manager.executeTrade(portfolioId, "AITBC", "AITBC", amount, 0);
    }

    function testFuzz_ExecuteTradeRejectsNonOwner(address caller) public {
        vm.assume(caller != agent);
        uint256 strategyId = _createStrategy();
        uint256 portfolioId = manager.createPortfolio(agent, strategyId);

        vm.prank(caller);
        vm.expectRevert("Not portfolio owner");
        manager.executeTrade(portfolioId, "AITBC", "AITBC", 1, 0);
    }

    function testFuzz_ExecuteTradeRejectsInvalidPortfolio(uint256 portfolioId) public {
        vm.assume(portfolioId == 0 || portfolioId > manager.portfolioCounter());

        vm.prank(agent);
        vm.expectRevert("Invalid portfolio ID");
        manager.executeTrade(portfolioId, "AITBC", "AITBC", 1, 0);
    }

    function testFuzz_ExecuteTradeRejectsUnknownAsset() public {
        uint256 strategyId = _createStrategy();
        uint256 portfolioId = manager.createPortfolio(agent, strategyId);

        vm.prank(agent);
        vm.expectRevert("Asset not supported");
        manager.executeTrade(portfolioId, "NOPE", "AITBC", 1, 0);
    }

    function testFuzz_CalculateRiskScoreInactiveIsZero(uint256 portfolioId) public {
        assertEq(manager.calculateRiskScore(portfolioId), 0);
    }

    function testFuzz_UpdateAssetPriceOnlyOwner(address caller, uint256 price) public {
        vm.assume(caller != owner);

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        manager.updateAssetPrice("AITBC", price);
    }

    function testFuzz_PauseBlocksPortfolioCreation() public {
        _createStrategy();
        manager.pause();

        vm.expectRevert("Pausable: paused");
        manager.createPortfolio(agent, 1);
        manager.unpause();
    }
}
