pragma circom 2.0.0;

include "node_modules/circomlib/circuits/comparators.circom";

// Simple ML inference verification circuit
// Basic test circuit to verify compilation

template SimpleInference() {
    signal input x;     // input
    signal input w;     // weight
    signal input b;     // bias
    signal input expected; // expected output

    signal output verified;

    // Simple computation: output = x * w + b
    signal computed;
    computed <== x * w + b;

    // Check if computed equals expected
    signal diff;
    diff <== computed - expected;

    // Use IsZero circuit to properly check if diff == 0
    component isZero = IsZero();
    isZero.in <== diff;
    verified <== isZero.out;
}

component main = SimpleInference();
