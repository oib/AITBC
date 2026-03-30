# AITBC Development Environment Scripts

This directory contains scripts for managing the AITBC development environment, including incus containers and systemd services.

## 📋 Available Scripts

### 🔧 `start-aitbc-dev.sh`
Starts incus containers and AITBC systemd services on localhost.

**Features:**
- Starts incus containers: `aitbc` and `aitbc1`
- Starts all local systemd services matching `aitbc-*`
- Checks service health and port status
- Tests health endpoints
- Provides colored output and status reporting

**Usage:**
```bash
./scripts/start-aitbc-dev.sh
```

### 🛑 `stop-aitbc-dev.sh`
Stops incus containers and AITBC systemd services on localhost.

**Features:**
- Stops incus containers: `aitbc` and `aitbc1`
- Stops all local systemd services matching `aitbc-*`
- Verifies services are stopped
- Provides colored output and status reporting

**Usage:**
```bash
./scripts/stop-aitbc-dev.sh
```

### 🚀 `start-aitbc-full.sh`
Comprehensive startup script for the complete AITBC development environment.

**Features:**
- Starts incus containers: `aitbc` and `aitbc1`
- Starts services inside containers
- Starts all local systemd services matching `aitbc-*`
- Tests connectivity to container services
- Provides detailed status reporting
- Shows container IP addresses
- Tests health endpoints

**Services Started:**
- **Local Services:** All `aitbc-*` systemd services
- **Container Services:** 
  - `aitbc-coordinator-api`
  - `aitbc-wallet-daemon`
  - `aitbc-blockchain-node`

**Usage:**
```bash
./scripts/start-aitbc-full.sh
```

## 🎯 Prerequisites

### Required Commands:
- `incus` - Container management
- `systemctl` - Systemd service management
- `curl` - Health endpoint testing
- `netstat` - Port checking

### Required Containers:
The scripts expect these incus containers to exist:
- `aitbc`
- `aitbc1`

### Required Services:
The scripts look for systemd services matching the pattern `aitbc-*`.

## 📊 Service Ports

| Port | Service | Description |
|------|---------|-------------|
| 8000 | Coordinator API | Main API service |
| 8001 | Exchange API | Trading functionality |
| 8002 | Marketplace API | GPU compute marketplace |
| 8003 | Wallet API | Digital wallet management |
| 8004 | Explorer | Blockchain explorer |
| 8006 | Blockchain RPC | Blockchain node RPC |
| 8007 | Web UI | Web user interface |
| 8010 | GPU Service | GPU-accelerated processing |
| 8011 | Learning Service | Machine learning |
| 8012 | Agent Coordinator | Agent orchestration |
| 8013 | Agent Registry | Agent registration |
| 8014 | OpenClaw Service | Edge computing |
| 8015 | AI Service | Advanced AI capabilities |
| 8020 | Multimodal Service | Multi-modal processing |
| 8021 | Modality Optimization | Modality optimization |
| 8081 | Blockchain Node 1 | Blockchain instance |
| 8082 | Blockchain Node 2 | Blockchain instance |
| 8006 | Coordinator API (dev) | Development API |

## 🔍 Health Endpoints

The scripts test these health endpoints:
- `http://localhost:8000/health` - Coordinator API
- `http://localhost:8001/api/health` - Exchange API
- `http://localhost:8002/health` - Marketplace API
- `http://localhost:8003/health` - Wallet API
- `http://localhost:8004/health` - Explorer
- `http://localhost:8007/` - Web UI
- `http://localhost:8010/health` - GPU Service
- `http://localhost:8011/health` - Learning Service
- `http://localhost:8012/health` - Agent Coordinator
- `http://localhost:8013/health` - Agent Registry
- `http://localhost:8014/health` - OpenClaw Service
- `http://localhost:8015/health` - AI Service
- `http://localhost:8020/health` - Multimodal Service
- `http://localhost:8021/health` - Modality Optimization

## 📝 Output Examples

### Success Output:
```
[INFO] Starting AITBC Development Environment...
[INFO] Starting incus containers...
[SUCCESS] Container aitbc started successfully
[SUCCESS] Container aitbc1 started successfully
[INFO] Starting AITBC systemd services on localhost...
[SUCCESS] Service aitbc-coordinator-api started successfully
[SUCCESS] Service aitbc-wallet-daemon started successfully
[INFO] Checking service status...
[SUCCESS] aitbc-coordinator-api: RUNNING
[SUCCESS] aitbc-wallet-daemon: RUNNING
[SUCCESS] AITBC Development Environment startup complete!
```

### Service Status:
```
[INFO] Checking AITBC service ports...
[SUCCESS] Coordinator API (port 8000): RUNNING
[SUCCESS] Exchange API (port 8001): RUNNING
[SUCCESS] Marketplace API (port 8002): RUNNING
[SUCCESS] Wallet API (port 8003): RUNNING
[SUCCESS] Explorer (port 8004): RUNNING
[SUCCESS] Blockchain RPC (port 8006): RUNNING
[SUCCESS] Web UI (port 8007): RUNNING
[SUCCESS] GPU Service (port 8010): RUNNING
[SUCCESS] Learning Service (port 8011): RUNNING
[SUCCESS] Agent Coordinator (port 8012): RUNNING
[SUCCESS] Agent Registry (port 8013): RUNNING
[SUCCESS] OpenClaw Service (port 8014): RUNNING
[SUCCESS] AI Service (port 8015): RUNNING
[SUCCESS] Multimodal Service (port 8020): RUNNING
[SUCCESS] Modality Optimization (port 8021): RUNNING
```

## 🛠️ Troubleshooting

### Common Issues:

1. **Container not found:**
   ```
   [ERROR] Container aitbc not found. Please create it first.
   ```
   **Solution:** Create the incus containers first:
   ```bash
   incus launch images:ubuntu/22.04 aitbc
   incus launch images:ubuntu/22.04 aitbc1
   ```

2. **Service not found:**
   ```
   [WARNING] No AITBC services found on localhost
   ```
   **Solution:** Install AITBC services or check if they're named correctly.

3. **Port already in use:**
   ```
   [WARNING] Service aitbc-coordinator-api is already running
   ```
   **Solution:** This is normal - the script detects already running services.

4. **Permission denied:**
   ```
   [ERROR] Failed to start service aitbc-coordinator-api
   ```
   **Solution:** Run with sudo or check user permissions.

### Debug Commands:

```bash
# Check all AITBC services
systemctl list-units | grep aitbc-

# Check container status
incus list

# View service logs
journalctl -f -u aitbc-coordinator-api

# View container logs
incus exec aitbc -- journalctl -f -u aitbc-coordinator-api

# Check port usage
netstat -tlnp | grep :800
```

## 🔄 Workflow

### Development Setup:
1. Create incus containers (if not exists)
2. Install AITBC services in containers
3. Install AITBC systemd services locally
4. Run `./scripts/start-aitbc-full.sh`

### Daily Development:
1. `./scripts/start-aitbc-full.sh` - Start everything
2. Work on AITBC development
3. `./scripts/stop-aitbc-dev.sh` - Stop when done

### Testing:
1. Start services with scripts
2. Test health endpoints
3. Check logs for issues
4. Stop services when finished

## 📚 Additional Information

- **Container IPs:** Scripts show container IP addresses for direct access
- **Health Checks:** Automatic health endpoint testing
- **Service Status:** Real-time status reporting
- **Error Handling:** Graceful error handling with informative messages

## 🎯 Best Practices

1. **Use the full script** for complete environment setup
2. **Check the output** for any warnings or errors
3. **Monitor logs** when troubleshooting issues
4. **Stop services** when not in use to conserve resources
5. **Run scripts from the project root** for proper path resolution
