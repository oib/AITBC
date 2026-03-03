pragma circom 2.0.0;

include "node_modules/circomlib/circuits/bitify.circom";
include "node_modules/circomlib/circuits/poseidon.circom";

/*
 * Simple Receipt Attestation Circuit
 */

template SimpleReceipt() {
    signal input receiptHash;
    signal input receipt[4];
    component hasher = Poseidon(4);
    for (var i = 0; i < 4; i++) {
        hasher.inputs[i] <== receipt[i];
    }
    hasher.out === receiptHash;
}

component main = SimpleReceipt();
