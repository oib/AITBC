# Quick Start

This guide provides the fastest way to install AITBC on a new host.

## One-Command Installation

Run this single command on any new host to install AITBC:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh)
```

## Manual Installation

Or clone and run manually:

```bash
git clone https://github.com/oib/aitbc.git /opt/aitbc
cd /opt/aitbc
chmod +x scripts/deployment/setup.sh
./scripts/deployment/setup.sh
```

**Note:** GitHub is the public repository. For internal development, use the Gitea repository instead.

## What the Setup Script Does

1. **Prerequisites Check**
   - Verifies Python 3.13.5+, pip3, git, systemd
   - Checks for root privileges

2. **Repository Setup**
   - Clones AITBC repository to `/opt/aitbc`
   - Handles multiple repository URLs for reliability

3. **Virtual Environments**
   - Creates Python venvs for each service
   - Installs dependencies from central requirements system
   - Uses profile-based installation via `install-profiles.sh`

4. **Runtime Directories**
   - Creates standard Linux directories:
     - `/var/lib/aitbc/keystore/` - Blockchain keys
     - `/var/lib/aitbc/data/` - Database files
     - `/var/lib/aitbc/logs/` - Application logs
     - `/etc/aitbc/` - Configuration files
   - Sets proper permissions and ownership

5. **PostgreSQL Databases**
   - Installs PostgreSQL if not present
   - Creates databases for all AITBC services
   - Creates dedicated users for each database
   - Grants necessary privileges

6. **Systemd Services**
   - Installs service files to `/etc/systemd/system/`
   - Enables auto-start on boot
   - Provides fallback manual startup

7. **Service Management**
   - Creates `/opt/aitbc/start-services.sh` for manual control
   - Sets up health monitoring
   - Configures logging

## Post-Installation

After running the setup script:

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh

# Restart all services
/opt/aitbc/start-services.sh

# View logs
tail -f /var/lib/aitbc/logs/aitbc-*.log
```

## See Also

- [Prerequisites](prerequisites.md)
- [Requirements Management](requirements-management.md)
- [Blockchain Setup](blockchain-setup.md)
