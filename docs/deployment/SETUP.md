# AITBC Setup Guide

## Quick Setup (New Host)

Run this single command on any new host to install AITBC:

```bash
sudo bash <(curl -sSL https://raw.githubusercontent.com/oib/aitbc/main/setup.sh)
```

Or clone and run manually:

```bash
sudo git clone https://gitea.bubuit.net/oib/aitbc.git /opt/aitbc
cd /opt/aitbc
sudo chmod +x setup.sh
sudo ./setup.sh
```

## What the Setup Script Does

1. **Prerequisites Check**
   - Verifies Python 3.13.5+, pip3, git, systemd
   - Checks for root privileges

2. **Repository Setup**
   - Clones AITBC repository to `/opt/aitbc`
   - Handles multiple repository URLs for reliability

3. **Virtual Environments**
   - Creates Python venvs for each service
   - Installs dependencies from `requirements.txt` when available
   - Falls back to core dependencies if requirements missing

4. **Runtime Directories**
   - Creates standard Linux directories:
     - `/var/lib/aitbc/keystore/` - Blockchain keys
     - `/var/lib/aitbc/data/` - Database files  
     - `/var/lib/aitbc/logs/` - Application logs
     - `/etc/aitbc/` - Configuration files
   - Sets proper permissions and ownership

5. **PostgreSQL Databases**
   - Installs PostgreSQL if not present
   - Creates databases: aitbc_coordinator, aitbc_exchange, aitbc_wallet, aitbc_marketplace, aitbc_governance, aitbc_trading, aitbc_gpu, aitbc_ai, aitbc_mempool
   - Creates dedicated users for each database
   - Grants necessary privileges
   - Uses centralized script: `/opt/aitbc/infra/scripts/setup_postgresql_databases.sh`

6. **Systemd Services**
   - Installs service files to `/etc/systemd/system/`
   - Enables auto-start on boot
   - Provides fallback manual startup

7. **Service Management**
   - Creates `/opt/aitbc/start-services.sh` for manual control
   - Creates `/opt/aitbc/health-check.sh` for monitoring
   - Sets up logging to `/var/log/aitbc-*.log`

## Runtime Directories

AITBC uses standard Linux system directories for runtime data:

```
/var/lib/aitbc/
├── keystore/     # Blockchain private keys (700 permissions)
├── data/         # Database files (.db, .sqlite)
└── logs/         # Application logs

/etc/aitbc/       # Configuration files
/var/log/aitbc/   # System logging (symlink)
```

### Security Notes
- **Keystore**: Restricted to root/aitbc user only
- **Data**: Writable by services, readable by admin
- **Logs**: Rotated automatically by logrotate

## Service Endpoints

| Service | Port | Health Endpoint |
|---------|------|----------------|
| Wallet API | 8003 | `http://localhost:8003/health` |
| Exchange API | 8001 | `http://localhost:8001/api/health` |
| Coordinator API | 8000 | `http://localhost:8000/health` |
| Blockchain RPC | 8545 | `http://localhost:8545` |

## Management Commands

```bash
# Check service health
/opt/aitbc/health-check.sh

# Restart all services
/opt/aitbc/start-services.sh

# View logs (new standard locations)
tail -f /var/lib/aitbc/logs/aitbc-wallet.log
tail -f /var/lib/aitbc/logs/aitbc-coordinator.log
tail -f /var/lib/aitbc/logs/aitbc-exchange.log

# Check keystore
ls -la /var/lib/aitbc/keystore/

# Systemd control
systemctl status aitbc-wallet
systemctl restart aitbc-coordinator-api
systemctl stop aitbc-exchange-api
```

## Troubleshooting

### Services Not Starting
1. Check logs: `tail -f /var/lib/aitbc/logs/aitbc-*.log`
2. Verify ports: `netstat -tlnp | grep ':800'`
3. Check processes: `ps aux | grep python`
4. Verify runtime directories: `ls -la /var/lib/aitbc/`

### Missing Dependencies
The setup script handles missing `requirements.txt` files by installing core dependencies:
- fastapi
- uvicorn
- pydantic
- httpx
- python-dotenv

### Port Conflicts
Services use these default ports. If conflicts exist:
1. Kill conflicting processes: `kill <pid>`
2. Modify service files to use different ports
3. Restart services

## Development Mode

For development with manual control:

```bash
cd /opt/aitbc/apps/wallet
source .venv/bin/activate
python simple_daemon.py

cd /opt/aitbc/apps/exchange
source .venv/bin/activate
python simple_exchange_api.py

cd /opt/aitbc/apps/coordinator-api/src
source ../.venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Production Considerations

For production deployment:
1. Configure proper environment variables
2. Set up reverse proxy (nginx)
3. Configure SSL certificates
4. Set up log rotation
5. Configure monitoring and alerts
6. Use proper database setup (PostgreSQL/Redis)
