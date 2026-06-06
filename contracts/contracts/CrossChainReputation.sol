// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";

contract CrossChainReputation is Ownable {
    struct Reputation {
        uint256 score;
        uint256 taskCompleted;
        uint256 disputeLost;
        uint256 lastUpdated;
    }

    mapping(address => Reputation) public reputations;

    event ReputationUpdated(address indexed agent, uint256 newScore);

    function updateReputation(address _agent, uint256 _score, uint256 _tasks, uint256 _disputes) external onlyOwner {
        reputations[_agent] = Reputation(_score, _tasks, _disputes, block.timestamp);
        emit ReputationUpdated(_agent, _score);
    }

    function getReputation(address _agent) external view returns (uint256) {
        return reputations[_agent].score;
    }
}
