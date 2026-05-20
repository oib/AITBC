# SSH Access Patterns for AITBC Nodes

## Purpose
Document SSH access patterns for all AITBC nodes in the infrastructure.

## Node Access Patterns

### aitbc (localhost)
Direct access - no SSH required.
```bash
# Run commands directly on localhost
echo "command"
systemctl restart service-name
curl http://127.0.0.1:8006/rpc/head
```

### aitbc1
Direct SSH access.
```bash
ssh aitbc1
# Or execute single command
ssh aitbc1 "command"
# Access aitbc1's blockchain RPC
ssh aitbc1 "curl http://127.0.0.1:8006/rpc/head"
# Access aitbc from aitbc1
ssh aitbc1 "curl http://aitbc:8006/rpc/head"
```

### gitea-runner (hosts aitbc2 blockchain node)
Direct SSH access. The aitbc2 blockchain node runs on this same host.
```bash
ssh gitea-runner
# Or execute single command
ssh gitea-runner "command"
# aitbc2 blockchain node runs on this host

# Execute aitbc2-specific commands
ssh gitea-runner "/opt/aitbc/aitbc-cli blockchain info"
ssh gitea-runner "systemctl status aitbc-blockchain-node --no-pager"
```

### ns3 (hosts hub.aitbc.bubuit.net incus container)
Direct SSH access. The hub.aitbc.bubuit.net service runs as an incus container on ns3.
```bash
ssh ns3
# Or execute single command
ssh ns3 "command"

# Access the aitbc container (hub.aitbc.bubuit.net)
ssh ns3 "incus exec aitbc -- bash"
# Or execute single command in container
ssh ns3 "incus exec aitbc -- command"

# Container IP: 192.168.100.10
# Access via container IP from ns3
ssh ns3 "curl http://192.168.100.10:8006/rpc/head"

# Check environment configuration in container
ssh ns3 "incus exec aitbc -- cat /etc/aitbc/.env"
ssh ns3 "incus exec aitbc -- cat /etc/aitbc/node.env"

# Check service status in container
ssh ns3 "incus exec aitbc -- systemctl status aitbc-blockchain-node --no-pager"
```

## Important Notes
- **Never SSH to localhost**: Commands should run directly on the local machine
- **Use proper quoting**: When passing commands to SSH, use single quotes to prevent shell expansion
- **Test connectivity**: Verify RPC endpoints are accessible before running sync operations

## Common Operations

### Check service status on aitbc1
```bash
ssh aitbc1 "systemctl status aitbc-blockchain-node --no-pager"
```

### Restart service on gitea-runner (aitbc2)
```bash
ssh gitea-runner "systemctl restart aitbc-blockchain-node"
```

### Copy file to aitbc1
```bash
scp /path/to/file aitbc1:/path/to/destination
```

### Execute script on gitea-runner
```bash
ssh gitea-runner "bash /path/to/script.sh"
```

## Multi-Node Operations

### Run command on all remote nodes
```bash
for node in aitbc1 gitea-runner ns3; do
  ssh "$node" "systemctl status aitbc-blockchain-node --no-pager"
done
```

### Check block heights across all nodes
```bash
for node in aitbc1 gitea-runner; do
  echo "=== $node ==="
  ssh "$node" "curl -s http://localhost:8006/rpc/bestBlock | jq '.height'"
done

# Check ns3 (public hub) separately as it may have different RPC port
echo "=== ns3 ==="
ssh ns3 "curl -s http://localhost:8006/rpc/bestBlock | jq '.height'"
```
