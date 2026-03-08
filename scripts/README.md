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
| 8001 | Coordinator API | Main API service |
| 8002 | Wallet Daemon | Wallet management |
| 8003 | Blockchain RPC | Blockchain node RPC |
| 8000 | Coordinator API (alt) | Alternative API |
| 8081 | Blockchain Node 1 | Blockchain instance |
| 8082 | Blockchain Node 2 | Blockchain instance |
| 8006 | Coordinator API (dev) | Development API |

## 🔍 Health Endpoints

The scripts test these health endpoints:
- `http://localhost:8001/health` - Coordinator API
- `http://localhost:8002/health` - Wallet Daemon  
- `http://localhost:8003/health` - Blockchain RPC

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
[SUCCESS] Coordinator API (port 8001): RUNNING
[SUCCESS] Wallet Daemon (port 8002): RUNNING
[WARNING] Blockchain RPC (port 8003): NOT RUNNING
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
