# Multi-Node Journalctl Real-Time Monitoring

This workflow provides real-time monitoring of SystemD journal logs across all three AITBC nodes (aitbc, aitbc1, gitea-runner) with filtering for warnings and errors.

## Prerequisites

### Required Setup
- SSH access to all three nodes (aitbc, aitbc1, gitea-runner)
- SystemD services running on all nodes
- Working directory: `/opt/aitbc`
- journalctl access on all nodes

### Node Configuration
- **aitbc** (hub for ait-mainnet): localhost
- **aitbc1** (hub for ait-testnet): ssh aitbc1
- **gitea-runner** (follower): ssh gitea-runner

## Real-Time Monitoring Modes

### Mode 1: Single Node Real-Time Monitoring

**Monitor aitbc (local node):**
```bash
journalctl -fu aitbc-blockchain-node.service
```

**Monitor specific service on aitbc:**
```bash
journalctl -fu aitbc-blockchain-node.service -p warning -p err
```

**Monitor all aitbc services:**
```bash
journalctl -fu 'aitbc-*' -p warning -p err
```

### Mode 2: Multi-Node Real-Time Monitoring

**Monitor all blockchain services on all nodes (parallel):**
```bash
# Terminal 1: aitbc
journalctl -fu 'aitbc-*' -p warning -p err

# Terminal 2: aitbc1
ssh aitbc1 'journalctl -fu "aitbc-*" -p warning -p err'

# Terminal 3: gitea-runner
ssh gitea-runner 'journalctl -fu "aitbc-*" -p warning -p err'
```

**Monitor with node identification:**
```bash
# aitbc
echo "=== MONITORING aitbc ===" && journalctl -fu 'aitbc-*' -p warning -p err --output-cat

# aitbc1
echo "=== MONITORING aitbc1 ===" && ssh aitbc1 'journalctl -fu "aitbc-*" -p warning -p err --output-cat'

# gitea-runner
echo "=== MONITORING gitea-runner ===" && ssh gitea-runner 'journalctl -fu "aitbc-*" -p warning -p err --output-cat'
```

### Mode 3: Filtered Monitoring

**Monitor only errors:**
```bash
# aitbc
journalctl -fu 'aitbc-*' -p err

# aitbc1
ssh aitbc1 'journalctl -fu "aitbc-*" -p err'

# gitea-runner
ssh gitea-runner 'journalctl -fu "aitbc-*" -p err'
```

**Monitor warnings and errors:**
```bash
# aitbc
journalctl -fu 'aitbc-*' -p warning -p err

# aitbc1
ssh aitbc1 'journalctl -fu "aitbc-*" -p warning -p err'

# gitea-runner
ssh gitea-runner 'journalctl -fu "aitbc-*" -p warning -p err'
```

**Monitor with time filter:**
```bash
# Monitor last hour of logs, then follow new logs
journalctl -fu 'aitbc-*' --since "1 hour ago" -p warning -p err
```

### Mode 4: Pattern-Specific Monitoring

**Monitor for specific error patterns:**
```bash
# Monitor for sync errors
journalctl -fu 'aitbc-*' | grep -i "sync\|error"

# Monitor for RPC bootstrap issues
journalctl -fu 'aitbc-*' | grep -i "bootstrap\|genesis"

# Monitor for P2P issues
journalctl -fu 'aitbc-*' | grep -i "p2p\|peer\|connection"
```

**Multi-node pattern monitoring:**
```bash
# aitbc
journalctl -fu 'aitbc-*' | grep -i "sync\|error"

# aitbc1
ssh aitbc1 'journalctl -fu "aitbc-*" | grep -i "sync\|error"'

# gitea-runner
ssh gitea-runner 'journalctl -fu "aitbc-*" | grep -i "sync\|error"'
```

## Quick Start Commands

### Quick All-Node Warning/Error Monitor
```bash
# Start monitoring all nodes for warnings and errors
echo "=== Starting multi-node warning/error monitoring ===" && \
journalctl -fu 'aitbc-*' -p warning -p err &
AITBC_PID=$!

ssh aitbc1 'journalctl -fu "aitbc-*" -p warning -p err' &
AITBC1_PID=$!

ssh gitea-runner 'journalctl -fu "aitbc-*" -p warning -p err' &
GITEA_PID=$!

# Store PIDs for cleanup
echo "Monitoring started. PIDs: aitbc=$AITBC_PID, aitbc1=$AITBC1_PID, gitea-runner=$GITEA_PID"
echo "Press Ctrl+C to stop all monitors"

# Function to cleanup on exit
trap "kill $AITBC_PID $AITBC1_PID $GITEA_PID 2>/dev/null; echo 'Monitoring stopped'" EXIT

wait
```

### Quick Error-Only Monitor
```bash
# Monitor only errors across all nodes
echo "=== Starting multi-node error-only monitoring ===" && \
journalctl -fu 'aitbc-*' -p err &
AITBC_PID=$!

ssh aitbc1 'journalctl -fu "aitbc-*" -p err' &
AITBC1_PID=$!

ssh gitea-runner 'journalctl -fu "aitbc-*" -p err' &
GITEA_PID=$!

# Store PIDs for cleanup
echo "Error monitoring started. PIDs: aitbc=$AITBC_PID, aitbc1=$AITBC1_PID, gitea-runner=$GITEA_PID"
echo "Press Ctrl+C to stop all monitors"

# Function to cleanup on exit
trap "kill $AITBC_PID $AITBC1_PID $GITEA_PID 2>/dev/null; echo 'Error monitoring stopped'" EXIT

wait
```

## Advanced Monitoring Scripts

### Script 1: Multi-Node Monitor with Timestamps
```bash
#!/bin/bash
# multi-node-monitor.sh - Real-time monitoring with timestamps

echo "=== Multi-Node Journalctl Monitor with Timestamps ==="
echo "Press Ctrl+C to stop monitoring"
echo ""

# Function to monitor single node with prefix
monitor_node() {
    local node_name=$1
    local node_cmd=$2

    while true; do
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$timestamp] $node_name"
        eval "$node_cmd" | head -5
        sleep 5
    done
}

# Start monitors in background
monitor_node "aitbc" "journalctl -u aitbc-blockchain-node.service -n 5 --no-pager -p warning -p err" &
MONITOR1=$!

monitor_node "aitbc1" "ssh aitbc1 'journalctl -u aitbc-blockchain-node.service -n 5 --no-pager -p warning -p err'" &
MONITOR2=$!

monitor_node "gitea-runner" "ssh gitea-runner 'journalctl -u aitbc-blockchain-node.service -n 5 --no-pager -p warning -p err'" &
MONITOR3=$!

trap "kill $MONITOR1 $MONITOR2 $MONITOR3 2>/dev/null; echo 'Monitoring stopped'" EXIT

wait
```

### Script 2: Error Counter with Alerts
```bash
#!/bin/bash
# error-counter.sh - Count errors and alert on threshold

ERROR_THRESHOLD=10
CHECK_INTERVAL=30

echo "=== Error Counter with Alerts ==="
echo "Threshold: $ERROR_THRESHOLD errors in $CHECK_INTERVAL seconds"
echo ""

while true; do
    echo "=== Error Count Check $(date '+%Y-%m-%d %H:%M:%S') ==="

    # Count errors on each node
    aitbc_errors=$(journalctl -u aitbc-blockchain-node.service --since "$CHECK_INTERVAL seconds ago" -p err --no-pager | wc -l)
    aitbc1_errors=$(ssh aitbc1 'journalctl -u aitbc-blockchain-node.service --since "$CHECK_INTERVAL seconds ago" -p err --no-pager' 2>/dev/null | wc -l)
    gitea_errors=$(ssh gitea-runner 'journalctl -u aitbc-blockchain-node.service --since "$CHECK_INTERVAL seconds ago" -p err --no-pager' 2>/dev/null | wc -l)

    echo "aitbc errors: $aitbc_errors"
    echo "aitbc1 errors: $aitbc1_errors"
    echo "gitea-runner errors: $gitea_errors"

    # Alert on threshold breach
    if [ "$aitbc_errors" -ge "$ERROR_THRESHOLD" ]; then
        echo "⚠️  ALERT: aitbc error count ($aitbc_errors) exceeds threshold ($ERROR_THRESHOLD)"
    fi

    if [ "$aitbc1_errors" -ge "$ERROR_THRESHOLD" ]; then
        echo "⚠️  ALERT: aitbc1 error count ($aitbc1_errors) exceeds threshold ($ERROR_THRESHOLD)"
    fi

    if [ "$gitea_errors" -ge "$ERROR_THRESHOLD" ]; then
        echo "⚠️  ALERT: gitea-runner error count ($gitea_errors) exceeds threshold ($ERROR_THRESHOLD)"
    fi

    echo ""
    sleep $CHECK_INTERVAL
done
```

### Script 3: Real-Time Log Aggregator
```bash
#!/bin/bash
# log-aggregator.sh - Aggregate logs from all nodes in real-time

echo "=== Real-Time Log Aggregator ==="
echo "Press Ctrl+C to stop aggregation"
echo ""

# Create named pipes for each node
PIPE_AITBC=$(mktemp -u)
PIPE_AITBC1=$(mktemp -u)
PIPE_GITEA=$(mktemp -u)

mkfifo $PIPE_AITBC
mkfifo $PIPE_AITBC1
mkfifo $PIPE_GITEA

# Function to read from pipe and add prefix
read_pipe() {
    local prefix=$1
    local pipe=$2

    while read line; do
        echo "[$prefix] $line"
    done < $pipe
}

# Start journalctl for each node and pipe to named pipes
journalctl -fu 'aitbc-*' -p warning -p err > $PIPE_AITBC &
PID_AITBC=$!

ssh aitbc1 'journalctl -fu "aitbc-*" -p warning -p err' > $PIPE_AITBC1 &
PID_AITBC1=$!

ssh gitea-runner 'journalctl -fu "aitbc-*" -p warning -p err' > $PIPE_GITEA &
PID_GITEA=$!

# Start readers for each pipe
read_pipe "aitbc" $PIPE_AITBC &
READER1=$!

read_pipe "aitbc1" $PIPE_AITBC1 &
READER2=$!

read_pipe "gitea" $PIPE_GITEA &
READER3=$!

# Cleanup function
cleanup() {
    kill $PID_AITBC $PID_AITBC1 $PID_GITEA $READER1 $READER2 $READER3 2>/dev/null
    rm -f $PIPE_AITBC $PIPE_AITBC1 $PIPE_GITEA
    echo "Log aggregation stopped"
}

trap cleanup EXIT

wait
```

## Common Monitoring Scenarios

### Scenario 1: Monitor After Configuration Change
```bash
# Monitor all nodes for 5 minutes after making changes
timeout 300 bash -c '
journalctl -fu "aitbc-*" -p warning -p err &
AITBC_PID=$!

ssh aitbc1 "journalctl -fu \"aitbc-*\" -p warning -p err" &
AITBC1_PID=$!

ssh gitea-runner "journalctl -fu \"aitbc-*\" -p warning -p err" &
GITEA_PID=$!

trap "kill $AITBC_PID $AITBC1_PID $GITEA_PID 2>/dev/null" EXIT

wait
'
```

### Scenario 2: Monitor Specific Chain
```bash
# Monitor for chain-specific issues
# aitbc (ait-mainnet hub)
journalctl -fu 'aitbc-*' | grep -i "mainnet\|chain=ait-mainnet"

# aitbc1 (ait-testnet hub)
ssh aitbc1 'journalctl -fu "aitbc-*" | grep -i "testnet\|chain=ait-testnet"'
```

### Scenario 3: Monitor Block Production
```bash
# Monitor block production issues
journalctl -fu 'aitbc-*' | grep -i "block.*production\|proposer\|proposed"

# Monitor for sync issues
journalctl -fu 'aitbc-*' | grep -i "sync\|import\|bulk"
```

### Scenario 4: Monitor RPC Bootstrap
```bash
# Monitor RPC bootstrap activity
journalctl -fu 'aitbc-*' | grep -i "bootstrap\|genesis\|rpc"

# Monitor across all nodes
ssh aitbc1 'journalctl -fu "aitbc-*" | grep -i "bootstrap\|genesis\|rpc"'
```

## Journalctl Priority Levels

Understanding priority levels for filtering:

- **emerg** (0): System is unusable
- **alert** (1): Action must be taken immediately
- **crit** (2): Critical conditions
- **err** (3): Error conditions
- **warning** (4): Warning conditions
- **notice** (5): Normal but significant condition
- **info** (6): Informational messages
- **debug** (7): Debug-level messages

**Common filtering combinations:**
- `-p err`: Only errors
- `-p warning -p err`: Warnings and errors
- `-p notice -p warning -p err`: Notice, warning, and errors
- `-p crit -p err`: Critical and errors only

## Troubleshooting Monitoring Issues

### SSH Connection Issues
```bash
# Test SSH connectivity before monitoring
ssh aitbc1 'echo "Connection OK"'
ssh gitea-runner 'echo "Connection OK"'
```

### Permission Issues
```bash
# Check journalctl access
journalctl -n 1 --no-pager
ssh aitbc1 'journalctl -n 1 --no-pager'
ssh gitea-runner 'journalctl -n 1 --no-pager'
```

### Service Not Running
```bash
# Check if services are running before monitoring
systemctl status aitbc-blockchain-node.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service'
ssh gitea-runner 'systemctl status aitbc-blockchain-node.service'
```

## Best Practices

1. **Use priority filtering** to reduce noise: `-p warning -p err`
2. **Monitor in separate terminals** for different nodes
3. **Use grep patterns** for specific issue types
4. **Set timeouts** for monitoring sessions to avoid indefinite runs
5. **Use cleanup traps** to stop background processes
6. **Test connectivity** before starting multi-node monitoring
7. **Use meaningful timestamps** when aggregating logs from multiple sources
8. **Focus on specific services** when troubleshooting known issues

## Related Skills
- multi-node-log-check - Comprehensive log checking workflow
- aitbc-blockchain-troubleshooting - Blockchain troubleshooting procedures
- aitbc-configuration-management - Configuration management and validation
