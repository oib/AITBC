pragma circom 2.0.0;

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

    // Use a simple comparison (0 if equal, non-zero if different)
    verified <== 1 - (diff * diff);  // Will be 1 if diff == 0, 0 otherwise
}

component main = SimpleInference();
