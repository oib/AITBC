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

    // An inbox anyone could fill without bound both spams the recipient and
    // makes getMessages unbounded; cap the depth and give the owner of the
    // inbox a clear plus a paged reader.
    uint256 public constant MAX_INBOX = 100;

    mapping(address => Message[]) public inbox;

    event MessageSent(address indexed sender, address indexed recipient);
    event InboxCleared(address indexed owner, uint256 dropped);

    function sendMessage(address _recipient, string calldata _encryptedContent) external {
        require(inbox[_recipient].length < MAX_INBOX, "Inbox full");
        inbox[_recipient].push(Message(msg.sender, _recipient, _encryptedContent, block.timestamp));
        emit MessageSent(msg.sender, _recipient);
    }

    function getMessages() external view returns (Message[] memory) {
        return getMessages(0, inbox[msg.sender].length);
    }

    function getMessages(uint256 offset, uint256 limit) public view returns (Message[] memory) {
        Message[] storage box = inbox[msg.sender];
        if (offset >= box.length) {
            return new Message[](0);
        }
        uint256 end = offset + limit;
        if (end > box.length || limit == 0) {
            end = box.length;
        }
        Message[] memory out = new Message[](end - offset);
        for (uint256 i = offset; i < end; i++) {
            out[i - offset] = box[i];
        }
        return out;
    }

    function clearInbox() external {
        uint256 dropped = inbox[msg.sender].length;
        delete inbox[msg.sender];
        emit InboxCleared(msg.sender, dropped);
    }
}
