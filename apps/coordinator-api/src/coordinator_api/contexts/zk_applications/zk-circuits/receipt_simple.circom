pragma circom 2.0.0;

include "node_modules/circomlib/circuits/bitify.circom";
include "node_modules/circomlib/circuits/poseidon.circom";

/*
 * Simple Receipt Attestation Circuit
 *
 * This circuit proves that a receipt is valid without revealing sensitive details.
 *
 * Public Inputs:
 * - receiptHash: Hash of the receipt (for public verification)
 *
 * Private Inputs:
 * - receipt: The full receipt data (private)
 */

template SimpleReceipt() {
    // Public signal
    signal input receiptHash;

    // Private signals
    signal input receipt[4];

    // Component for hashing
    component hasher = Poseidon(4);

    // Connect private inputs to hasher
    for (var i = 0; i < 4; i++) {
        hasher.inputs[i] <== receipt[i];
    }

    // Ensure the computed hash matches the public hash
    hasher.out === receiptHash;
}

/*
 * Membership Proof Circuit
 *
 * Proves that a value is part of a set without revealing which one
 */

template MembershipProof(n) {
    // Public signals
    signal input root;
    signal input nullifier;
    signal input pathIndices[n];

    // Private signals
    signal input leaf;
    signal input pathElements[n];
    signal input salt;

    // Component for hashing
    component hasher[n];

    // Initialize hasher for the leaf
    hasher[0] = Poseidon(2);
    hasher[0].inputs[0] <== leaf;
    hasher[0].inputs[1] <== salt;

    // Hash up the Merkle tree
    for (var i = 0; i < n - 1; i++) {
        hasher[i + 1] = Poseidon(2);

        // Choose left or right based on path index
        hasher[i + 1].inputs[0] <== pathIndices[i] * pathElements[i] + (1 - pathIndices[i]) * hasher[i].out;
        hasher[i + 1].inputs[1] <== pathIndices[i] * hasher[i].out + (1 - pathIndices[i]) * pathElements[i];
    }

    // Ensure final hash equals root
    hasher[n - 1].out === root;

    // Compute nullifier as hash(leaf, salt)
    component nullifierHasher = Poseidon(2);
    nullifierHasher.inputs[0] <== leaf;
    nullifierHasher.inputs[1] <== salt;
    nullifierHasher.out === nullifier;
}

/*
 * Note: a BidRangeProof template once lived here; it was removed in
 * 2026-09 because nothing instantiated it and its GreaterEqThan was fed
 * per-bit differences (i.e. it could never work as written).
 */

// Main component instantiation
component main = SimpleReceipt();
