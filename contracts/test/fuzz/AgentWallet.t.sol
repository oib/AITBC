// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/AgentWallet.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MTK") {
        _mint(msg.sender, 1_000_000 * 10**18);
    }
}

contract AgentWalletFuzzTest is Test {
    AgentWallet public wallet;
    MockToken public token;
    address public owner;
    address public agentOwner;
    address public agent;
    address public funder;
    address public recipient;

    function setUp() public {
        owner = address(this);
        agentOwner = address(0x1);
        agent = address(0x2);
        funder = address(0x3);
        recipient = address(0x4);

        token = new MockToken();
        wallet = new AgentWallet(address(token));

        token.transfer(funder, 500_000 * 10**18);
    }

    function testFuzz_ConstructorRejectsZeroToken() public {
        vm.expectRevert("Invalid token address");
        new AgentWallet(address(0));
    }

    function testFuzz_RegisterAgent(address agentAddr, uint256 limit) public {
        vm.assume(agentAddr != address(0));

        vm.prank(agentOwner);
        wallet.registerAgent(agentAddr, limit);

        (address agentOwner_, , uint256 spendingLimit, uint256 totalSpent, bool isActive) = wallet.agents(agentAddr);
        assertEq(agentOwner_, agentOwner);
        assertEq(spendingLimit, limit);
        assertEq(totalSpent, 0);
        assertTrue(isActive);
    }

    function testFuzz_RegisterAgentRejectsZero() public {
        vm.expectRevert("Invalid agent address");
        wallet.registerAgent(address(0), 100);
    }

    function testFuzz_RegisterAgentRejectsDuplicate(uint256 limit) public {
        vm.prank(agentOwner);
        wallet.registerAgent(agent, limit);

        vm.prank(owner);
        vm.expectRevert("Agent already registered");
        wallet.registerAgent(agent, limit);
    }

    function testFuzz_Deposit(uint256 amount, uint256 limit) public {
        amount = bound(amount, 1, 400_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, limit);

        vm.startPrank(funder);
        token.approve(address(wallet), amount);
        wallet.deposit(agent, amount);
        vm.stopPrank();

        (, uint256 balance, , , ) = wallet.agents(agent);
        assertEq(balance, amount);
    }

    function testFuzz_DepositRevertsIfInactive(uint256 amount) public {
        amount = bound(amount, 1, 1_000 * 10**18);

        vm.startPrank(agentOwner);
        wallet.registerAgent(agent, 0);
        wallet.deactivateAgent(agent);
        vm.stopPrank();

        vm.startPrank(funder);
        token.approve(address(wallet), amount);
        vm.expectRevert("Agent is not active");
        wallet.deposit(agent, amount);
        vm.stopPrank();
    }

    function testFuzz_Withdraw(uint256 amount) public {
        amount = bound(amount, 1, 400_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, 0);

        vm.startPrank(funder);
        token.approve(address(wallet), amount);
        wallet.deposit(agent, amount);
        vm.stopPrank();

        uint256 ownerBefore = token.balanceOf(agentOwner);
        vm.prank(agentOwner);
        wallet.withdraw(agent, amount);

        assertEq(token.balanceOf(agentOwner), ownerBefore + amount);
        (, uint256 balance, , , ) = wallet.agents(agent);
        assertEq(balance, 0);
    }

    function testFuzz_WithdrawOnlyAgentOwner(address caller, uint256 amount) public {
        vm.assume(caller != agentOwner && caller != address(0));
        amount = bound(amount, 1, 1_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, 0);

        vm.startPrank(funder);
        token.approve(address(wallet), amount);
        wallet.deposit(agent, amount);
        vm.stopPrank();

        vm.prank(caller);
        vm.expectRevert("Not agent owner");
        wallet.withdraw(agent, amount);
    }

    function testFuzz_WithdrawInsufficient(uint256 deposit, uint256 extra) public {
        deposit = bound(deposit, 1, 100_000 * 10**18);
        extra = bound(extra, 1, 100_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, 0);

        vm.startPrank(funder);
        token.approve(address(wallet), deposit);
        wallet.deposit(agent, deposit);
        vm.stopPrank();

        vm.prank(agentOwner);
        vm.expectRevert("Insufficient balance");
        wallet.withdraw(agent, deposit + extra);
    }

    function testFuzz_MicroTransaction(uint256 amount, uint256 limit) public {
        amount = bound(amount, 1, 100_000 * 10**18);
        limit = bound(limit, amount, 200_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, limit);

        vm.startPrank(funder);
        token.approve(address(wallet), amount);
        wallet.deposit(agent, amount);
        vm.stopPrank();

        vm.prank(agent);
        uint256 txId = wallet.executeMicroTransaction(recipient, amount, "test payment");

        assertEq(token.balanceOf(recipient), amount);
        (, uint256 balance, , uint256 totalSpent, ) = wallet.agents(agent);
        assertEq(balance, 0);
        assertEq(totalSpent, amount);

        (, address txAgent, address txRecipient, uint256 txAmount, , ) = wallet.transactions(txId);
        assertEq(txAgent, agent);
        assertEq(txRecipient, recipient);
        assertEq(txAmount, amount);

        uint256[] memory txs = wallet.getAgentTransactions(agent);
        assertEq(txs.length, 1);
        assertEq(txs[0], txId);
    }

    function testFuzz_MicroTransactionRespectsLimit(uint256 amount, uint256 limit) public {
        amount = bound(amount, 2, 100_000 * 10**18);
        limit = bound(limit, 1, amount - 1);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, limit);

        vm.startPrank(funder);
        token.approve(address(wallet), amount);
        wallet.deposit(agent, amount);
        vm.stopPrank();

        vm.prank(agent);
        vm.expectRevert("Spending limit exceeded");
        wallet.executeMicroTransaction(recipient, amount, "over limit");
    }

    function testFuzz_MicroTransactionInsufficientBalance(uint256 amount) public {
        amount = bound(amount, 1, 100_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, type(uint256).max);

        vm.prank(agent);
        vm.expectRevert("Insufficient balance");
        wallet.executeMicroTransaction(recipient, amount, "no funds");
    }

    function testFuzz_MicroTransactionRejectsZeroRecipient(uint256 amount) public {
        amount = bound(amount, 1, 1_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, amount);

        vm.startPrank(funder);
        token.approve(address(wallet), amount);
        wallet.deposit(agent, amount);
        vm.stopPrank();

        vm.prank(agent);
        vm.expectRevert("Invalid recipient");
        wallet.executeMicroTransaction(address(0), amount, "null");
    }

    function testFuzz_MicroTransactionOnlyRegistered(address caller, uint256 amount) public {
        vm.assume(caller != agent);
        amount = bound(amount, 1, 1_000 * 10**18);

        vm.prank(agentOwner);
        wallet.registerAgent(agent, amount);

        vm.prank(caller);
        vm.expectRevert("Agent is not active");
        wallet.executeMicroTransaction(recipient, amount, "unregistered");
    }

    function testFuzz_MultipleTransactionsAccumulateSpent(uint8 n, uint256 amount) public {
        vm.assume(n > 1 && n <= 20);
        amount = bound(amount, 1, 1_000 * 10**18);
        uint256 limit = amount * n;

        vm.prank(agentOwner);
        wallet.registerAgent(agent, limit);

        vm.startPrank(funder);
        token.approve(address(wallet), limit);
        wallet.deposit(agent, limit);
        vm.stopPrank();

        for (uint256 i = 0; i < n; i++) {
            vm.prank(agent);
            wallet.executeMicroTransaction(recipient, amount, "batch");
        }

        (, , , uint256 totalSpent, ) = wallet.agents(agent);
        assertEq(totalSpent, limit);
        assertEq(wallet.getAgentTransactions(agent).length, n);
    }
}
