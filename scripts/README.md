# AITBC Development Environment Scripts

This directory contains scripts for managing the AITBC development environment, including incus containers and systemd services.

## 📋 Available Scripts

### 🔧 `start-aitbc-dev.sh`
Starts incus containers and AITBC systemd services on localhost.

**Features:**
- Starts incus containers: `aitbc` and `<node1>`
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
- Stops incus containers: `aitbc` and `<node1>`
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
- Starts incus containers: `aitbc` and `<node1>`
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
- `<node1>`

### Required Services:
The scripts look for systemd services matching the pattern `aitbc-*`.

## 📊 Service Ports

> **Note:** For authoritative port configuration, see [Service Ports Reference](../docs/reference/SERVICE_PORTS.md).

| Port | Service | Description |
|------|---------|-------------|
| 8201 | API Gateway | Customer-facing API entry point |
| 8202 | Blockchain RPC | Blockchain node RPC |
| 8203 | Coordinator API | Job/marketplace/escrow failover endpoint |
| 8100 | Blockchain Explorer API | Block/transaction search |
| 8101 | GPU Service | GPU compute service |
| 8102 | Marketplace Service | GPU compute marketplace |
| 8104 | Trading Service | Trading engine |
| 8105 | Governance Service | Governance API |
| 8106 | Exchange API | Trading functionality |
| 8107 | Agent Coordinator | Agent messaging coordinator |
| 8108 | Wallet Daemon | Digital wallet management |
| 8110 | Whisper Service | Whisper messaging |
| 8111 | Edge Service | Edge compute and dispatch |
| 7070 | Blockchain P2P | Peer-to-peer gossip relay |
| 8210 | Pool Hub | Pool hub API |
| 8230 | FFmpeg Service | FFmpeg processing |
| 8205 | Blockchain Event Bridge | Chain event streaming |
| 8002 | Monitoring Service | Metrics collection |
| 8005 | AI Engine | AI inference engine |
| 8012 | Adaptive Learning | Learning service |
| 8020 | Multi-Modal Agent | Multi-modal AI agent |
| 8021 | Modality Optimization | Modality optimization service |
| 8270 | Hermes Agent | Hermes agent service |

## 🔍 Health Endpoints

The scripts test these health endpoints:
- `http://localhost:8203/health` - Coordinator API
- `http://localhost:8106/api/health` - Exchange API
- `http://localhost:8102/health` - Marketplace API
- `http://localhost:8108/health` - Wallet API
- `http://localhost:8202/health` - Blockchain RPC

## 📝 Output Examples

### Success Output:
```
[INFO] Starting AITBC Development Environment...
[INFO] Starting incus containers...
[SUCCESS] Container aitbc started successfully
[SUCCESS] Container <node1> started successfully
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
[SUCCESS] API Gateway (port 8201): RUNNING
[SUCCESS] Blockchain RPC (port 8202): RUNNING
[SUCCESS] Coordinator API (port 8203): RUNNING
[SUCCESS] Blockchain Explorer API (port 8100): RUNNING
[SUCCESS] GPU Service (port 8101): RUNNING
[SUCCESS] Marketplace Service (port 8102): RUNNING
[SUCCESS] Trading Service (port 8104): RUNNING
[SUCCESS] Governance Service (port 8105): RUNNING
[SUCCESS] Exchange API (port 8106): RUNNING
[SUCCESS] Agent Coordinator (port 8107): RUNNING
[SUCCESS] Wallet Daemon (port 8108): RUNNING
[SUCCESS] Whisper Service (port 8110): RUNNING
[SUCCESS] Edge Service (port 8111): RUNNING
[SUCCESS] Blockchain P2P (port 7070): RUNNING
[SUCCESS] Pool Hub (port 8210): RUNNING
[SUCCESS] FFmpeg Service (port 8230): RUNNING
[SUCCESS] Blockchain Event Bridge (port 8205): RUNNING
[SUCCESS] Monitoring Service (port 8002): RUNNING
[SUCCESS] AI Engine (port 8005): RUNNING
[SUCCESS] Adaptive Learning (port 8012): RUNNING
[SUCCESS] Multi-Modal Agent (port 8020): RUNNING
[SUCCESS] Modality Optimization (port 8021): RUNNING
[SUCCESS] Hermes Agent (port 8270): RUNNING
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
   incus launch images:ubuntu/22.04 <node1>
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

## Environment variables

The scripts in this tree take fleet addresses, service endpoints and deployment
targets from `AITBC_*` environment variables rather than hardcoded hosts. See
[docs/deployment/script-environment.md](../docs/deployment/script-environment.md).
