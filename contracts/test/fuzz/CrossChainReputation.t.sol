// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/CrossChainReputation.sol";

contract CrossChainReputationFuzzTest is Test {
    event ReputationUpdated(address indexed agent, uint256 newScore);

    CrossChainReputation public reputation;
    address public owner;
    address public agent;

    function setUp() public {
        owner = address(this);
        agent = address(0x1);
        reputation = new CrossChainReputation();
    }

    function testFuzz_UpdateReputation(uint256 score, uint256 tasks, uint256 disputes) public {
        reputation.updateReputation(agent, score, tasks, disputes);

        assertEq(reputation.getReputation(agent), score);

        (uint256 storedScore, uint256 storedTasks, uint256 storedDisputes, uint256 lastUpdated) =
            reputation.reputations(agent);
        assertEq(storedScore, score);
        assertEq(storedTasks, tasks);
        assertEq(storedDisputes, disputes);
        assertEq(lastUpdated, block.timestamp);
    }

    function testFuzz_UpdateReputationOnlyOwner(address caller, uint256 score) public {
        vm.assume(caller != owner);

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        reputation.updateReputation(agent, score, 0, 0);
    }

    function testFuzz_UpdateReputationEmitsEvent(uint256 score) public {
        vm.expectEmit(true, false, false, true, address(reputation));
        emit ReputationUpdated(agent, score);
        reputation.updateReputation(agent, score, 0, 0);
    }

    function testFuzz_DefaultReputationIsZero(address agent_) public {
        assertEq(reputation.getReputation(agent_), 0);
    }

    function testFuzz_ReputationOverwrite(uint256 score1, uint256 score2) public {
        reputation.updateReputation(agent, score1, 1, 0);
        reputation.updateReputation(agent, score2, 2, 1);
        assertEq(reputation.getReputation(agent), score2);
    }
}
