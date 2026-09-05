// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/AgentMemory.sol";
import "../../contracts/ZKReceiptVerifier.sol";

contract AgentMemoryFuzzTest is Test {
    AgentMemory public memory_;
    ZKReceiptVerifier public zkVerifier;
    address public owner;
    address public user1;

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        // No verifier: the proof-verification branch is skipped entirely
        memory_ = new AgentMemory(address(0));
    }

    function testFuzz_AnchorMemory(string calldata cid, string calldata memoryType, bool isEncrypted) public {
        vm.assume(bytes(cid).length > 0 && bytes(cid).length <= 128);
        vm.assume(bytes(memoryType).length > 0 && bytes(memoryType).length <= 64);

        vm.prank(user1);
        memory_.anchorMemory(cid, memoryType, bytes32(0), "", isEncrypted);

        assertEq(memory_.getMemoryCount(user1), 1);
        assertEq(memory_.agentMemoryVersions(user1), 1);

        AgentMemory.MemoryAnchor memory anchor = memory_.getLatestMemory(user1);
        assertEq(anchor.cid, cid);
        assertEq(anchor.memoryType, memoryType);
        assertEq(anchor.zkProofHash, bytes32(0));
        assertEq(anchor.isEncrypted, isEncrypted);
        assertEq(anchor.version, 1);
        assertEq(anchor.timestamp, block.timestamp);
    }

    function testFuzz_VersionIncrements(uint8 n) public {
        vm.assume(n > 0 && n <= 50);

        for (uint256 i = 0; i < n; i++) {
            vm.prank(user1);
            memory_.anchorMemory("QmTest", "vector_db", bytes32(0), "", false);
        }

        assertEq(memory_.getMemoryCount(user1), n);
        assertEq(memory_.agentMemoryVersions(user1), n);
        assertEq(memory_.getLatestMemory(user1).version, n);
    }

    function testFuzz_MemoriesArePerAgent(address agent) public {
        vm.assume(agent != user1 && agent != address(0));

        vm.prank(user1);
        memory_.anchorMemory("QmTest", "vector_db", bytes32(0), "", false);

        assertEq(memory_.getMemoryCount(agent), 0);
    }

    function testFuzz_RevertIfEmptyCid(string calldata memoryType) public {
        vm.assume(bytes(memoryType).length > 0);

        vm.prank(user1);
        vm.expectRevert("Invalid CID");
        memory_.anchorMemory("", memoryType, bytes32(0), "", false);
    }

    function testFuzz_RevertIfEmptyMemoryType(string calldata cid) public {
        vm.assume(bytes(cid).length > 0);

        vm.prank(user1);
        vm.expectRevert("Invalid memory type");
        memory_.anchorMemory(cid, "", bytes32(0), "", false);
    }

    function testFuzz_GetLatestRevertsIfNone(address agent) public {
        vm.assume(agent != user1);

        vm.prank(user1);
        memory_.anchorMemory("QmTest", "vector_db", bytes32(0), "", false);

        vm.expectRevert("No memory anchored");
        memory_.getLatestMemory(agent);
    }

    function testFuzz_UnverifiedHashAcceptedWithoutVerifier(string calldata cid, bytes32 zkProofHash) public {
        vm.assume(bytes(cid).length > 0 && bytes(cid).length <= 128);
        vm.assume(zkProofHash != bytes32(0));

        // With no verifier configured, a non-zero hash is stored unchecked
        vm.prank(user1);
        memory_.anchorMemory(cid, "vector_db", zkProofHash, "", false);

        assertEq(memory_.getLatestMemory(user1).zkProofHash, zkProofHash);
    }

    function testFuzz_UpdateZKVerifierOnlyOwner(address caller, address newVerifier) public {
        vm.assume(caller != owner);
        vm.assume(newVerifier != address(0));

        vm.prank(caller);
        vm.expectRevert("Ownable: caller is not the owner");
        memory_.updateZKVerifier(newVerifier);
    }

    function testFuzz_UpdateZKVerifierZeroAddress() public {
        vm.expectRevert("Invalid address");
        memory_.updateZKVerifier(address(0));
    }

    function testFuzz_AnchorWithVerifierRejectsBadProof(bytes32 zkProofHash) public {
        vm.assume(zkProofHash != bytes32(0));

        zkVerifier = new ZKReceiptVerifier();
        memory_.updateZKVerifier(address(zkVerifier));

        vm.prank(user1);
        vm.expectRevert();
        memory_.anchorMemory("QmTest", "vector_db", zkProofHash, hex"deadbeef", false);
    }

    function testFuzz_AnchorWithVerifierRequiresProof(bytes32 zkProofHash) public {
        vm.assume(zkProofHash != bytes32(0));

        zkVerifier = new ZKReceiptVerifier();
        memory_.updateZKVerifier(address(zkVerifier));

        vm.prank(user1);
        vm.expectRevert("Proof required for hash");
        memory_.anchorMemory("QmTest", "vector_db", zkProofHash, "", false);
    }

    function testFuzz_ConstructorWithZeroVerifier() public {
        AgentMemory m = new AgentMemory(address(0));
        assertEq(address(m.zkVerifier()), address(0));
    }
}
