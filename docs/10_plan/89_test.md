# Cross-Container Marketplace Test Scenario
## Miner1 Registration & Client1 Discovery Test

### **Objective**
Test the complete marketplace workflow where:
1. **miner1** on localhost registers Ollama model services with marketplace on **aitbc**
2. **client1** on localhost discovers and can access miner1's offer via marketplace on **aitbc1**

### **Test Architecture**
```
┌─────────────────┐    HTTP/18000    ┌─────────────────┐    HTTP/18001    ┌─────────────────┐
│   localhost     │ ◄──────────────► │     aitbc       │ ◄──────────────► │     aitbc1      │
│  (miner1/client1)│   (Marketplace)   │  (Primary MP)   │   (Marketplace)   │ (Secondary MP)  │
│                 │                   │                 │                   │                 │
│ • miner1        │                   │ • Port 8000     │                   │ • Port 8000     │
│ • client1       │                   │ • Port 18000    │                   │ • Port 18001    │
│ • Ollama Models │                   │ • Redis Cache   │                   │ • Redis Cache   │
└─────────────────┘                   └─────────────────┘                   └─────────────────┘
```

### **Prerequisites**
- ✅ aitbc marketplace running on port 18000 (localhost proxy)
- ✅ aitbc1 marketplace running on port 18001 (localhost proxy)
- ✅ Ollama installed and running on localhost
- ✅ miner1 and client1 configurations available
- ✅ Geographic load balancer operational on port 8080

### **Test Phase 1: Miner1 Service Registration**

#### **1.1 Check Ollama Models Available**
```bash
# List available Ollama models on localhost
ollama list

# Expected models (updated based on actual environment):
# NAME                                     ID              SIZE      MODIFIED      
# lauchacarro/qwen2.5-translator:latest    0a947c33631d    986 MB    4 months ago     
# gemma3:1b                                8648f39daa8f    815 MB    11 months ago    
```

#### **1.2 Miner1 Registration Process**
```bash
# Set miner1 environment
export MINER_ID="miner1"
export MINER_WALLET="0x1234567890abcdef1234567890abcdef12345678"
export MINER_REGION="localhost"
export OLLAMA_BASE_URL="http://localhost:11434"

# Register miner1 with aitbc marketplace
aitbc marketplace gpu register \
  --miner-id $MINER_ID \
  --wallet $MINER_WALLET \
  --region $MINER_REGION \
  --gpu-model "NVIDIA-RTX-4060Ti" \
  --gpu-memory "16GB" \
  --compute-capability "8.9" \
  --price-per-hour "0.001" \
  --models "gemma3:1b,lauchacarro/qwen2.5-translator:latest" \
  --endpoint "http://localhost:11434" \
  --marketplace-url "http://127.0.0.1:18000"

# Expected response:
# {
#   "status": "success",
#   "miner_id": "miner1",
#   "registration_id": "reg_1234567890",
#   "marketplace": "aitbc",
#   "timestamp": "2026-02-26T12:44:00Z"
# }
```

#### **1.3 Verify Registration on aitbc**
```bash
# Check miner1 registration on aitbc marketplace
curl -s http://127.0.0.1:18000/v1/marketplace/offers | jq '.[] | select(.miner_id == "miner1")'

# Expected response:
# {
#   "miner_id": "miner1",
#   "wallet": "0x1234567890abcdef1234567890abcdef12345678",
#   "region": "localhost",
#   "gpu_model": "NVIDIA-RTX-4060Ti",
#   "gpu_memory": "16GB",
#   "compute_capability": "8.9",
#   "price_per_hour": "0.001",
#   "models": ["gemma3:1b", "lauchacarro/qwen2.5-translator:latest"],
#   "endpoint": "http://localhost:11434",
#   "status": "active",
#   "registered_at": "2026-02-26T12:44:00Z"
# }
```

### **Test Phase 2: Cross-Container Marketplace Synchronization**

#### **2.1 Check Synchronization to aitbc1**
```bash
# Wait for synchronization (typically 30-60 seconds)
sleep 45

# Check miner1 registration on aitbc1 marketplace
curl -s http://127.0.0.1:18001/v1/marketplace/offers | jq '.[] | select(.miner_id == "miner1")'

# Expected response should be identical to 1.3
```
