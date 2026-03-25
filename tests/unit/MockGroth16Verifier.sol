// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract MockGroth16Verifier {
    function verifyProof(bytes memory) external pure returns (bool) {
        return true;
    }
}
