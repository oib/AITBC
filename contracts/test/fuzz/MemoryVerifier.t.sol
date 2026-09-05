// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../../contracts/MemoryVerifier.sol";
import "../../contracts/ZKReceiptVerifier.sol";

contract MemoryVerifierFuzzTest is Test {
    event MemoryVerified(address indexed agent, string cid, bool isValid);

    MemoryVerifier public verifier;
    ZKReceiptVerifier public zkVerifier;
    address public agent;

    function setUp() public {
        agent = address(0x1);
        zkVerifier = new ZKReceiptVerifier();
        verifier = new MemoryVerifier(address(zkVerifier));
    }

    function testFuzz_VerifyMemoryIntegrity(bytes calldata proof, string calldata cid) public {
        vm.assume(bytes(cid).length <= 128);
        vm.assume(proof.length <= 256);

        bool expected = proof.length > 0;
        vm.expectEmit(true, false, false, true, address(verifier));
        emit MemoryVerified(agent, cid, expected);
        verifier.verifyMemoryIntegrity(agent, cid, proof);
    }

    function testFuzz_EmptyProofIsInvalid(string calldata cid) public {
        vm.assume(bytes(cid).length <= 128);

        vm.expectEmit(true, false, false, true, address(verifier));
        emit MemoryVerified(agent, cid, false);
        verifier.verifyMemoryIntegrity(agent, cid, "");
    }

    function testFuzz_ConstructorStoresVerifier(address zk) public {
        MemoryVerifier v = new MemoryVerifier(zk);
        assertEq(address(v.zkVerifier()), zk);
    }
}
