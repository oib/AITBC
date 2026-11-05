// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/AgentMemory.sol";
import "../contracts/AgentIdentity.sol";
import "../contracts/AgentCommunication.sol";
import "../contracts/ZKReceiptVerifier.sol";

/**
 * Pins issue #1123:
 *  - AgentMemory.anchorMemory passed zeroed a/b/c points to the verifier,
 *    ignoring the caller's _proof bytes entirely;
 *  - AgentIdentity.registerAgent was owner-only and named only the owner;
 *  - AgentCommunication inboxes accepted unlimited messages from anyone and
 *    getMessages returned the whole array.
 */
contract AgentTrio1123Test is Test {
    AgentMemory memory_;
    AgentIdentity identity;
    AgentCommunication comm;
    ZKReceiptVerifier verifier;

    address alice = address(0xA);
    address bob = address(0xB);

    function setUp() public {
        verifier = new ZKReceiptVerifier();
        memory_ = new AgentMemory(address(verifier));
        identity = new AgentIdentity();
        comm = new AgentCommunication();
    }

    // --- AgentMemory: the real proof bytes are now decoded and verified ---

    function testAnchorRejectsZeroedProof() public {
        // The exact call the old code made internally: a/b/c all zero must
        // not verify against a real Groth16 verifier.
        bytes memory zeroProof = abi.encode(
            [uint(0), uint(0)],
            [[uint(0), uint(0)], [uint(0), uint(0)]],
            [uint(0), uint(0)]
        );
        vm.prank(alice);
        vm.expectRevert("ZK Proof verification failed");
        memory_.anchorMemory("QmX", "vector_db", bytes32(uint256(1)), zeroProof, false);
    }

    function testAnchorRejectsGarbageProof() public {
        vm.prank(alice);
        vm.expectRevert(); // abi.decode of a malformed blob reverts
        memory_.anchorMemory("QmX", "vector_db", bytes32(uint256(1)), hex"deadbeef", false);
    }

    function testAnchorWithoutProofStillWorks() public {
        vm.prank(alice);
        memory_.anchorMemory("QmX", "vector_db", bytes32(0), "", false);
        AgentMemory.MemoryAnchor memory a = memory_.getLatestMemory(alice);
        assertEq(a.cid, "QmX");
    }

    // --- AgentIdentity: agents name themselves ---

    function testAgentRegistersOwnName() public {
        vm.prank(alice);
        identity.registerAgent("alice-agent");
        assertEq(identity.agentName(alice), "alice-agent");

        vm.prank(bob);
        identity.registerAgent("bob-agent");
        assertEq(identity.agentName(bob), "bob-agent");
        // Alice's name is untouched by Bob's registration.
        assertEq(identity.agentName(alice), "alice-agent");
    }

    // --- AgentCommunication: bounded, pageable, clearable inboxes ---

    function testInboxCapEnforced() public {
        for (uint256 i = 0; i < 100; i++) {
            vm.prank(alice);
            comm.sendMessage(bob, string.concat("m", vm.toString(i)));
        }
        vm.prank(alice);
        vm.expectRevert("Inbox full");
        comm.sendMessage(bob, "overflow");
    }

    function testGetMessagesPaged() public {
        for (uint256 i = 0; i < 10; i++) {
            vm.prank(alice);
            comm.sendMessage(bob, string.concat("m", vm.toString(i)));
        }
        vm.prank(bob);
        AgentCommunication.Message[] memory page = comm.getMessages(4, 3);
        assertEq(page.length, 3);
        assertEq(page[0].encryptedContent, "m4");
        assertEq(page[2].encryptedContent, "m6");

        vm.prank(bob);
        assertEq(comm.getMessages(10, 5).length, 0);
    }

    function testClearInboxUnblocksSenders() public {
        for (uint256 i = 0; i < 100; i++) {
            vm.prank(alice);
            comm.sendMessage(bob, "spam");
        }
        vm.prank(bob);
        comm.clearInbox();
        vm.prank(bob);
        assertEq(comm.getMessages().length, 0);

        vm.prank(alice);
        comm.sendMessage(bob, "after clear");
        vm.prank(bob);
        assertEq(comm.getMessages().length, 1);
    }
}
