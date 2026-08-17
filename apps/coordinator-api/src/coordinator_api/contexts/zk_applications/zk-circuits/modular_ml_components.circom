pragma circom 2.0.0;

include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

/*
 * Modular ML Circuit Components
 *
 * Reusable components for machine learning circuits.
 *
 * FIXED POINT (V23-94)
 * --------------------
 * A prime field has no fractions. Parameters and the learning rate are integers scaled by
 * LR_SCALE: with LR_SCALE = 1000000, the value 10000 means a learning rate of 0.01. Gradients
 * are *unscaled* integers, so `learning_rate * gradient` comes out at LR_SCALE and can be
 * subtracted from a scaled parameter directly. Mixing the scales up is the whole difficulty
 * here, so each template says which scale each of its signals carries.
 *
 * Every input that reaches a comparison or a subtraction is bounded first. `LessThan` and
 * `LessEqThan` are only sound for inputs below 2^n, and field subtraction wraps: without a
 * bound, a caller who supplies a large field element controls the comparison instead of being
 * constrained by it, and an update that drives a parameter below zero lands near the modulus
 * and reads back as an enormous positive parameter.
 *
 * WHAT WAS WRONG BEFORE
 * ---------------------
 * `LearningRateValidation` was an empty template:
 *
 *     // Removed constraint for optimization - learning rate validation handled externally
 *     // This reduces non-linear constraints from 1 to 0 for better proving performance
 *
 * Nothing validated it externally. `POST /v1/ml-zk/prove/modular` passes `inputs` straight to
 * the witness generator, so any learning rate at all proved -- negative, zero, a thousand, a
 * field element one below the modulus. The "optimization" removed the circuit's only check on
 * its only scalar input and the API advertised the result as a feature.
 *
 * The constraint it replaced was no better. It still stands in `apps/zk-circuits`:
 *
 *     component lt1 = LessThan(252);  lt1.in[0] <== learning_rate;  lt1.in[1] <== 1;
 *     component gt0 = GreaterThan(252); gt0.in[0] <== learning_rate; gt0.in[1] <== 0;
 *
 * which asks for an integer strictly between 0 and 1. That circuit is unsatisfiable for every
 * input -- verified by compiling it and generating witnesses at lr = 0, 1, 2, 10000 and
 * 1000000: all five rejected. Comparing against the literal 1 is the bug in both copies; the
 * bound has to be LR_SCALE.
 *
 * `LossConstraint` was worse than wrong, it could not compile:
 *
 *     diff_squared * (1 - diff_squared / tolerance_squared) === 0;
 *
 * Dividing by a signal is not a quadratic constraint and circom rejects it. It was never
 * instantiated, so it was never compiled and nobody found out. Read as arithmetic it permits
 * exactly two losses -- 0 and the tolerance -- rather than the range the comment claims.
 */

// Gradient descent step for one parameter.
//
//   current_param, learning_rate, new_param : scaled by LR_SCALE
//   gradient                                : unscaled integer, bounded to GRAD_BITS
template ParameterUpdate(GRAD_BITS) {
    signal input current_param;
    signal input gradient;
    signal input learning_rate;

    signal output new_param;

    // Bound the gradient before multiplying. learning_rate is bounded by whoever validated it
    // (LearningRateValidation below); an unbounded gradient would let the product be any field
    // element and put new_param anywhere.
    component gradient_bound = Num2Bits(GRAD_BITS);
    gradient_bound.in <== gradient;

    new_param <== current_param - learning_rate * gradient;
}

// The same step across a parameter vector, at one shared learning rate.
template VectorParameterUpdate(PARAM_COUNT, GRAD_BITS) {
    signal input current_params[PARAM_COUNT];
    signal input gradients[PARAM_COUNT];
    signal input learning_rate;

    signal output new_params[PARAM_COUNT];

    component updates[PARAM_COUNT];

    for (var i = 0; i < PARAM_COUNT; i++) {
        updates[i] = ParameterUpdate(GRAD_BITS);
        updates[i].current_param <== current_params[i];
        updates[i].gradient <== gradients[i];
        updates[i].learning_rate <== learning_rate;
        new_params[i] <== updates[i].new_param;
    }
}

// |predicted_loss - actual_loss| <= tolerance, for values in [0, 2^N).
//
// Both directions are needed and neither is a squaring. Let shifted = predicted - actual +
// tolerance. Bounding it to N + 1 bits forces shifted >= 0, because a negative difference is
// a field element near the modulus and cannot be written in N + 1 bits -- that is
// actual - predicted <= tolerance. Comparing shifted <= 2 * tolerance is the other direction.
// Together they are the absolute-value bound the old comment claimed.
template LossConstraint(N) {
    signal input predicted_loss;
    signal input actual_loss;
    signal input tolerance;

    component predicted_bound = Num2Bits(N);
    predicted_bound.in <== predicted_loss;

    component actual_bound = Num2Bits(N);
    actual_bound.in <== actual_loss;

    component tolerance_bound = Num2Bits(N);
    tolerance_bound.in <== tolerance;

    signal shifted;
    shifted <== predicted_loss - actual_loss + tolerance;

    // shifted >= 0. With all three inputs in [0, 2^N), shifted is in (-2^N, 2^(N+1)), so this
    // range check rules out exactly the negative half.
    component shifted_bound = Num2Bits(N + 1);
    shifted_bound.in <== shifted;

    // shifted <= 2 * tolerance. Both sides are below 2^(N+1), inside LessEqThan's domain.
    component within = LessEqThan(N + 2);
    within.in[0] <== shifted;
    within.in[1] <== 2 * tolerance;
    within.out === 1;
}

// 0 < learning_rate < LR_SCALE, i.e. 0 < lr < 1 in real terms.
template LearningRateValidation(LR_SCALE, LR_BITS) {
    signal input learning_rate;

    // Bound before comparing -- see the module docstring.
    component lr_bound = Num2Bits(LR_BITS);
    lr_bound.in <== learning_rate;

    component lr_below_one = LessThan(LR_BITS);
    lr_below_one.in[0] <== learning_rate;
    lr_below_one.in[1] <== LR_SCALE;
    lr_below_one.out === 1;

    component lr_is_zero = IsZero();
    lr_is_zero.in <== learning_rate;
    lr_is_zero.out === 0;
}

// One epoch: update every parameter, then prove the results stayed in range.
template TrainingEpoch(PARAM_COUNT, GRAD_BITS, PARAM_BITS) {
    signal input epoch_params[PARAM_COUNT];
    signal input epoch_gradients[PARAM_COUNT];
    signal input learning_rate;

    signal output next_epoch_params[PARAM_COUNT];

    component param_update = VectorParameterUpdate(PARAM_COUNT, GRAD_BITS);
    param_update.current_params <== epoch_params;
    param_update.gradients <== epoch_gradients;
    param_update.learning_rate <== learning_rate;
    next_epoch_params <== param_update.new_params;

    // Subtraction wraps, so an update that took a parameter below zero would otherwise be
    // indistinguishable from one that produced a huge positive parameter.
    component param_bound[PARAM_COUNT];
    for (var i = 0; i < PARAM_COUNT; i++) {
        param_bound[i] = Num2Bits(PARAM_BITS);
        param_bound[i].in <== next_epoch_params[i];
    }
}

// Main modular training verification using components.
template ModularTrainingVerification(PARAM_COUNT, EPOCHS, LR_SCALE, LR_BITS, GRAD_BITS, PARAM_BITS) {
    signal input initial_parameters[PARAM_COUNT];
    signal input learning_rate;

    // Gradients are an input, one set per epoch. They used to be hardcoded to 1 in the loop
    // below -- `epochs[e].epoch_gradients[i] <== 1;  // Constant gradient` -- under a comment
    // saying they "would be computed in real implementation", while `TrainingEpoch` already
    // took them as a signal. A proof of gradient descent whose gradients are a circuit
    // constant proves nothing about anyone's training run.
    signal input gradients[EPOCHS][PARAM_COUNT];

    signal output final_parameters[PARAM_COUNT];
    signal output training_complete;

    component lr_validator = LearningRateValidation(LR_SCALE, LR_BITS);
    lr_validator.learning_rate <== learning_rate;

    signal current_params[EPOCHS + 1][PARAM_COUNT];

    for (var i = 0; i < PARAM_COUNT; i++) {
        current_params[0][i] <== initial_parameters[i];
    }

    component epochs[EPOCHS];
    for (var e = 0; e < EPOCHS; e++) {
        epochs[e] = TrainingEpoch(PARAM_COUNT, GRAD_BITS, PARAM_BITS);

        for (var i = 0; i < PARAM_COUNT; i++) {
            epochs[e].epoch_params[i] <== current_params[e][i];
            epochs[e].epoch_gradients[i] <== gradients[e][i];
        }

        epochs[e].learning_rate <== learning_rate;

        for (var i = 0; i < PARAM_COUNT; i++) {
            current_params[e + 1][i] <== epochs[e].next_epoch_params[i];
        }
    }

    for (var i = 0; i < PARAM_COUNT; i++) {
        final_parameters[i] <== current_params[EPOCHS][i];
    }

    // Carries no information a valid proof does not already carry -- every constraint above
    // held, or there would be no proof. Kept because it is part of the published public
    // signal layout.
    training_complete <== 1;
}

// LR_SCALE = 1e6, so a learning rate is given in millionths: 0.01 is 10000.
// LR_BITS = 20 covers LR_SCALE (2^20 = 1048576 > 1000000).
// GRAD_BITS = 20 allows gradients up to 1048575.
// PARAM_BITS = 40 allows scaled parameters up to ~1.1e12, i.e. real values up to ~1.1e6.
component main = ModularTrainingVerification(4, 3, 1000000, 20, 20, 40);
