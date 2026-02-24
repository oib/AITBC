# ZK Circuits Engine

## Overview

The ZK Circuits Engine provides zero-knowledge proof capabilities for privacy-preserving machine learning operations on the AITBC platform. It enables cryptographic verification of ML computations without revealing the underlying data or model parameters.

## Architecture

### Circuit Library
- **ml_inference_verification.circom**: Verifies neural network inference correctness
- **ml_training_verification.circom**: Verifies gradient descent training without revealing data
- **receipt_simple.circom**: Basic receipt verification (existing)

### Proof System
- **Groth16**: Primary proving system for efficiency
- **Trusted Setup**: Powers-of-tau ceremony for circuit-specific keys
- **Verification Keys**: Pre-computed for each circuit

## Circuit Details

### ML Inference Verification

```circom
pragma circom 2.0.0;

template MLInferenceVerification(INPUT_SIZE, HIDDEN_SIZE, OUTPUT_SIZE) {
    signal public input model_id;
    signal public input inference_id;
    signal public input expected_output[OUTPUT_SIZE];
    signal public input output_hash;

    signal private input inputs[INPUT_SIZE];
    signal private input weights1[HIDDEN_SIZE][INPUT_SIZE];
    signal private input biases1[HIDDEN_SIZE];
    signal private input weights2[OUTPUT_SIZE][HIDDEN_SIZE];
    signal private input biases2[OUTPUT_SIZE];

    signal private input inputs_hash;
    signal private input weights1_hash;
    signal private input biases1_hash;
    signal private input weights2_hash;
    signal private input biases2_hash;

    signal output verification_result;
    // ... neural network computation and verification
}
```

**Features:**
- Matrix multiplication verification
- ReLU activation function verification
- Hash-based privacy preservation
- Output correctness verification

### ML Training Verification

```circom
template GradientDescentStep(PARAM_COUNT) {
    signal input parameters[PARAM_COUNT];
    signal input gradients[PARAM_COUNT];
    signal input learning_rate;
    signal input parameters_hash;
    signal input gradients_hash;

    signal output new_parameters[PARAM_COUNT];
    signal output new_parameters_hash;
    // ... gradient descent computation
}
```

**Features:**
- Gradient descent verification
- Parameter update correctness
- Training data privacy preservation
- Convergence verification

## API Integration

### Proof Generation
```bash
POST /v1/ml-zk/prove/inference
{
  "inputs": {
    "model_id": "model_123",
    "inference_id": "inference_456",
    "expected_output": [2.5]
  },
  "private_inputs": {
    "inputs": [1, 2, 3, 4],
    "weights1": [0.1, 0.2, 0.3, 0.4],
    "biases1": [0.1, 0.2]
  }
}
```

### Proof Verification
```bash
POST /v1/ml-zk/verify/inference
{
  "proof": "...",
  "public_signals": [...],
  "verification_key": "..."
}
```

## Development Workflow

### Circuit Development
1. Write Circom circuit with templates
2. Compile with `circom circuit.circom --r1cs --wasm --sym --c -o build/`
3. Generate trusted setup with `snarkjs`
4. Export verification key
5. Integrate with ZKProofService

### Testing
- Unit tests for circuit compilation
- Integration tests for proof generation/verification
- Performance benchmarks for proof time
- Memory usage analysis

## Performance Characteristics

- **Circuit Compilation**: ~30-60 seconds
- **Proof Generation**: <2 seconds
- **Proof Verification**: <100ms
- **Circuit Size**: ~10-50KB compiled
- **Security Level**: 128-bit equivalent

## Security Considerations

- **Trusted Setup**: Powers-of-tau ceremony properly executed
- **Circuit Correctness**: Thorough mathematical verification
- **Input Validation**: Proper bounds checking on all signals
- **Side Channel Protection**: Constant-time operations where possible

## Future Enhancements

- **PLONK/STARK Integration**: Alternative proving systems
- **Recursive Proofs**: Proof composition for complex workflows
- **Hardware Acceleration**: GPU-accelerated proof generation
- **Multi-party Computation**: Distributed proof generation
