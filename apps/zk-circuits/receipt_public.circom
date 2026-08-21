pragma circom 2.0.0;

include "node_modules/circomlib/circuits/bitify.circom";
include "node_modules/circomlib/circuits/poseidon.circom";

template SimpleReceiptPublic() {
    // Public signal: the expected Poseidon hash of the private receipt
    signal input receiptHash;

    // Private signals
    signal input receipt[4];

    // Hash the private receipt
    component hasher = Poseidon(4);
    for (var i = 0; i < 4; i++) {
        hasher.inputs[i] <== receipt[i];
    }

    // Ensure the computed hash matches the public hash
    hasher.out === receiptHash;
}

component main {public [receiptHash]} = SimpleReceiptPublic();
