# FHE Service

## Overview

The Fully Homomorphic Encryption (FHE) Service enables encrypted computation on sensitive machine learning data within the AITBC platform. It allows ML inference to be performed on encrypted data without decryption, maintaining privacy throughout the computation process.

## Architecture

### FHE Providers
- **TenSEAL**: Primary provider for rapid prototyping and production use
- **Concrete ML**: Specialized provider for neural network inference
- **Abstract Interface**: Extensible provider system for future FHE libraries

### Encryption Schemes
- **CKKS**: Optimized for approximate computations (neural networks)
- **BFV**: Optimized for exact integer arithmetic
- **Concrete**: Specialized for neural network operations

## TenSEAL Integration

### Context Generation
```python
from app.services.fhe_service import FHEService

fhe_service = FHEService()
context = fhe_service.generate_fhe_context(
    scheme="ckks",
    provider="tenseal",
    poly_modulus_degree=8192,
    coeff_mod_bit_sizes=[60, 40, 40, 60]
)
```

### Data Encryption
```python
# Encrypt ML input data
encrypted_input = fhe_service.encrypt_ml_data(
    data=[[1.0, 2.0, 3.0, 4.0]],  # Input features
    context=context
)
```

### Encrypted Inference
```python
# Perform inference on encrypted data
model = {
    "weights": [[0.1, 0.2, 0.3, 0.4]],
    "biases": [0.5]
}

encrypted_result = fhe_service.encrypted_inference(
    model=model,
    encrypted_input=encrypted_input
)
```

## API Integration

### FHE Inference Endpoint
```bash
POST /v1/ml-zk/fhe/inference
{
  "scheme": "ckks",
  "provider": "tenseal",
  "input_data": [[1.0, 2.0, 3.0, 4.0]],
  "model": {
    "weights": [[0.1, 0.2, 0.3, 0.4]],
    "biases": [0.5]
  }
}

Response:
{
  "fhe_context_id": "ctx_123",
  "encrypted_result": "encrypted_hex_string",
  "result_shape": [1, 1],
  "computation_time_ms": 150
}
```

## Provider Details

### TenSEAL Provider
```python
class TenSEALProvider(FHEProvider):
    def generate_context(self, scheme: str, **kwargs) -> FHEContext:
        # CKKS context for neural networks
        context = ts.context(
            ts.SCHEME_TYPE.CKKS,
            poly_modulus_degree=8192,
            coeff_mod_bit_sizes=[60, 40, 40, 60]
        )
        context.global_scale = 2**40
        return FHEContext(...)

    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        ts_context = ts.context_from(context.public_key)
        encrypted_tensor = ts.ckks_tensor(ts_context, data)
        return EncryptedData(...)

    def encrypted_inference(self, model: Dict, encrypted_input: EncryptedData):
        # Perform encrypted matrix multiplication
        result = encrypted_input.dot(weights) + biases
        return result
```

### Concrete ML Provider
```python
class ConcreteMLProvider(FHEProvider):
    def __init__(self):
        import concrete.numpy as cnp
        self.cnp = cnp

    def generate_context(self, scheme: str, **kwargs) -> FHEContext:
        # Concrete ML context setup
        return FHEContext(scheme="concrete", ...)

    def encrypt(self, data: np.ndarray, context: FHEContext) -> EncryptedData:
        encrypted_circuit = self.cnp.encrypt(data, p=15)
        return EncryptedData(...)

    def encrypted_inference(self, model: Dict, encrypted_input: EncryptedData):
        # Neural network inference with Concrete ML
        return self.cnp.run(encrypted_input, model)
```

## Security Model

### Privacy Guarantees
- **Data Confidentiality**: Input data never decrypted during computation
- **Model Protection**: Model weights can be encrypted during inference
- **Output Privacy**: Results remain encrypted until client decryption
- **End-to-End Security**: No trusted third parties required

### Performance Characteristics
- **Encryption Time**: ~10-100ms per operation
- **Inference Time**: ~100-500ms (TenSEAL)
- **Accuracy**: Near-native performance for neural networks
- **Scalability**: Linear scaling with input size

## Use Cases

### Private ML Inference
```python
# Client encrypts sensitive medical data
encrypted_health_data = fhe_service.encrypt_ml_data(health_records, context)

# Server performs diagnosis without seeing patient data
encrypted_diagnosis = fhe_service.encrypted_inference(
    model=trained_model,
    encrypted_input=encrypted_health_data
)

# Client decrypts result locally
diagnosis = fhe_service.decrypt(encrypted_diagnosis, private_key)
```

### Federated Learning
- Multiple parties contribute encrypted model updates
- Coordinator aggregates updates without decryption
- Final model remains secure throughout process

### Secure Outsourcing
- Cloud providers perform computation on encrypted data
- No access to plaintext data or computation results
- Compliance with privacy regulations (GDPR, HIPAA)

## Development Workflow

### Testing FHE Operations
```python
def test_fhe_inference():
    # Setup FHE context
    context = fhe_service.generate_fhe_context(scheme="ckks")

    # Test data
    test_input = np.array([[1.0, 2.0, 3.0]])
    test_model = {"weights": [[0.1, 0.2, 0.3]], "biases": [0.1]}

    # Encrypt and compute
    encrypted = fhe_service.encrypt_ml_data(test_input, context)
    result = fhe_service.encrypted_inference(test_model, encrypted)

    # Verify result shape and properties
    assert result.shape == (1, 1)
    assert result.context == context
```

### Performance Benchmarking
```python
def benchmark_fhe_performance():
    import time

    # Benchmark encryption
    start = time.time()
    encrypted = fhe_service.encrypt_ml_data(data, context)
    encryption_time = time.time() - start

    # Benchmark inference
    start = time.time()
    result = fhe_service.encrypted_inference(model, encrypted)
    inference_time = time.time() - start

    return {
        "encryption_ms": encryption_time * 1000,
        "inference_ms": inference_time * 1000,
        "total_ms": (encryption_time + inference_time) * 1000
    }
```

## Deployment Considerations

### Resource Requirements
- **Memory**: 2-8GB RAM per concurrent FHE operation
- **CPU**: Multi-core support for parallel operations
- **Storage**: Minimal (contexts cached in memory)

### Scaling Strategies
- **Horizontal Scaling**: Multiple FHE service instances
- **Load Balancing**: Distribute FHE requests across nodes
- **Caching**: Reuse FHE contexts for repeated operations

### Monitoring
- **Latency Tracking**: End-to-end FHE operation timing
- **Error Rates**: FHE operation failure monitoring
- **Resource Usage**: Memory and CPU utilization metrics

## Future Enhancements

- **Hardware Acceleration**: FHE operations on specialized hardware
- **Advanced Schemes**: Integration with newer FHE schemes (TFHE, BGV)
- **Multi-Party FHE**: Secure computation across multiple parties
- **Hybrid Approaches**: Combine FHE with ZK proofs for optimal privacy-performance balance
