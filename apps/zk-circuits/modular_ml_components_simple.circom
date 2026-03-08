pragma circom 2.0.0;

template ParameterUpdate() {
    signal input current_param;
    signal input gradient;
    signal input learning_rate;
    signal output new_param;
    new_param <== current_param - learning_rate * gradient;
}

template VectorParameterUpdate(PARAM_COUNT) {
    signal input current_params[PARAM_COUNT];
    signal input gradients[PARAM_COUNT];
    signal input learning_rate;
    signal output new_params[PARAM_COUNT];
    component updates[PARAM_COUNT];
    for (var i = 0; i < PARAM_COUNT; i++) {
        updates[i] = ParameterUpdate();
        updates[i].current_param <== current_params[i];
        updates[i].gradient <== gradients[i];
        updates[i].learning_rate <== learning_rate;
        new_params[i] <== updates[i].new_param;
    }
}

template LossConstraint() {
    signal input predicted_loss;
    signal input actual_loss;
    signal input tolerance;
    signal diff;
    diff <== predicted_loss - actual_loss;
    signal diff_squared;
    diff_squared <== diff * diff;
    signal tolerance_squared;
    tolerance_squared <== tolerance * tolerance;
    diff_squared * (1 - diff_squared / tolerance_squared) === 0;
}

template LearningRateValidation() {
    signal input learning_rate;
}

template TrainingEpoch(PARAM_COUNT) {
    signal input epoch_params[PARAM_COUNT];
    signal input epoch_gradients[PARAM_COUNT];
    signal input learning_rate;
    signal output next_epoch_params[PARAM_COUNT];
    component param_update = VectorParameterUpdate(PARAM_COUNT);
    param_update.current_params <== epoch_params;
    param_update.gradients <== epoch_gradients;
    param_update.learning_rate <== learning_rate;
    next_epoch_params <== param_update.new_params;
}

template ModularTrainingVerification(PARAM_COUNT, EPOCHS) {
    signal input initial_parameters[PARAM_COUNT];
    signal input learning_rate;
    signal output final_parameters[PARAM_COUNT];
    signal output training_complete;
    component lr_validator = LearningRateValidation();
    lr_validator.learning_rate <== learning_rate;
    signal current_params[EPOCHS + 1][PARAM_COUNT];
    for (var i = 0; i < PARAM_COUNT; i++) {
        current_params[0][i] <== initial_parameters[i];
    }
    component epochs[EPOCHS];
    for (var e = 0; e < EPOCHS; e++) {
        epochs[e] = TrainingEpoch(PARAM_COUNT);
        for (var i = 0; i < PARAM_COUNT; i++) {
            epochs[e].epoch_params[i] <== current_params[e][i];
        }
        for (var i = 0; i < PARAM_COUNT; i++) {
            epochs[e].epoch_gradients[i] <== 1;
        }
        epochs[e].learning_rate <== learning_rate;
        for (var i = 0; i < PARAM_COUNT; i++) {
            current_params[e + 1][i] <== epochs[e].next_epoch_params[i];
        }
    }
    for (var i = 0; i < PARAM_COUNT; i++) {
        final_parameters[i] <== current_params[EPOCHS][i];
    }
    training_complete <== 1;
}

component main = ModularTrainingVerification(4, 3);
