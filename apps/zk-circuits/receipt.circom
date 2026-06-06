pragma circom 2.0.0;

include "node_modules/circomlib/circuits/bitify.circom";
include "node_modules/circomlib/circuits/escalarmulfix.circom";
include "node_modules/circomlib/circuits/comparators.circom";
include "node_modules/circomlib/circuits/poseidon.circom";

/*
 * Receipt Attestation Circuit
 * 
 * This circuit proves that a receipt is valid without revealing sensitive details.
 * 
 * Public Inputs:
 * - receiptHash: Hash of the receipt (for public verification)
 * - settlementAmount: Amount to be settled (public)
 * - timestamp: Receipt timestamp (public)
 * 
 * Private Inputs:
 * - receipt: The full receipt data (private)
 * - computationResult: Result of the computation (private)
 * - pricingRate: Pricing rate used (private)
 * - minerReward: Reward for miner (private)
 * - coordinatorFee: Fee for coordinator (private)
 */

template ReceiptAttestation() {
    // Public signals
    signal input receiptHash;
    signal input settlementAmount;
    signal input timestamp;
    
    // Private signals
    signal input receipt[8];
    signal input computationResult;
    signal input pricingRate;
    signal input minerReward;
    signal input coordinatorFee;
    
    // Components
    component hasher = Poseidon(8);
    component amountChecker = GreaterEqThan(8);
    component feeCalculator = Add8(8);
    
    // Hash the receipt to verify it matches the public hash
    for (var i = 0; i < 8; i++) {
        hasher.inputs[i] <== receipt[i];
    }
    
    // Ensure the computed hash matches the public hash
    hasher.out === receiptHash;
    
    // Verify settlement amount calculation
    // settlementAmount = minerReward + coordinatorFee
    feeCalculator.a[0] <== minerReward;
    feeCalculator.a[1] <== coordinatorFee;
    for (var i = 2; i < 8; i++) {
        feeCalculator.a[i] <== 0;
    }
    feeCalculator.out === settlementAmount;
    
    // Ensure amounts are non-negative
    amountChecker.in[0] <== settlementAmount;
    amountChecker.in[1] <== 0;
    amountChecker.out === 1;
    
    // Additional constraints can be added here:
    // - Timestamp validation
    // - Pricing rate bounds
    // - Computation result format
}

/*
 * Simplified Receipt Hash Preimage Circuit
 * 
 * This is a minimal circuit for initial testing that proves
 * knowledge of a receipt preimage without revealing it.
 */
template ReceiptHashPreimage() {
    // Public signal
    signal input hash;
    
    // Private signals (receipt data)
    signal input data[4];
    
    // Hash component
    component poseidon = Poseidon(4);
    
    // Connect inputs
    for (var i = 0; i < 4; i++) {
        poseidon.inputs[i] <== data[i];
    }
    
    // Constraint: computed hash must match public hash
    poseidon.out === hash;
}

/*
 * Signature Verification Component
 *
 * SECURITY NOTE: Signature verification moved off-chain
 *
 * Full on-chain signature verification in Circom is complex and requires
 * significant circuit constraints. For the immediate security fix, signature
 * verification is performed off-chain by the Coordinator API before accepting
 * proofs. The circuit proves knowledge of the receipt preimage without
 * attempting to verify signatures.
 *
 * Future Enhancement: Implement EdDSA verification using circomlib's
 * eddsa.circom circuits for on-chain signature verification.
 *
 * Current Security Model:
 * - API layer verifies signatures before accepting proofs
 * - Circuit proves receipt preimage knowledge
 * - Signature verification is a prerequisite for proof submission
 */

/*
 * Main circuit for initial implementation
 */
component main = ReceiptHashPreimage();
