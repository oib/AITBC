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
```

### aitbc1
Direct SSH access.
```bash
ssh aitbc1
# Or execute single command
ssh aitbc1 "command"
```

### gitea-runner (also hosts aitbc2)
Direct SSH access. aitbc2 blockchain node runs on the same host.
```bash
ssh gitea-runner
# Or execute single command
ssh gitea-runner "command"
```

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
for node in aitbc1 gitea-runner; do
  ssh "$node" "systemctl status aitbc-blockchain-node --no-pager"
done
```

### Check block heights across all nodes
```bash
for node in aitbc1 gitea-runner; do
  echo "=== $node ==="
  ssh "$node" "curl -s http://localhost:8006/rpc/bestBlock | jq '.height'"
done
```
