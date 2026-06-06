// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/access/Ownable.sol";

contract AgentCommunication is Ownable {
    struct Message {
        address sender;
        address recipient;
        string encryptedContent;
        uint256 timestamp;
    }

    mapping(address => Message[]) public inbox;

    event MessageSent(address indexed sender, address indexed recipient);

    function sendMessage(address _recipient, string calldata _encryptedContent) external {
        inbox[_recipient].push(Message(msg.sender, _recipient, _encryptedContent, block.timestamp));
        emit MessageSent(msg.sender, _recipient);
    }

    function getMessages() external view returns (Message[] memory) {
        return inbox[msg.sender];
    }
}
