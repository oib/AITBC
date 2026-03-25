// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract MockZKVerifier {
    function verifyPerformanceProof(
        uint256,
        uint256,
        uint256,
        uint256,
        uint256,
        bytes memory
    ) external pure returns (bool) {
        return true;
    }
}
