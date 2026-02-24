# Edge GPU Setup Guide

## Overview
This guide covers setting up edge GPU optimization for consumer-grade hardware in the AITBC marketplace.

## Prerequisites

### Hardware Requirements
- NVIDIA GPU with compute capability 7.0+ (Turing architecture or newer)
- Minimum 6GB VRAM for edge optimization
- Linux operating system with NVIDIA drivers

### Software Requirements
- NVIDIA CUDA Toolkit 11.0+
- Ollama GPU inference engine
- Python 3.8+ with required packages

## Installation

### 1. Install NVIDIA Drivers
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nvidia-driver-470

# Verify installation
nvidia-smi
```

### 2. Install CUDA Toolkit
```bash
# Download and install CUDA
wget https://developer.download.nvidia.com/compute/cuda/11.8.0/local_installers/cuda_11.8.0_520.61.05_linux.run
sudo sh cuda_11.8.0_520.61.05_linux.run

# Add to PATH
echo 'export PATH=/usr/local/cuda/bin${PATH:+:${PATH}}' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}' >> ~/.bashrc
source ~/.bashrc
```

### 3. Install Ollama
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama
```

### 4. Configure GPU Miner
```bash
# Clone and setup AITBC
git clone https://github.com/aitbc/aitbc.git
cd aitbc

# Configure GPU miner
cp scripts/gpu/gpu_miner_host.py.example scripts/gpu/gpu_miner_host.py
# Edit configuration with your miner credentials
```

## Configuration

### Edge GPU Optimization Settings
```python
# In gpu_miner_host.py
EDGE_CONFIG = {
    "enable_edge_optimization": True,
    "geographic_region": "us-west",  # Your region
    "latency_target_ms": 50,
    "power_optimization": True,
    "thermal_management": True
}
```

### Ollama Model Selection
```bash
# Pull edge-optimized models
ollama pull llama2:7b  # ~4GB, good for edge
ollama pull mistral:7b # ~4GB, efficient

# List available models
ollama list
```

## Testing

### GPU Discovery Test
```bash
# Run GPU discovery
python scripts/gpu/gpu_miner_host.py --test-discovery

# Expected output:
# Discovered GPU: RTX 3060 (Ampere)
# Edge optimized: True
# Memory: 12GB
# Compatible models: llama2:7b, mistral:7b
```

### Latency Test
```bash
# Test geographic latency
python scripts/gpu/gpu_miner_host.py --test-latency us-east

# Expected output:
# Latency to us-east: 45ms
# Edge optimization: Enabled
```

### Inference Test
```bash
# Test ML inference
python scripts/gpu/gpu_miner_host.py --test-inference

# Expected output:
# Model: llama2:7b
# Inference time: 1.2s
# Edge optimized: True
# Privacy preserved: True
```

## Troubleshooting

### Common Issues

#### GPU Not Detected
```bash
# Check NVIDIA drivers
nvidia-smi

# Check CUDA installation
nvcc --version

# Reinstall drivers if needed
sudo apt purge nvidia*
sudo apt autoremove
sudo apt install nvidia-driver-470
```

#### High Latency
- Check network connection
- Verify geographic region setting
- Consider edge data center proximity

#### Memory Issues
- Reduce model size (use 7B instead of 13B)
- Enable memory optimization in Ollama
- Monitor GPU memory usage with nvidia-smi

#### Thermal Throttling
- Improve GPU cooling
- Reduce power consumption settings
- Enable thermal management in miner config

## Performance Optimization

### Memory Management
```python
# Optimize memory usage
OLLAMA_CONFIG = {
    "num_ctx": 1024,      # Reduced context for edge
    "num_batch": 256,     # Smaller batches
    "num_gpu": 1,         # Single GPU for edge
    "low_vram": True      # Enable low VRAM mode
}
```

### Network Optimization
```python
# Optimize for edge latency
NETWORK_CONFIG = {
    "use_websockets": True,
    "compression": True,
    "batch_size": 10,     # Smaller batches for lower latency
    "heartbeat_interval": 30
}
```

### Power Management
```python
# Power optimization settings
POWER_CONFIG = {
    "max_power_w": 200,   # Limit power consumption
    "thermal_target_c": 75,  # Target temperature
    "auto_shutdown": True    # Shutdown when idle
}
```

## Monitoring

### Performance Metrics
Monitor key metrics for edge optimization:
- GPU utilization (%)
- Memory usage (GB)
- Power consumption (W)
- Temperature (°C)
- Network latency (ms)
- Inference throughput (tokens/sec)

### Health Checks
```bash
# GPU health check
nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv

# Ollama health check
curl http://localhost:11434/api/tags

# Miner health check
python scripts/gpu/gpu_miner_host.py --health-check
```

## Security Considerations

### GPU Isolation
- Run GPU workloads in sandboxed environments
- Use NVIDIA MPS for multi-process isolation
- Implement resource limits per miner

### Network Security
- Use TLS encryption for all communications
- Implement API rate limiting
- Monitor for unauthorized access attempts

### Privacy Protection
- Ensure ZK proofs protect model inputs
- Use FHE for sensitive data processing
- Implement audit logging for all operations
