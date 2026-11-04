// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../contracts/ZKReceiptVerifier.sol";
import "../contracts/PerformanceVerifier.sol";
import "../contracts/AIPowerRental.sol";
import "../contracts/Groth16Verifier.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract PPMockToken is ERC20 {
    constructor() ERC20("T", "T") { _mint(msg.sender, 1e24); }
}

/// #1100 fail-closed pins: no path may accept arbitrary proof bytes.
contract PerformanceProofFailClosedTest is Test {
    ZKReceiptVerifier zk;
    PerformanceVerifier pv;

    function setUp() public {
        zk = new ZKReceiptVerifier();
        pv = new PerformanceVerifier(address(zk), address(new Groth16Verifier()), address(0x13));
    }

    function testZkReceiptVerifyPerformanceProofReverts(bytes memory junk) public {
        vm.expectRevert("performance proof verifier not implemented");
        zk.verifyPerformanceProof(1, 100, 90, 95, 100, junk);
    }

    function testPerformanceVerifierStubReverts(bytes memory junk) public {
        vm.expectRevert("performance proof verifier not implemented");
        pv.verifyPerformanceProof(1, 100, 90, 95, 100, junk);
    }
}
