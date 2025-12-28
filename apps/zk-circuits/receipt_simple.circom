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
 * Bid Range Proof Circuit
 * 
 * Proves that a bid is within a valid range without revealing the amount
 */

template BidRangeProof() {
    // Public signals
    signal input commitment;
    signal input minAmount;
    signal input maxAmount;
    
    // Private signals
    signal input bid;
    signal input salt;
    
    // Component for hashing commitment
    component commitmentHasher = Poseidon(2);
    commitmentHasher.inputs[0] <== bid;
    commitmentHasher.inputs[1] <== salt;
    commitmentHasher.out === commitment;
    
    // Components for range checking
    component minChecker = GreaterEqThan(8);
    component maxChecker = GreaterEqThan(8);
    
    // Convert amounts to 8-bit representation
    component bidBits = Num2Bits(64);
    component minBits = Num2Bits(64);
    component maxBits = Num2Bits(64);
    
    bidBits.in <== bid;
    minBits.in <== minAmount;
    maxBits.in <== maxAmount;
    
    // Check bid >= minAmount
    for (var i = 0; i < 64; i++) {
        minChecker.in[i] <== bidBits.out[i] - minBits.out[i];
    }
    minChecker.out === 1;
    
    // Check maxAmount >= bid
    for (var i = 0; i < 64; i++) {
        maxChecker.in[i] <== maxBits.out[i] - bidBits.out[i];
    }
    maxChecker.out === 1;
}

// Main component instantiation
component main = SimpleReceipt();
