// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/AgentWallet.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockTokenPolicy is ERC20 {
    constructor() ERC20("Mock", "MTK") {
        _mint(msg.sender, 10_000_000 ether);
    }
}

contract AgentWalletPolicyTest is Test {
    AgentWallet public wallet;
    MockTokenPolicy public token;
    address public policyOwner = address(0xA11CE);
    address public agent = address(0xBEEF);
    address public payee = address(0xCAFE);
    address public otherPayee = address(0xDEAD);

    function setUp() public {
        token = new MockTokenPolicy();
        wallet = new AgentWallet(address(token));
        token.transfer(address(this), 1_000_000 ether);
    }

    function testManagedAgentPolicyOwnerCanWithdraw() public {
        vm.prank(policyOwner);
        wallet.registerManagedAgent(agent, 100 ether, 10 ether, 1 days);

        token.approve(address(wallet), 50 ether);
        wallet.deposit(agent, 50 ether);

        vm.prank(policyOwner);
        wallet.withdraw(agent, 20 ether);
        assertEq(token.balanceOf(policyOwner), 20 ether);
    }

    function testAgentCannotWithdrawManagedWallet() public {
        vm.prank(policyOwner);
        wallet.registerManagedAgent(agent, 100 ether, 10 ether, 1 days);

        token.approve(address(wallet), 10 ether);
        wallet.deposit(agent, 10 ether);

        vm.prank(agent);
        vm.expectRevert("Not agent owner");
        wallet.withdraw(agent, 1 ether);
    }

    function testAllowlistBlocksUnknownRecipient() public {
        vm.prank(policyOwner);
        wallet.registerManagedAgent(agent, 100 ether, 0, 0);
        vm.prank(policyOwner);
        wallet.setAllowlistRequired(agent, true);
        vm.prank(policyOwner);
        wallet.setRecipientAllowed(agent, payee, true);

        token.approve(address(wallet), 5 ether);
        wallet.deposit(agent, 5 ether);

        vm.prank(agent);
        vm.expectRevert("Recipient not allowed");
        wallet.executeMicroTransaction(otherPayee, 1 ether, "x");

        vm.prank(agent);
        wallet.executeMicroTransaction(payee, 1 ether, "ok");
        assertEq(token.balanceOf(payee), 1 ether);
    }

    function testPeriodCapResetsAfterWindow() public {
        vm.prank(policyOwner);
        wallet.registerManagedAgent(agent, 100 ether, 3 ether, 1 hours);

        token.approve(address(wallet), 10 ether);
        wallet.deposit(agent, 10 ether);

        vm.prank(agent);
        wallet.executeMicroTransaction(payee, 2 ether, "a");
        vm.prank(agent);
        wallet.executeMicroTransaction(payee, 1 ether, "b");

        vm.prank(agent);
        vm.expectRevert("Period limit exceeded");
        wallet.executeMicroTransaction(payee, 1 ether, "c");

        vm.warp(block.timestamp + 1 hours + 1);

        vm.prank(agent);
        wallet.executeMicroTransaction(payee, 2 ether, "after roll");
        assertEq(wallet.periodSpent(agent), 2 ether);
    }

    function testPurposeLengthBound() public {
        vm.prank(agent);
        wallet.registerAgent(agent, 10 ether);
        token.approve(address(wallet), 1 ether);
        wallet.deposit(agent, 1 ether);

        bytes memory longPurpose = new bytes(257);
        vm.prank(agent);
        vm.expectRevert("Purpose too long");
        wallet.executeMicroTransaction(payee, 1 wei, string(longPurpose));
    }
}
