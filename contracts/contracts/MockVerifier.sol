// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title MockVerifier
 * @dev Mock verifier for testing purposes
 */
contract MockVerifier {
    function verifyPerformance(
        uint256 _agentWallet,
        uint256 _responseTime,
        uint256 _accuracy,
        uint256 _availability,
        uint256 _computePower,
        bytes memory _zkProof
    ) external pure returns (bool) {
        // Always return true for testing
        return true;
    }
}
