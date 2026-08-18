pragma circom 2.0.0;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

/*
 * Simplified ML Training Verification Circuit
 *
 * Proves that EPOCHS steps of gradient descent were applied to PARAM_COUNT parameters at a
 * learning rate the circuit actually constrains.
 *
 * FIXED POINT (V23-94)
 * --------------------
 * A prime field has no fractions, so `learning_rate` and every parameter are integers scaled
 * by LR_SCALE: the value 10000 with LR_SCALE = 1000000 means a learning rate of 0.01. Both
 * carry the same scale, which is what makes the update below exact — see the derivation there.
 *
 * The previous version wrote the range check as
 *
 *     learning_rate * (1 - learning_rate) === learning_rate;  // Ensures 0 < lr < 1
 *
 * which rearranges to learning_rate^2 === 0. A prime field has no nilpotents, so the only
 * satisfying value was learning_rate = 0 — the one value the comment excludes. With a zero
 * learning rate every epoch below is a no-op, so the circuit could only ever prove that
 * training ran and changed nothing, while still asserting training_complete = 1. Verified
 * against the compiled witness generator: lr = 0 produced a witness, lr = 1 and lr = 2 were
 * rejected.
 */

template SimpleTrainingVerification(PARAM_COUNT, EPOCHS, LR_SCALE, LR_BITS, PARAM_BITS) {
    signal input initial_parameters[PARAM_COUNT];
    signal input learning_rate;

    signal output final_parameters[PARAM_COUNT];
    signal output training_complete;

    // ---------------------------------------------------------------------------------------
    // Learning rate: 0 < learning_rate < LR_SCALE, i.e. 0 < lr < 1 in real terms.
    // ---------------------------------------------------------------------------------------

    // Bound it before comparing. `LessThan` is only sound for inputs below 2^LR_BITS, so a
    // caller who could supply a larger field element would otherwise control the comparison
    // rather than be constrained by it.
    component lr_bound = Num2Bits(LR_BITS);
    lr_bound.in <== learning_rate;

    component lr_below_one = LessThan(LR_BITS);
    lr_below_one.in[0] <== learning_rate;
    lr_below_one.in[1] <== LR_SCALE;
    lr_below_one.out === 1;

    component lr_is_zero = IsZero();
    lr_is_zero.in <== learning_rate;
    lr_is_zero.out === 0;

    // ---------------------------------------------------------------------------------------
    // Training epochs.
    // ---------------------------------------------------------------------------------------

    signal current_parameters[EPOCHS + 1][PARAM_COUNT];

    for (var i = 0; i < PARAM_COUNT; i++) {
        current_parameters[0][i] <== initial_parameters[i];
    }

    // Every epoch's result is range-checked. Subtraction in a prime field wraps, so without
    // this an update that drove a parameter below zero would land on a field element near the
    // modulus and read back as an enormous positive parameter.
    component param_bound[EPOCHS][PARAM_COUNT];

    for (var e = 0; e < EPOCHS; e++) {
        for (var i = 0; i < PARAM_COUNT; i++) {
            // Gradient descent at a unit gradient, in scaled units:
            //
            //   param_real       = param_scaled / LR_SCALE
            //   lr_real          = learning_rate / LR_SCALE
            //   delta_real       = lr_real * 1
            //   param_next_real  = param_real - delta_real
            //                    = (param_scaled - learning_rate) / LR_SCALE
            //
            // so subtracting the scaled learning rate from the scaled parameter is the exact
            // update — no division, no rounding. The unit gradient is a placeholder, as it was
            // before; the comment that claimed 0.1 while the code used 1 is gone.
            current_parameters[e + 1][i] <== current_parameters[e][i] - learning_rate;

            param_bound[e][i] = Num2Bits(PARAM_BITS);
            param_bound[e][i].in <== current_parameters[e + 1][i];
        }
    }

    for (var i = 0; i < PARAM_COUNT; i++) {
        final_parameters[i] <== current_parameters[EPOCHS][i];
    }

    // Carries no information a valid proof does not already carry — every constraint above
    // held, or there would be no proof. Kept because it is part of the published public
    // signal layout.
    training_complete <== 1;
}

// LR_SCALE = 1e6, so a learning rate is given in millionths: 0.01 is 10000.
// LR_BITS = 20 covers LR_SCALE (2^20 = 1048576 > 1000000).
// PARAM_BITS = 40 allows scaled parameters up to ~1.1e12, i.e. real values up to ~1.1e6.
component main = SimpleTrainingVerification(4, 3, 1000000, 20, 40);
