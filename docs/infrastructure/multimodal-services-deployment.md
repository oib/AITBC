# AITBC Multimodal Services Environment Configuration

## Overview

AITBC has two multimodal services optimized for different environments:

- **`aitbc-multimodal.service`** - CPU-only multimodal service (Port 8002)
- **`aitbc-multimodal-gpu.service`** - GPU-accelerated multimodal service (Port 8003)

## Environment-Specific Deployment

### AT1 (Localhost) Environment
**Required Service:** `aitbc-multimodal-gpu.service` only

```bash
# Deploy for AT1 (localhost)
./scripts/deploy/deploy-multimodal-services.sh at1
# or
./scripts/deploy/deploy-multimodal-services.sh localhost
```

**Configuration:**
- ✅ **GPU Service**: ENABLED (Port 8003)
- ❌ **CPU Service**: DISABLED (Port 8002)
- **Reasoning**: AT1 has GPU resources for development/testing

### Production Servers (aitbc, aitbc1)
**Required Service:** `aitbc-multimodal.service` only

```bash
# Deploy for production servers
./scripts/deploy/deploy-multimodal-services.sh server
# or
./scripts/deploy/deploy-multimodal-services.sh production
# or
./scripts/deploy/deploy-multimodal-services.sh aitbc
```

**Configuration:**
- ✅ **CPU Service**: ENABLED (Port 8002)
- ❌ **GPU Service**: DISABLED (Port 8003)
- **Reasoning**: Production servers optimized for CPU processing

## Service Differences

| Feature | aitbc-multimodal | aitbc-multimodal-gpu |
|---------|------------------|----------------------|
| **Port** | 8002 | 8003 |
| **GPU Support** | No | Yes |
| **Memory** | 2G | 4G |
| **CPU** | 200% | 300% |
| **Dependencies** | coordinator-api | coordinator-api + nvidia-persistenced |
| **Module** | `aitbc_multimodal.main` | `aitbc_gpu_multimodal.main` |
| **GPU Variables** | None | `CUDA_VISIBLE_DEVICES=0` |

## Deployment Script Usage

### Available Environments

```bash
# AT1/Localhost (GPU only)
./scripts/deploy/deploy-multimodal-services.sh at1
./scripts/deploy/deploy-multimodal-services.sh localhost

# Production Servers (CPU only)
./scripts/deploy/deploy-multimodal-services.sh server
./scripts/deploy/deploy-multimodal-services.sh production
./scripts/deploy/deploy-multimodal-services.sh aitbc
./scripts/deploy/deploy-multimodal-services.sh aitbc1

# Both services (for testing)
./scripts/deploy/deploy-multimodal-services.sh both
```

### Manual Deployment

If you need to manually configure services:

```bash
# For AT1 (localhost)
systemctl disable aitbc-multimodal.service
systemctl enable aitbc-multimodal-gpu.service

# For Production Servers
systemctl enable aitbc-multimodal.service
systemctl disable aitbc-multimodal-gpu.service
```

## Verification

Check service status after deployment:

```bash
# Check enabled services
systemctl list-units --type=service | grep -E "(aitbc-multimodal|aitbc-multimodal-gpu)"

# Check specific service
systemctl status aitbc-multimodal-gpu.service
systemctl status aitbc-multimodal.service
```

## Troubleshooting

### Service Not Found
```bash
# Ensure service files are copied to system directory
cp /home/oib/windsurf/aitbc/systemd/aitbc-*-multimodal.service /etc/systemd/system/
systemctl daemon-reload
```

### Port Conflicts
```bash
# Check port usage
sudo netstat -tlnp | grep -E ":(8002|8003)"
```

### GPU Service Issues
```bash
# Check NVIDIA drivers
nvidia-smi

# Check NVIDIA persistence service
systemctl status nvidia-persistenced.service
```

## Architecture Decision

This environment-specific configuration ensures:

1. **Resource Optimization**: AT1 leverages GPU capabilities for development
2. **Production Stability**: Servers use CPU-only processing for reliability
3. **Port Separation**: No conflicts between services
4. **Scalability**: Easy to scale based on environment needs
5. **Maintainability**: Clear separation of concerns

## Future Considerations

- **Auto-detection**: Script could auto-detect GPU availability
- **Dynamic switching**: Runtime switching between CPU/GPU modes
- **Load balancing**: Distribute requests based on service availability
- **Monitoring**: Add health checks for each service type
