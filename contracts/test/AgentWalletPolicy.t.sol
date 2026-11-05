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
    address public squatter = address(0xBAD);
    address public payee = address(0xCAFE);
    address public otherPayee = address(0xDEAD);

    function setUp() public {
        token = new MockTokenPolicy();
        wallet = new AgentWallet(address(token));
        token.transfer(address(this), 1_000_000 ether);
    }

    function _registerManaged(
        address _policyOwner,
        uint256 _lifetimeLimit,
        uint256 _periodLimit,
        uint256 _periodDuration
    ) internal {
        vm.startPrank(_policyOwner);
        wallet.proposeManagedAgentRegistration(agent, _lifetimeLimit, _periodLimit, _periodDuration);
        vm.stopPrank();
        vm.prank(agent);
        wallet.acceptManagedAgentRegistration(agent, policyOwner);
    }

    function testManagedAgentPolicyOwnerCanWithdraw() public {
        _registerManaged(policyOwner, 100 ether, 10 ether, 1 days);

        token.approve(address(wallet), 50 ether);
        wallet.deposit(agent, 50 ether);

        vm.prank(policyOwner);
        wallet.withdraw(agent, 20 ether);
        assertEq(token.balanceOf(policyOwner), 20 ether);
    }

    function testAgentCannotWithdrawManagedWallet() public {
        _registerManaged(policyOwner, 100 ether, 10 ether, 1 days);

        token.approve(address(wallet), 10 ether);
        wallet.deposit(agent, 10 ether);

        vm.prank(agent);
        vm.expectRevert("Not agent owner");
        wallet.withdraw(agent, 1 ether);
    }

    function testSquatterProposalDoesNotRegisterWithoutAccept() public {
        vm.prank(squatter);
        wallet.proposeManagedAgentRegistration(agent, 100 ether, 0, 0);
        (address owner,,,,) = wallet.agents(agent);
        assertEq(owner, address(0));
        (,,,, bool active) = wallet.pendingManagedRegistration(agent);
        assertTrue(active);

        vm.prank(agent);
        wallet.cancelManagedAgentProposal(agent);
        (,,,, active) = wallet.pendingManagedRegistration(agent);
        assertFalse(active);
    }

    function testOnlyAgentCanAccept() public {
        vm.prank(policyOwner);
        wallet.proposeManagedAgentRegistration(agent, 100 ether, 0, 0);
        vm.prank(squatter);
        vm.expectRevert("Only agent can accept");
        wallet.acceptManagedAgentRegistration(agent, policyOwner);
    }

    function testAllowlistBlocksUnknownRecipient() public {
        _registerManaged(policyOwner, 100 ether, 0, 0);
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
        _registerManaged(policyOwner, 100 ether, 3 ether, 1 hours);

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
    // #1151: the accept must be bound to the intended policy owner — a
    // front-running proposal must not swap who the agent accepts.
    function testFrontRunProposalCannotSwapPolicyOwner() public {
        vm.prank(policyOwner);
        wallet.proposeManagedAgentRegistration(agent, 100 ether, 10 ether, 1 days);
        vm.prank(squatter);
        wallet.proposeManagedAgentRegistration(agent, 1 ether, 0, 0);

        vm.prank(agent);
        vm.expectRevert("Proposal not from expected policy owner");
        wallet.acceptManagedAgentRegistration(agent, policyOwner);

        vm.prank(agent);
        wallet.acceptManagedAgentRegistration(agent, squatter);
        assertEq(wallet.agentPolicyOwner(agent), squatter);
    }

    // #1151: self-registration supersedes a pending proposal — the orphaned
    // entry is cleared instead of lingering as a fake live offer.
    function testSelfRegistrationDropsPendingProposal() public {
        vm.prank(policyOwner);
        wallet.proposeManagedAgentRegistration(agent, 100 ether, 0, 0);
        vm.prank(agent);
        wallet.registerAgent(agent, 50 ether);

        (,,,, bool active) = wallet.pendingManagedRegistration(agent);
        assertFalse(active);
        (address owner,,,,) = wallet.agents(agent);
        assertEq(owner, agent);
    }
}
