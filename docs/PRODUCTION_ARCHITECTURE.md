# AITBC Production Environment

## 🏗️ Proper System Architecture

The AITBC production environment follows Linux Filesystem Hierarchy Standard (FHS) compliance:

### 📁 System Directory Structure

```
/etc/aitbc/production/          # Production configurations
├── .env                       # Production environment variables
├── blockchain.py              # Blockchain service config
├── database.py                # Database configuration
├── services.py                # Services configuration
└── certs/                     # SSL certificates

/var/lib/aitbc/production/     # Production services and data
├── blockchain.py              # Production blockchain service
├── marketplace.py             # Production marketplace service
├── unified_marketplace.py     # Unified marketplace service
├── openclaw_ai.py             # OpenClaw AI service
└── backups/                   # Production backups

/var/log/aitbc/production/      # Production logs
├── blockchain/                # Blockchain service logs
├── marketplace/               # Marketplace service logs
└── unified_marketplace/       # Unified marketplace logs
```

### 🚀 Launching Production Services

Use the production launcher:

```bash
# Launch all production services
/opt/aitbc/scripts/production_launcher.py

# Launch individual service
python3 /var/lib/aitbc/production/blockchain.py
```

### ⚙️ Configuration Management

Production configurations are stored in `/etc/aitbc/production/`:
- Environment variables in `.env`
- Service-specific configs in Python modules
- SSL certificates in `certs/`

### 📊 Monitoring and Logs

Production logs are centralized in `/var/log/aitbc/production/`:
- Each service has its own log directory
- Logs rotate automatically
- Real-time monitoring available

### 🔧 Maintenance

- **Backups**: Stored in `/var/lib/aitbc/production/backups/`
- **Updates**: Update code in `/opt/aitbc/`, restart services
- **Configuration**: Edit files in `/etc/aitbc/production/`

### 🛡️ Security

- All production files have proper permissions
- Keystore remains at `/var/lib/aitbc/keystore/`
- Environment variables are protected
- SSL certificates secured in `/etc/aitbc/production/certs/`

## 📋 Migration Complete

The "box in box" structure has been eliminated:
- ✅ Configurations moved to `/etc/aitbc/production/`
- ✅ Services moved to `/var/lib/aitbc/production/`
- ✅ Logs centralized in `/var/log/aitbc/production/`
- ✅ Repository cleaned of production runtime files
- ✅ Proper FHS compliance achieved
