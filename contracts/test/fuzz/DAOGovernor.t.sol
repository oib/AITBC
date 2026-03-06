// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/DAOGovernor.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract DAOGovernorFuzzTest is Test {
    DAOGovernor public governor;
    ERC20 public govToken;
    address public owner;
    address public proposer;
    address public voter;

    function setUp() public {
        owner = address(this);
        proposer = makeAddr("proposer");
        voter = makeAddr("voter");
        govToken = new ERC20("GovToken", "GOV");
        governor = new DAOGovernor(address(govToken));

        // Mint tokens and delegate
        vm.prank(owner);
        govToken.mint(voter, 1000e18);
        vm.prank(voter);
        govToken.delegate(voter);
    }

    function invariant_quorumInvariant() public {
        uint256 quorum = governor.quorum();
        uint256 totalSupply = govToken.totalSupply();
        assertLe(quorum, totalSupply, "Quorum cannot exceed total supply");
    }

    function testFuzz_ProposalFlow(uint256 amount, uint256 votes) public {
        vm.assume(amount >= 1e18 && amount <= 1000e18);
        vm.assume(votes >= 1e18 && votes <= 1000e18);

        vm.prank(owner);
        govToken.mint(proposer, amount);
        vm.prank(proposer);
        govToken.delegate(proposer);

        // Create proposal
        address[] memory targets = new address[](1);
        targets[0] = address(governor);
        uint256[] memory values = new uint256[](1);
        values[0] = 0;
        bytes[] memory calldatas = new bytes[](1);
        calldatas[0] = abi.encodeWithSignature("setQuorum(uint256)", 1000);

        vm.prank(proposer);
        governor.propose(targets, values, calldatas, "Test proposal");
    }
}
