pragma circom 2.0.0;

include "node_modules/circomlib/circuits/poseidon.circom";
include "node_modules/circomlib/circuits/bitify.circom";
include "node_modules/circomlib/circuits/comparators.circom";

// Poseidon hash of a fixed-size array of field elements.
template PoseidonHash(n) {
    signal input in[n];
    signal output out;
    component p = Poseidon(n);
    for (var i = 0; i < n; i++) {
        p.inputs[i] <== in[i];
    }
    out <== p.out;
}

// Simple element-wise linear model: out[i] = in[i] * weight + bias.
template SimpleLinear(n) {
    signal input in[n];
    signal input weight;
    signal input bias;
    signal output out[n];
    for (var i = 0; i < n; i++) {
        out[i] <== in[i] * weight + bias;
    }
}

// receipt_model proves a deterministic model execution.
//
// Public signals:
//   input_hash   = Poseidon(input_values)
//   model_hash   = Poseidon(weights)
//   output_hash  = Poseidon(output_values)
//   model_id     = deterministic model identifier (0 = simple linear)
//
// Private signals:
//   input_values[n]   = the job input as field elements
//   weights[m]        = the model weights as field elements
//   output_values[n]  = the model output as field elements
//
// Constraints:
//   Poseidon(input_values) == input_hash
//   Poseidon(weights) == model_hash
//   Poseidon(output_values) == output_hash
//   output_values == Model(model_id, input_values, weights)
//
// This does NOT prove semantic correctness of an open-ended response; it only
// proves that a committed model applied to a committed input produced a
// committed output.
template ReceiptModel(input_len, output_len, weight_len) {
    // Public signals.
    signal input input_hash;
    signal input model_hash;
    signal input output_hash;
    signal input model_id;

    // Private witness.
    signal input input_values[input_len];
    signal input weights[weight_len];
    signal input output_values[output_len];

    // Bind private witness to public hashes.
    component input_hasher = PoseidonHash(input_len);
    for (var i = 0; i < input_len; i++) {
        input_hasher.in[i] <== input_values[i];
    }
    input_hash === input_hasher.out;

    component model_hasher = PoseidonHash(weight_len);
    for (var i = 0; i < weight_len; i++) {
        model_hasher.in[i] <== weights[i];
    }
    model_hash === model_hasher.out;

    component output_hasher = PoseidonHash(output_len);
    for (var i = 0; i < output_len; i++) {
        output_hasher.in[i] <== output_values[i];
    }
    output_hash === output_hasher.out;

    // Model execution. Only model_id 0 is supported in this version.
    component lin = SimpleLinear(output_len);
    for (var i = 0; i < output_len; i++) {
        lin.in[i] <== input_values[i];
    }
    lin.weight <== weights[0];
    lin.bias <== weights[1];
    for (var i = 0; i < output_len; i++) {
        output_values[i] === lin.out[i];
    }

    model_id === 0;
}

component main {public [input_hash, model_hash, output_hash, model_id]} = ReceiptModel(4, 4, 2);
