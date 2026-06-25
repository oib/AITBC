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

## cuInit Fails in Incus/LXC Container (Error 999)

**Symptoms:**
- `nvidia-smi` works inside the container
- `nvcc --version` works
- PyCUDA / CUDA runtime fails with `cuInit failed: unknown error` (error 999)
- Coordinator-api logs: `PyCUDA not available or no CUDA-capable device detected`

**Diagnosis:**
```bash
# nvidia-smi works (uses NVML, only needs /dev/nvidia0)
nvidia-smi

# But CUDA runtime fails (needs /dev/nvidia-uvm)
/opt/aitbc/venv/bin/python -c "import ctypes; cuda = ctypes.CDLL('libcuda.so.1'); print(f'cuInit: {cuda.cuInit(0)}')"

# Check for missing UVM device
ls -la /dev/nvidia-uvm*
# If missing, that's the problem
```

**Root cause:**
CUDA runtime requires the NVIDIA Unified Virtual Memory (UVM) device at `/dev/nvidia-uvm`.
`nvidia-smi` only needs NVML (`/dev/nvidia0`), so it works even when UVM is missing.
Incus/LXC containers need the UVM device explicitly passed through from the host.

**Solution (run on the HOST, not inside the container):**
```bash
# Find the container name
incus list

# Add the nvidia-uvm device to the container
incus config device add <container-name> nvidia-uvm unix-char \
    path=/dev/nvidia-uvm \
    major=236 minor=0 mode=666

incus config device add <container-name> nvidia-uvm-tools unix-char \
    path=/dev/nvidia-uvm-tools \
    major=236 minor=1 mode=666

# Restart the container (or restart the service that uses CUDA)
incus restart <container-name>
```

**Verify inside the container after restart:**
```bash
ls -la /dev/nvidia-uvm*
/opt/aitbc/venv/bin/python -c "
import pycuda.driver as cuda
cuda.init()
import pycuda.autoinit
print(f'GPU: {cuda.Device(0).name()}')
"
```

## See Also

- [Performance Issues](performance-issues.md) - Performance optimization
- [Service Management](service-management.md) - General service troubleshooting
- [Marketplace Issues](marketplace-issues.md) - GPU offer matching issues
