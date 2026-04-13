# AITBC Production Environment

## 🏗️ Proper System Architecture

The AITBC production environment follows Linux Filesystem Hierarchy Standard (FHS) compliance:

### 📁 System Directory Structure

```
/etc/aitbc/                    # Production configurations
├── .env                       # Production environment variables
├── blockchain.env             # Blockchain service config
└── production/                # Production-specific configs

/opt/aitbc/services/           # Production service scripts
├── blockchain_http_launcher.py
├── blockchain_simple.py
├── marketplace.py
└── ...                        # Other service scripts

/var/lib/aitbc/                # Runtime data
├── data/                      # Blockchain databases
│   ├── blockchain/            # Blockchain data
│   ├── coordinator/           # Coordinator database
│   └── marketplace/           # Marketplace data
├── keystore/                  # Cryptographic keys (secure)
└── backups/                   # Production backups

/var/log/aitbc/                # Production logs
├── production/                # Production service logs
├── blockchain/                # Blockchain service logs
└── coordinator/               # Coordinator logs
```

### 🚀 Launching Production Services

Services are launched via systemd:

```bash
# Start blockchain node
systemctl start aitbc-blockchain-node

# Start blockchain RPC
systemctl start aitbc-blockchain-rpc

# Start coordinator API
systemctl start aitbc-agent-coordinator

# Check status
systemctl status aitbc-blockchain-node
```

### ⚙️ Configuration Management

Production configurations are stored in `/etc/aitbc/`:
- Environment variables in `.env`
- Blockchain config in `blockchain.env`
- Service-specific configs in production subdirectory

### 📊 Monitoring and Logs

Production logs are centralized in `/var/log/aitbc/`:
- Each service has its own log directory
- Logs rotate automatically
- Real-time monitoring available

Coordinator observability endpoints:
 - JSON metrics endpoint: `http://localhost:8000/v1/metrics`
 - Prometheus metrics endpoint: `http://localhost:8000/metrics`
 - Health endpoint: `http://localhost:8000/v1/health`
 - Web dashboard source: `/opt/aitbc/website/dashboards/metrics.html`

Current monitoring flow:
 - FastAPI request middleware records request counts, error counts, response time, and cache stats
 - `metrics.py` calculates live metric summaries and alert thresholds
 - `/v1/metrics` returns JSON for dashboard consumption
 - `/metrics` remains available for Prometheus-style scraping
 - Alert delivery uses webhook dispatch when `AITBC_ALERT_WEBHOOK_URL` is configured, otherwise alerts are logged locally

### 🔧 Maintenance

- **Backups**: Stored in `/var/lib/aitbc/backups/`
- **Updates**: Update code in `/opt/aitbc/`, restart services
- **Configuration**: Edit files in `/etc/aitbc/`

### 🛡️ Security

- All production files have proper permissions
- Keystore at `/var/lib/aitbc/keystore/` (secure, permissions 700)
- Environment variables are protected
- SSL certificates in `/etc/aitbc/production/certs/` (if used)

## 📋 Architecture Status

The AITBC production environment follows FHS compliance:
- ✅ Configurations in `/etc/aitbc/`
- ✅ Service scripts in `/opt/aitbc/services/`
- ✅ Runtime data in `/var/lib/aitbc/`
- ✅ Logs centralized in `/var/log/aitbc/`
- ✅ Repository clean of runtime files
- ✅ Proper FHS compliance achieved
