# GPU Issues

This guide covers GPU problems including detection issues, CUDA errors, and memory problems.

## GPU Not Detected

**Symptoms:**
- GPU not recognized
- CUDA errors
- Mining fails

**Diagnosis:**
```bash
# Check GPU
nvidia-smi

# Check CUDA
nvcc --version

# Check driver
dmesg | grep -i nvidia
```

**Solutions:**
1. Reinstall NVIDIA driver
```bash
# Remove old driver
apt remove nvidia-* --purge

# Install new driver
apt install nvidia-driver-535

# Reboot
reboot
```

2. Check CUDA installation
```bash
# Verify CUDA installation
nvcc --version

# Reinstall CUDA if needed
apt install nvidia-cuda-toolkit
```

3. Check GPU permissions
```bash
# Add user to video group
usermod -aG video $USER

# Reboot
reboot
```

## GPU Memory Errors

**Symptoms:**
- Out of memory errors
- CUDA out of memory
- Jobs failing

**Diagnosis:**
```bash
# Check GPU memory
nvidia-smi

# Monitor memory usage
watch -n 1 nvidia-smi
```

**Solutions:**
1. Reduce batch size
```python
# Reduce batch size in job configuration
batch_size = 8  # Reduce from 16
```

2. Clear GPU cache
```python
import torch
torch.cuda.empty_cache()
```

3. Restart mining service
```bash
systemctl restart aitbc-miner
```

## See Also

- [Performance Issues](performance-issues.md) - Performance optimization
- [Service Management](service-management.md) - General service troubleshooting
- [Marketplace Issues](marketplace-issues.md) - GPU offer matching issues
