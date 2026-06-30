# AITBC Setup - Reference

**Last Updated**: 2026-06-30
**Version**: 1.0

## Essential Links

### Installation
- [Prerequisites](installation/prerequisites.md) - System and software requirements
- [Quick Start](installation/quick-start.md) - One-command installation
- [Installation](installation/installation.md) - Monorepo installation
- [Requirements Management](installation/requirements-management.md) - Dependency profiles

### Node Onboarding
- [Blockchain Setup](node/blockchain-setup.md) - Configure blockchain node
- [Agent Messaging](node/agent-messaging.md) - PING/PONG messaging
- [Coin Requests](node/coin-requests.md) - Request free coins from hub
- [Configuration Guide](node/configuration-guide.md) - Configuration files

### Mining
- [Miner Quick Start](mining/miner-quick-start.md) - Register GPU and earn tokens

### Platform Overview
- [Introduction](overview/introduction.md) - What is AITBC
- [CLI Guide](overview/cli-guide.md) - CLI setup and usage
- [Enhanced Services](overview/enhanced-services.md) - Enhanced services guide

### Reference
- [Service Endpoints](reference/service-endpoints.md) - Port configuration
- [Management Commands](reference/management-commands.md) - Service control
- [Troubleshooting](reference/troubleshooting.md) - Common issues
- [Security Notes](reference/security-notes.md) - Security best practices
- [Production Deployment](reference/production-deployment.md) - Production checklist
- [Service Isolation](../operations/SERVICE_ISOLATION_2026-06-07.md) - Service user security configuration

### Open Island

#### Join an Open Island as Follower

To join an existing AITBC hub (e.g., `https://hub.aitbc.bubuit.net`) as a follower node:

```bash
# 1. Clone the repository
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# 2. Download hub configuration
mkdir -p /etc/aitbc
curl https://hub.aitbc.bubuit.net/agent/blockchain.env -o /etc/aitbc/blockchain.env
curl https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env -o /etc/aitbc/blockchain-secrets.env
chmod 600 /etc/aitbc/blockchain-secrets.env

# 3. Configure node identity
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
# Edit NODE_ID in /etc/aitbc/node.env to a unique value for your node

# 4. Run setup script (non-interactive mode)
./scripts/deployment/setup.sh --open-island https://hub.aitbc.bubuit.net --node-id your-node-id

# 5. Start blockchain node (follower only needs blockchain-node, not blockchain-p2p)
systemctl start aitbc-blockchain-node
systemctl enable aitbc-blockchain-node
systemctl status aitbc-blockchain-node
```

The node will automatically:
- Connect to the hub's RPC URL (`default_peer_rpc_url` from `blockchain.env`)
- Register a subscription lease via `POST /rpc/subscribe`
- Receive blocks via WebSocket push (`wss://hub/rpc/subscribe/ws`)
- Send periodic heartbeats to maintain the lease
- Fall back to periodic pull sync if subscription fails
- Join the island with the configured `CHAIN_ID`

> **Note:** Followers do **not** need to start `aitbc-blockchain-p2p`. That service is hub-only.

#### Verify Sync Status

```bash
# Check subscription status
journalctl -u aitbc-blockchain-node -f | grep -i "subscribe\|lease\|websocket\|Sync mode"

# View imported blocks
journalctl -u aitbc-blockchain-node | grep "Imported block"

# Check local node height vs hub
curl -s http://localhost:8202/rpc/head | jq .height
curl -s https://hub.aitbc.bubuit.net/rpc/head | jq .height
```

- [Open Island Testing](open-island.md) - Join hub.aitbc.bubuit.net

## Common Commands

```bash
# Check service health
/opt/aitbc/scripts/monitoring/health_check.sh

# Restart all services
/opt/aitbc/start-services.sh

# View logs
tail -f /var/lib/aitbc/logs/aitbc-*.log

# Systemd control
systemctl status aitbc-blockchain-node
systemctl restart aitbc-coordinator-api

# AITBC CLI (marketplace, wallet, blockchain operations)
aitbc market list          # List marketplace offers
aitbc wallet balance       # Check wallet balance
aitbc blockchain status    # Check blockchain status
aitbc --help               # Show all CLI commands
```

## Updating an Existing Node

After the initial `setup.sh` run, use `update.sh` to safely apply new code changes. It backs up, pulls, syncs the venv, relinks systemd, restarts services, and runs a health check.

```bash
sudo /opt/aitbc/scripts/deployment/update.sh
```

For flags (`--no-pull`, `--no-restart`, `--skip-backup`), step-by-step details, rollback procedures, and troubleshooting, see [UPDATE.md](./UPDATE.md).

### Re-running setup on an existing node

If you run `setup.sh` on a node that is already installed (detected by the presence of `/etc/aitbc/node.env` and `/opt/aitbc/venv`), it automatically forwards to `update.sh` instead of re-running the full first-time install. This prevents accidental re-initialization of databases, credentials, and node identity.

To force a full re-run (e.g. to repair a broken install), use `--force`:

```bash
sudo /opt/aitbc/scripts/deployment/setup.sh --force
```

## Scenarios

For comprehensive AITBC capabilities and use cases, see [Scenarios Documentation](../scenarios/).

## See Also

- [README](../README.md) - Main documentation index
- [Deployment](../deployment/) - Production deployment guides
- [Incus Port Forwarding](../deployment/incus-port-forwarding.md) - Container port configuration
- [Firehol Configuration](../deployment/firehol-configuration.md) - Firewall configuration
- [Nginx Setup](../deployment/nginx-setup.md) - Nginx reverse proxy configuration
- [Service Ports Reference](../reference/SERVICE_PORTS.md) - Complete port configuration

## Troubleshooting

### Common Setup Issues

#### ModuleNotFoundError: No module named 'pydantic-settings'

`pydantic-settings` is a core dependency (required by multiple apps including coordinator-api and blockchain-node). It is included in `requirements.txt` since v0.4.26. If you see this error, reinstall dependencies:

```bash
cd /opt/aitbc
source venv/bin/activate
pip install -r requirements.txt
systemctl restart aitbc-coordinator-api aitbc-blockchain-node
```

#### PermissionError: Permission denied on /var/lib/aitbc/data

The blockchain-node service runs as `aitbc-blockchain` user and needs write access to data directories.

```bash
# Fix permissions
chown -R aitbc-blockchain:aitbc-services /var/lib/aitbc/data
systemctl restart aitbc-blockchain-node
```

#### Service fails to start: Unable to locate executable '/opt/aitbc/venv/bin/python'

The virtual environment may not exist or was corrupted.

```bash
# Recreate virtual environment
rm -rf /opt/aitbc/venv
cd /opt/aitbc
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
systemctl restart aitbc-blockchain-node
```

#### Service user does not exist

Service users are created by the setup script. If they're missing:

```bash
# Create service users manually
groupadd aitbc-services
useradd -r -s /bin/false -g aitbc-services aitbc-blockchain
useradd -r -s /bin/false -g aitbc-services aitbc-public
useradd -r -s /bin/false -g aitbc-services aitbc-internal
useradd -r -s /bin/false -g aitbc-services aitbc-gpu
useradd -r -s /bin/false -g aitbc-services aitbc-wallet
```

#### Sync mode: pull (periodic, WebSocket push unavailable)

The node is using pull sync instead of push sync. This is normal for follower nodes and will work correctly.

```bash
# Verify sync is working
journalctl -u aitbc-blockchain-node | grep "Imported block"
```

If you want to enable push sync, ensure the hub supports subscription endpoints and check your network connectivity to the hub.

#### Service fails: "Failed to load environment files: No such file or directory"

The service's `EnvironmentFile=/etc/aitbc/%N.env` references a file that doesn't exist. The `%N` specifier expands to the unit name **without** `.service` (e.g., `aitbc-blockchain-node.service` → `aitbc-blockchain-node`).

```bash
# Check which env file the service expects
grep EnvironmentFile /etc/systemd/system/aitbc-blockchain-node.service

# Verify the file exists (must NOT have .service in the name)
ls -la /etc/aitbc/aitbc-blockchain-node.env

# If missing, regenerate env files
sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh

# Or create manually (see "Per-Service Environment Files" section above)
```

#### Service fails: "fe_sendauth: no password supplied"

The `DATABASE_URL` in the service's `%N.env` file lacks credentials. PostgreSQL requires a username and password.

```bash
# Check the DATABASE_URL in the env file
grep DATABASE_URL /etc/aitbc/aitbc-coordinator-api.env

# If it's missing credentials, fix it:
# Wrong:  DATABASE_URL=postgresql://localhost:5432/aitbc_coordinator
# Right:  DATABASE_URL=postgresql://aitbc_user:<password>@localhost:5432/aitbc_coordinator

# Regenerate with correct credentials
sudo /opt/aitbc/scripts/deployment/setup_postgresql_databases.sh
sudo systemctl restart aitbc-coordinator-api
```

#### systemctl enable fails: "no installation config"

The service file is missing an `[Install]` section. Add it to the service file:

```bash
echo -e '\n[Install]\nWantedBy=multi-user.target' | sudo tee -a /etc/systemd/system/aitbc-coordinator-api.service
sudo systemctl daemon-reload
sudo systemctl enable aitbc-coordinator-api
```

## Related Topics

- [Quick Start](./setup-quick-start.md) - Installation and profiles
- [Service Selection](./setup-service-selection.md) - Role-based service configuration
- [Subscription System](./setup-subscription.md) - Lease-based block synchronization
- [Configuration](./setup-configuration.md) - Runtime directories, secrets, and environment files
- [Security](./setup-security.md) - Service user security
