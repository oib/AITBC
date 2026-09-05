// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/AgentCommunication.sol";

contract AgentCommunicationFuzzTest is Test {
    event MessageSent(address indexed sender, address indexed recipient);

    AgentCommunication public comm;
    address public sender;
    address public recipient;

    function setUp() public {
        sender = address(0x1);
        recipient = address(0x2);
        comm = new AgentCommunication();
    }

    function testFuzz_SendMessage(string calldata content) public {
        vm.assume(bytes(content).length <= 256);

        vm.prank(sender);
        comm.sendMessage(recipient, content);

        vm.prank(recipient);
        AgentCommunication.Message[] memory msgs = comm.getMessages();
        assertEq(msgs.length, 1);
        assertEq(msgs[0].sender, sender);
        assertEq(msgs[0].recipient, recipient);
        assertEq(msgs[0].encryptedContent, content);
        assertEq(msgs[0].timestamp, block.timestamp);
    }

    function testFuzz_InboxIsolation(address other) public {
        vm.assume(other != recipient);

        vm.prank(sender);
        comm.sendMessage(recipient, "hello");

        vm.prank(other);
        assertEq(comm.getMessages().length, 0);
    }

    function testFuzz_MessageCount(uint8 n) public {
        vm.assume(n > 0 && n <= 50);

        for (uint256 i = 0; i < n; i++) {
            vm.prank(sender);
            comm.sendMessage(recipient, string(abi.encodePacked("msg", i)));
        }

        vm.prank(recipient);
        assertEq(comm.getMessages().length, n);
    }

    function testFuzz_EmptyInbox(address wallet) public {
        vm.prank(wallet);
        assertEq(comm.getMessages().length, 0);
    }

    function testFuzz_SendMessageEmitsEvent() public {
        vm.expectEmit(true, true, false, false, address(comm));
        emit MessageSent(sender, recipient);
        vm.prank(sender);
        comm.sendMessage(recipient, "ping");
    }
}
