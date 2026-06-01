# GPU Resource Tracking Integration

Hermes agents can register and track GPU resources on-chain for immutable proof of compute availability.

## CLI Commands

- `aitbc gpu-onchain register <gpu_id> --miner-id <id> --model <model> --memory-gb <gb> --price-per-hour <price> --wallet <wallet>` - Register GPU
- `aitbc gpu-onchain query <gpu_id>` - Query GPU registration
- `aitbc gpu-onchain list --status <status>` - List all registered GPUs
- `aitbc gpu-onchain allocate <gpu_id> --client-id <address> --duration-hours <hours> --total-cost <cost> --wallet <wallet>` - Allocate GPU
- `aitbc gpu-onchain allocations <gpu_id>` - Query GPU allocations

## RPC Endpoints

- `POST /rpc/gpu/register` - Register GPU on-chain
- `GET /rpc/gpu/info/{gpu_id}` - Query GPU registration
- `GET /rpc/gpus` - List all registered GPUs
- `POST /rpc/gpu/allocate` - Allocate GPU to client
- `GET /rpc/gpu/allocations/{gpu_id}` - Query GPU allocations

## Usage Example

```bash
# Register a GPU on blockchain
aitbc gpu-onchain register GPU-ba5c6553-6396-ab66-5706-17e6de30a93a \
  --miner-id miner-001 \
  --model "RTX 4090" \
  --memory-gb 24 \
  --cuda-version "12.1" \
  --region "us-west" \
  --capabilities "cuda,ray,triton" \
  --price-per-hour 0.5 \
  --wallet my-agent-wallet

# Query GPU registration from blockchain
aitbc gpu-onchain query GPU-ba5c6553-6396-ab66-5706-17e6de30a93a

# List all registered GPUs
aitbc gpu-onchain list

# List only active GPUs
aitbc gpu-onchain list --status active

# Allocate GPU to a client
aitbc gpu-onchain allocate GPU-ba5c6553-6396-ab66-5706-17e6de30a93a \
  --client-id <client_wallet_address> \
  --duration-hours 24 \
  --total-cost 12.0 \
  --wallet my-agent-wallet

# Query GPU allocations
aitbc gpu-onchain allocations GPU-ba5c6553-6396-ab66-5706-17e6de30a93a
```

## Use Cases

- Immutable proof of GPU availability
- Track GPU allocation history
- Enable GPU marketplace with on-chain verification

## RPC Endpoint Testing

```bash
# Test GPU registration endpoint
curl -X POST http://hub.aitbc.bubuit.net:8006/rpc/gpu/register \
  -H "Content-Type: application/json" \
  -d '{"gpu_id": "GPU-test", "miner_id": "miner-001", "model": "RTX 4090", "memory_gb": 24, "price_per_hour": 0.5, "registered_by": "<wallet_address>", "chain_id": "ait-hub.aitbc.bubuit.net"}'

# Test GPU query endpoint
curl -X GET "http://hub.aitbc.bubuit.net:8006/rpc/gpu/info/GPU-test?chain_id=ait-hub.aitbc.bubuit.net"

# Test GPU list endpoint
curl -X GET "http://hub.aitbc.bubuit.net:8006/rpc/gpus?chain_id=ait-hub.aitbc.bubuit.net"
```

## Database Verification

```bash
# Check GPU registrations
SELECT * FROM gpu_registration WHERE gpu_id = 'GPU-ba5c6553-6396-ab66-5706-17e6de30a93a';

# Check GPU allocations
SELECT * FROM gpu_allocation WHERE gpu_id = 'GPU-ba5c6553-6396-ab66-5706-17e6de30a93a';
```
