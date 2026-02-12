// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title Groth16Verifier
 * @dev Auto-generated Groth16 proof verifier for the SimpleReceipt circuit.
 *
 * To regenerate from the actual circuit:
 *   cd apps/zk-circuits
 *   npx snarkjs groth16 setup receipt_simple.r1cs pot12_final.ptau circuit_0000.zkey
 *   npx snarkjs zkey contribute circuit_0000.zkey circuit_final.zkey --name="AITBC" -v
 *   npx snarkjs zkey export solidityverifier circuit_final.zkey ../../contracts/Groth16Verifier.sol
 *
 * This file is a functional stub that matches the interface expected by
 * ZKReceiptVerifier.sol. Replace with the snarkjs-generated version for production.
 */
contract Groth16Verifier {

    // Verification key points (placeholder — replace with real VK from snarkjs export)
    uint256 constant ALPHA_X = 0x0000000000000000000000000000000000000000000000000000000000000001;
    uint256 constant ALPHA_Y = 0x0000000000000000000000000000000000000000000000000000000000000002;
    uint256 constant BETA_X1 = 0x0000000000000000000000000000000000000000000000000000000000000001;
    uint256 constant BETA_X2 = 0x0000000000000000000000000000000000000000000000000000000000000002;
    uint256 constant BETA_Y1 = 0x0000000000000000000000000000000000000000000000000000000000000003;
    uint256 constant BETA_Y2 = 0x0000000000000000000000000000000000000000000000000000000000000004;
    uint256 constant GAMMA_X1 = 0x0000000000000000000000000000000000000000000000000000000000000001;
    uint256 constant GAMMA_X2 = 0x0000000000000000000000000000000000000000000000000000000000000002;
    uint256 constant GAMMA_Y1 = 0x0000000000000000000000000000000000000000000000000000000000000003;
    uint256 constant GAMMA_Y2 = 0x0000000000000000000000000000000000000000000000000000000000000004;
    uint256 constant DELTA_X1 = 0x0000000000000000000000000000000000000000000000000000000000000001;
    uint256 constant DELTA_X2 = 0x0000000000000000000000000000000000000000000000000000000000000002;
    uint256 constant DELTA_Y1 = 0x0000000000000000000000000000000000000000000000000000000000000003;
    uint256 constant DELTA_Y2 = 0x0000000000000000000000000000000000000000000000000000000000000004;

    // IC points for 1 public signal (SimpleReceipt: receiptHash)
    uint256 constant IC0_X = 0x0000000000000000000000000000000000000000000000000000000000000001;
    uint256 constant IC0_Y = 0x0000000000000000000000000000000000000000000000000000000000000002;
    uint256 constant IC1_X = 0x0000000000000000000000000000000000000000000000000000000000000003;
    uint256 constant IC1_Y = 0x0000000000000000000000000000000000000000000000000000000000000004;

    /**
     * @dev Verify a Groth16 proof.
     * @param a Proof element a (G1 point)
     * @param b Proof element b (G2 point)
     * @param c Proof element c (G1 point)
     * @param input Public signals array (1 element for SimpleReceipt)
     * @return r Whether the proof is valid
     *
     * NOTE: This stub always returns true for development/testing.
     * Replace with the snarkjs-generated verifier for production use.
     */
    function verifyProof(
        uint[2] calldata a,
        uint[2][2] calldata b,
        uint[2] calldata c,
        uint[1] calldata input
    ) public view returns (bool r) {
        // Production: pairing check using bn256 precompiles
        // ecPairing(a, b, alpha, beta, vk_x, gamma, c, delta)
        //
        // Stub: validate proof elements are non-zero
        if (a[0] == 0 && a[1] == 0) return false;
        if (c[0] == 0 && c[1] == 0) return false;
        if (input[0] == 0) return false;

        return true;
    }
}
