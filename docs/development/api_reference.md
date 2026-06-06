# API Reference - Edge Computing & ML Features

## Edge GPU Endpoints

### GET /v1/marketplace/edge-gpu/profiles
Get consumer GPU profiles with filtering options.

**Query Parameters:**
- `architecture` (optional): Filter by GPU architecture (turing, ampere, ada_lovelace)
- `edge_optimized` (optional): Filter for edge-optimized GPUs
- `min_memory_gb` (optional): Minimum memory requirement

**Response:**
```json
{
  "profiles": [
    {
      "id": "cgp_abc123",
      "gpu_model": "RTX 3060",
      "architecture": "ampere",
      "consumer_grade": true,
      "edge_optimized": true,
      "memory_gb": 12,
      "power_consumption_w": 170,
      "edge_premium_multiplier": 1.0
    }
  ],
  "count": 1
}
```

### POST /v1/marketplace/edge-gpu/scan/{miner_id}
Scan and register edge GPUs for a miner.

**Response:**
```json
{
  "miner_id": "miner_123",
  "gpus_discovered": 2,
  "gpus_registered": 2,
  "edge_optimized": 1
}
```

### GET /v1/marketplace/edge-gpu/metrics/{gpu_id}
Get real-time edge GPU performance metrics.

**Query Parameters:**
- `hours` (optional): Time range in hours (default: 24)

### POST /v1/marketplace/edge-gpu/optimize/inference/{gpu_id}
Optimize ML inference request for edge GPU.

## ML ZK Proof Endpoints

### POST /v1/ml-zk/prove/inference
Generate ZK proof for ML inference correctness.

**Request:**
```json
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

### POST /v1/ml-zk/verify/inference
Verify ZK proof for ML inference.

### POST /v1/ml-zk/fhe/inference
Perform ML inference on encrypted data using FHE.

**Request:**
```json
{
  "scheme": "ckks",
  "provider": "tenseal",
  "input_data": [[1.0, 2.0, 3.0, 4.0]],
  "model": {
    "weights": [[0.1, 0.2, 0.3, 0.4]],
    "biases": [0.5]
  }
}
```

### GET /v1/ml-zk/circuits
List available ML ZK circuits.

## Error Codes

### Edge GPU Errors
- `400`: Invalid GPU parameters
- `404`: GPU not found
- `500`: GPU discovery failed

### ML ZK Errors
- `400`: Invalid proof parameters
- `404`: Circuit not found
- `500`: Proof generation/verification failed
