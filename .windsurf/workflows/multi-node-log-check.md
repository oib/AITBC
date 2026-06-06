# Multi-Node Log Check Workflow

This workflow provides comprehensive logfile and journalctl checking across all three AITBC nodes (aitbc, aitbc1, gitea-runner) for debugging and monitoring purposes.

## Prerequisites

### Required Setup
- SSH access to all three nodes (aitbc, aitbc1, gitea-runner)
- SystemD services running on all nodes
- Working directory: `/opt/aitbc`

### Node Configuration
- **aitbc** (genesis node): localhost
- **aitbc1** (follower node): ssh aitbc1
- **gitea-runner** (CI runner): ssh gitea-runner

## Workflow Phases

### Phase 1: SystemD Service Status Check
**Objective**: Check SystemD service status across all nodes

```bash
echo "=== SYSTEMD SERVICE STATUS CHECK ==="
echo ""

echo "=== aitbc (Genesis) ==="
systemctl status aitbc-blockchain-node.service --no-pager | head -5
systemctl status aitbc-coordinator-api.service --no-pager | head -5
systemctl status aitbc-blockchain-p2p.service --no-pager | head -5

echo ""
echo "=== aitbc1 (Follower) ==="
ssh aitbc1 'systemctl status aitbc-blockchain-node.service --no-pager | head -5'
ssh aitbc1 'systemctl status aitbc-coordinator-api.service --no-pager | head -5'
ssh aitbc1 'systemctl status aitbc-blockchain-p2p.service --no-pager | head -5'

echo ""
echo "=== gitea-runner ==="
ssh gitea-runner 'systemctl status gitea-runner.service --no-pager | head -5'
```

### Phase 2: Application Log Check
**Objective**: Check application logs in /var/log/aitbc across all nodes

```bash
echo "=== APPLICATION LOG CHECK ==="
echo ""

echo "=== aitbc (Genesis) ==="
echo "Recent blockchain-node logs:"
tail -n 20 /var/log/aitbc/blockchain-node.log 2>/dev/null || echo "No blockchain-node log"
echo ""
echo "Recent coordinator-api logs:"
tail -n 20 /var/log/aitbc/coordinator-api.log 2>/dev/null || echo "No coordinator-api log"
echo ""
echo "Recent P2P logs:"
tail -n 20 /var/log/aitbc/blockchain-p2p.log 2>/dev/null || echo "No P2P log"

echo ""
echo "=== aitbc1 (Follower) ==="
echo "Recent blockchain-node logs:"
ssh aitbc1 'tail -n 20 /var/log/aitbc/blockchain-node.log 2>/dev/null || echo "No blockchain-node log"'
echo ""
echo "Recent coordinator-api logs:"
ssh aitbc1 'tail -n 20 /var/log/aitbc/coordinator-api.log 2>/dev/null || echo "No coordinator-api log"'
echo ""
echo "Recent P2P logs:"
ssh aitbc1 'tail -n 20 /var/log/aitbc/blockchain-p2p.log 2>/dev/null || echo "No P2P log"'
```

### Phase 3: SystemD Journal Check
**Objective**: Check SystemD journal logs for all services across all nodes

```bash
echo "=== SYSTEMD JOURNAL CHECK ==="
echo ""

echo "=== aitbc (Genesis) ==="
echo "Recent blockchain-node journal:"
journalctl -u aitbc-blockchain-node.service -n 20 --no-pager
echo ""
echo "Recent coordinator-api journal:"
journalctl -u aitbc-coordinator-api.service -n 20 --no-pager
echo ""
echo "Recent P2P journal:"
journalctl -u aitbc-blockchain-p2p.service -n 20 --no-pager

echo ""
echo "=== aitbc1 (Follower) ==="
echo "Recent blockchain-node journal:"
ssh aitbc1 'journalctl -u aitbc-blockchain-node.service -n 20 --no-pager'
echo ""
echo "Recent coordinator-api journal:"
ssh aitbc1 'journalctl -u aitbc-coordinator-api.service -n 20 --no-pager'
echo ""
echo "Recent P2P journal:"
ssh aitbc1 'journalctl -u aitbc-blockchain-p2p.service -n 20 --no-pager'

echo ""
echo "=== gitea-runner ==="
echo "Recent gitea-runner journal:"
ssh gitea-runner 'journalctl -u gitea-runner.service -n 20 --no-pager'
```

### Phase 4: Error Pattern Search
**Objective**: Search for error patterns in logs across all nodes

```bash
echo "=== ERROR PATTERN SEARCH ==="
echo ""

echo "=== aitbc (Genesis) ==="
echo "Errors in blockchain-node logs:"
rg -i "error|exception|failed" /var/log/aitbc/blockchain-node.log 2>/dev/null | tail -10 || echo "No errors found"
echo ""
echo "Errors in coordinator-api logs:"
rg -i "error|exception|failed" /var/log/aitbc/coordinator-api.log 2>/dev/null | tail -10 || echo "No errors found"

echo ""
echo "=== aitbc1 (Follower) ==="
echo "Errors in blockchain-node logs:"
ssh aitbc1 'rg -i "error|exception|failed" /var/log/aitbc/blockchain-node.log 2>/dev/null | tail -10 || echo "No errors found"'
echo ""
echo "Errors in coordinator-api logs:"
ssh aitbc1 'rg -i "error|exception|failed" /var/log/aitbc/coordinator-api.log 2>/dev/null | tail -10 || echo "No errors found"

echo ""
echo "=== gitea-runner ==="
echo "Errors in gitea-runner journal:"
ssh gitea-runner 'journalctl -u gitea-runner --since "1 hour ago" --no-pager | rg -i "error|exception|failed" | tail -10 || echo "No errors found"'
```

### Phase 5: P2P Network Health Check
**Objective**: Check P2P network health across all nodes

```bash
echo "=== P2P NETWORK HEALTH CHECK ==="
echo ""

echo "=== aitbc (Genesis) ==="
echo "P2P peer connections:"
journalctl -u aitbc-blockchain-p2p -n 50 --no-pager | grep -E "(peer|connected|handshake)" | tail -10
echo ""
echo "P2P node ID errors:"
journalctl -u aitbc-blockchain-p2p --no-pager | grep -c "invalid or self node_id" || echo "0 errors"

echo ""
echo "=== aitbc1 (Follower) ==="
echo "P2P peer connections:"
ssh aitbc1 'journalctl -u aitbc-blockchain-p2p -n 50 --no-pager | grep -E "(peer|connected|handshake)" | tail -10'
echo ""
echo "P2P node ID errors:"
ssh aitbc1 'journalctl -u aitbc-blockchain-p2p --no-pager | grep -c "invalid or self node_id" || echo "0 errors"'
```

### Phase 6: Disk Space and Resource Check
**Objective**: Check disk space and resources across all nodes

```bash
echo "=== DISK SPACE AND RESOURCE CHECK ==="
echo ""

echo "=== aitbc (Genesis) ==="
echo "Disk space:"
df -h /var/log/aitbc /var/lib/aitbc
echo ""
echo "Memory:"
free -h

echo ""
echo "=== aitbc1 (Follower) ==="
echo "Disk space:"
ssh aitbc1 'df -h /var/log/aitbc /var/lib/aitbc'
echo ""
echo "Memory:"
ssh aitbc1 'free -h'

echo ""
echo "=== gitea-runner ==="
echo "Disk space:"
ssh gitea-runner 'df -h /opt/gitea-runner/logs'
echo ""
echo "Memory:"
ssh gitea-runner 'free -h'
```

### Phase 7: CI Log Check (gitea-runner only)
**Objective**: Check CI job logs on gitea-runner

```bash
echo "=== CI LOG CHECK ==="
echo ""

echo "=== gitea-runner CI Logs ==="
echo "Latest CI job log:"
ssh gitea-runner 'tail -n 50 /opt/gitea-runner/logs/latest.log 2>/dev/null || echo "No CI logs found"'
echo ""
echo "CI log index:"
ssh gitea-runner 'tail -n 10 /opt/gitea-runner/logs/index.tsv 2>/dev/null || echo "No CI log index found"'
```

## Quick Log Check Commands

### Single Node Quick Check
```bash
# Quick check for aitbc node
cd /opt/aitbc
echo "=== aitbc Quick Check ==="
systemctl status aitbc-blockchain-node.service --no-pager | grep Active
tail -n 10 /var/log/aitbc/blockchain-node.log
journalctl -u aitbc-blockchain-node.service -n 10 --no-pager
```

### Multi-Node Quick Check
```bash
# Quick check across all nodes
cd /opt/aitbc
echo "=== Multi-Node Quick Check ==="
echo "aitbc blockchain-node: $(systemctl is-active aitbc-blockchain-node.service)"
echo "aitbc1 blockchain-node: $(ssh aitbc1 'systemctl is-active aitbc-blockchain-node.service')"
echo "gitea-runner: $(ssh gitea-runner 'systemctl is-active gitea-runner.service')"
```

### Error-Only Check
```bash
# Check only for errors across all nodes
cd /opt/aitbc
echo "=== Error-Only Check ==="
echo "aitbc errors:"
rg -i "error|exception|failed" /var/log/aitbc/*.log 2>/dev/null | tail -5
echo "aitbc1 errors:"
ssh aitbc1 'rg -i "error|exception|failed" /var/log/aitbc/*.log 2>/dev/null | tail -5'
echo "gitea-runner errors:"
ssh gitea-runner 'journalctl -u gitea-runner --since "1 hour ago" --no-pager | rg -i "error|exception|failed" | tail -5'
```

## Common Log Locations

### aitbc (Genesis)
- `/var/log/aitbc/blockchain-node.log` - Blockchain node logs
- `/var/log/aitbc/coordinator-api.log` - Coordinator API logs
- `/var/log/aitbc/blockchain-p2p.log` - P2P service logs

### aitbc1 (Follower)
- Same as aitbc (Genesis)

### gitea-runner
- `/opt/gitea-runner/logs/latest.log` - Latest CI job log
- `/opt/gitea-runner/logs/index.tsv` - CI log index
- `/opt/gitea-runner/runner.log` - Gitea runner logs

## Common Journalctl Commands

### Check specific service
```bash
journalctl -u <service-name> -n 50 --no-pager
```

### Check with time filter
```bash
journalctl -u <service-name> --since "1 hour ago" --no-pager
journalctl -u <service-name> --since today --no-pager
journalctl -u <service-name> -f  # Follow logs
```

### Check for errors only
```bash
journalctl -u <service-name> -p err -n 50 --no-pager
```

### Check across all nodes
```bash
# aitbc
journalctl -u aitbc-blockchain-node.service -n 20 --no-pager

# aitbc1
ssh aitbc1 'journalctl -u aitbc-blockchain-node.service -n 20 --no-pager'

# gitea-runner
ssh gitea-runner 'journalctl -u gitea-runner.service -n 20 --no-pager'
```
