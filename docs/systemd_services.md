# AITBC Systemd Services

All AITBC services are now managed by systemd for automatic startup, monitoring, and logging.

## Services Overview

| Service | Port | Description | Status |
|---------|------|-------------|--------|
| `aitbc-coordinator-api` | 8000 | Main Coordinator API for blockchain operations | Active |
| `aitbc-exchange-api` | 3003 | Exchange API for trading operations | Active |
| `aitbc-exchange-frontend` | 3002 | Exchange web frontend | Active |
| `aitbc-wallet` | 8001 | Wallet daemon service | Pending |
| `aitbc-node` | 8545 | Blockchain node service | Pending |

## Service Management

### Check Status
```bash
/root/aitbc/scripts/manage_services.sh status
```

### Start All Services
```bash
/root/aitbc/scripts/manage_services.sh start
```

### Stop All Services
```bash
/root/aitbc/scripts/manage_services.sh stop
```

### Restart All Services
```bash
/root/aitbc/scripts/manage_services.sh restart
```

### View Logs
```bash
# View specific service logs
/root/aitbc/scripts/manage_services.sh logs coordinator-api
/root/aitbc/scripts/manage_services.sh logs exchange-api
/root/aitbc/scripts/manage_services.sh logs exchange-frontend
/root/aitbc/scripts/manage_services.sh logs wallet
/root/aitbc/scripts/manage_services.sh logs node

# Or use systemctl directly
sudo journalctl -u aitbc-coordinator-api -f
sudo journalctl -u aitbc-exchange-api -f
sudo journalctl -u aitbc-exchange-frontend -f
```

### Enable/Disable Autostart
```bash
# Enable services to start on boot
/root/aitbc/scripts/manage_services.sh enable

# Disable services from starting on boot
/root/aitbc/scripts/manage_services.sh disable
```

## Individual Service Control

You can also control services individually using systemctl:

```bash
# Start a specific service
sudo systemctl start aitbc-coordinator-api

# Stop a specific service
sudo systemctl stop aitbc-coordinator-api

# Restart a specific service
sudo systemctl restart aitbc-coordinator-api

# Check if service is enabled
sudo systemctl is-enabled aitbc-coordinator-api

# Enable service on boot
sudo systemctl enable aitbc-coordinator-api

# Disable service on boot
sudo systemctl disable aitbc-coordinator-api
```

## Service Files Location

Service definition files are located at:
- `/etc/systemd/system/aitbc-coordinator-api.service`
- `/etc/systemd/system/aitbc-exchange-api.service`
- `/etc/systemd/system/aitbc-exchange-frontend.service`
- `/etc/systemd/system/aitbc-wallet.service`
- `/etc/systemd/system/aitbc-node.service`

## Troubleshooting

### Service Not Starting
1. Check the service status: `sudo systemctl status aitbc-service-name`
2. View the logs: `sudo journalctl -u aitbc-service-name -n 50`
3. Check if port is already in use: `netstat -tlnp | grep :port`

### Service Keeps Restarting
1. The service is configured to auto-restart on failure
2. Check logs for the error causing failures
3. Temporarily disable auto-restart for debugging: `sudo systemctl stop aitbc-service-name`

### Manual Override
If systemd services are not working, you can run services manually:
```bash
# Coordinator API
cd /root/aitbc/apps/coordinator-api
/root/aitbc/.venv/bin/python -m uvicorn src.app.main:app --host 0.0.0.0 --port 8000

# Exchange API
cd /root/aitbc/apps/trade-exchange
/root/aitbc/.venv/bin/python simple_exchange_api.py

# Exchange Frontend
cd /root/aitbc/apps/trade-exchange
/root/aitbc/.venv/bin/python server.py --port 3002
```

## Benefits of Systemd

1. **Automatic Startup**: Services start automatically on boot
2. **Automatic Restart**: Services restart on failure
3. **Centralized Logging**: All logs go to journald
4. **Resource Management**: Systemd manages service resources
5. **Dependency Management**: Services can depend on each other
6. **Security**: Services run with specified user/group permissions
