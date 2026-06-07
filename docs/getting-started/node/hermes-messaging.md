# Hermes Messaging Setup

This guide covers setting up PING/PONG messaging via the Hermes polling daemon.

## Configure Hermes Polling Daemon

Create `/etc/aitbc/node.env`:

```bash
NODE_ID=<your-node-id>
ISLAND_ID=<your-island-id>
CHAIN_ID=ait-hub.aitbc.bubuit.net
NODE_ROLE=follower

# Hermes Configuration
HERMES_COORDINATOR_URL=http://localhost:8203
HERMES_AGENT_ID=<your-agent-id>
```

## Start Hermes Polling Daemon

```bash
# Create systemd service
cat > /etc/systemd/system/aitbc-agent-daemon.service << 'EOF'
[Unit]
Description=AITBC Agent Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
EnvironmentFile=/etc/aitbc/node.env
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/apps/agent-daemon/aitbc-agent-daemon-wrapper.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
systemctl daemon-reload
systemctl enable aitbc-agent-daemon.service
systemctl start aitbc-agent-daemon.service
```

## Test PING/PONG

The polling daemon automatically handles PING messages and responds with PONG. No manual configuration needed.

## Verify Operation

```bash
# Check service status
systemctl status aitbc-agent-daemon

# Check logs
journalctl -u aitbc-agent-daemon -f

# Verify coordinator connectivity
curl -s http://localhost:8203/health
```

## See Also

- [Blockchain Setup](blockchain-setup.md)
- [Coin Requests](coin-requests.md)
- [Troubleshooting](../reference/troubleshooting.md)
