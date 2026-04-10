---
description: Atomic AITBC cross-node coordination and messaging operations with deterministic outputs
title: aitbc-node-coordinator
version: 1.0
---

# AITBC Node Coordinator

## Purpose
Coordinate cross-node operations, synchronize blockchain state, and manage inter-node messaging between genesis and follower nodes.

## Activation
Trigger when user requests cross-node operations: synchronization, coordination, messaging, or multi-node status checks.

## Input
```json
{
  "operation": "sync|status|message|coordinate|health",
  "target_node": "genesis|follower|all",
  "message": "string (optional for message operation)",
  "sync_type": "blockchain|mempool|configuration|git|all (optional for sync)",
  "timeout": "number (optional, default: 60)",
  "force": "boolean (optional, default: false)",
  "verify": "boolean (optional, default: true)"
}
```

## Output
```json
{
  "summary": "Cross-node operation completed successfully",
  "operation": "sync|status|message|coordinate|health",
  "target_node": "genesis|follower|all",
  "nodes_status": {
    "genesis": {
      "status": "online|offline|degraded",
      "block_height": "number",
      "mempool_size": "number",
      "p2p_connections": "number",
      "service_uptime": "string",
      "last_sync": "timestamp"
    },
    "follower": {
      "status": "online|offline|degraded",
      "block_height": "number",
      "mempool_size": "number",
      "p2p_connections": "number",
      "service_uptime": "string",
      "last_sync": "timestamp"
    }
  },
  "sync_result": "success|partial|failed",
  "sync_details": {
    "blockchain_synced": "boolean",
    "mempool_synced": "boolean",
    "configuration_synced": "boolean",
    "git_synced": "boolean"
  },
  "message_delivery": {
    "sent": "number",
    "delivered": "number",
    "failed": "number"
  },
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate target node connectivity using `ping` and SSH test
- Check SSH access to remote nodes with `ssh aitbc1 "echo test"`
- Verify blockchain service status with `systemctl status aitbc-blockchain-node`
- Assess synchronization requirements based on sync_type parameter
- Check P2P mesh network status with `netstat -an | grep 7070`
- Validate git synchronization status with `git status`

### 2. Plan
- Select appropriate coordination strategy based on operation type
- Prepare sync/messaging parameters for execution
- Define validation criteria for operation success
- Set fallback mechanisms for partial failures
- Calculate timeout based on operation complexity
- Determine if force flag is required for conflicting operations

### 3. Execute
- **For sync operations:**
  - Execute `git pull` on both nodes for git sync
  - Use CLI commands for blockchain state sync
  - Restart services if force flag is set
- **For status operations:**
  - Execute `ssh aitbc1 "systemctl status aitbc-blockchain-node"`
  - Check blockchain height with CLI: `./aitbc-cli chain block latest`
  - Query mempool status with CLI: `./aitbc-cli mempool status`
- **For message operations:**
  - Use P2P mesh network for message delivery
  - Track message delivery status
- **For coordinate operations:**
  - Execute coordinated actions across nodes
  - Monitor execution progress
- **For health operations:**
  - Run comprehensive health checks
  - Collect service metrics

### 4. Validate
- Verify node connectivity with ping and SSH
- Check synchronization completeness by comparing block heights
- Validate blockchain state consistency across nodes
- Confirm messaging delivery with delivery receipts
- Verify git synchronization with `git log --oneline -1`
- Check service status after operations
- Validate no service degradation occurred

## Constraints
- **MUST NOT** restart blockchain services without explicit request or force flag
- **MUST NOT** modify node configurations without explicit approval
- **MUST NOT** exceed 60 seconds execution time for sync operations
- **MUST NOT** execute more than 5 parallel cross-node operations simultaneously
- **MUST** validate SSH connectivity before remote operations
- **MUST** handle partial failures gracefully with fallback mechanisms
- **MUST** preserve service state during coordination operations
- **MUST** verify git synchronization before force operations
- **MUST** check service health before critical operations
- **MUST** respect timeout limits (default 60s, max 120s for complex ops)
- **MUST** validate target node existence before operations
- **MUST** return detailed error information for all failures

## Environment Assumptions
- SSH access configured between genesis (aitbc) and follower (aitbc1) with key-based authentication
- SSH keys located at `/root/.ssh/` for passwordless access
- Blockchain nodes operational on both nodes via systemd services
- P2P mesh network active on port 7070 with peer configuration
- Git synchronization configured between nodes at `/opt/aitbc/.git`
- CLI accessible on both nodes at `/opt/aitbc/aitbc-cli`
- Python venv activated at `/opt/aitbc/venv/bin/python` for CLI operations
- Systemd services: `aitbc-blockchain-node.service` on both nodes
- Node addresses: genesis (localhost/aitbc), follower (aitbc1)
- Git remote: `origin` at `http://gitea.bubuit.net:3000/oib/aitbc.git`
- Log directory: `/var/log/aitbc/` for service logs
- Data directory: `/var/lib/aitbc/` for blockchain data

## Error Handling
- SSH connectivity failures → Return connection error with affected node, attempt fallback node
- SSH authentication failures → Return authentication error, check SSH key permissions
- Blockchain service offline → Mark node as offline in status, attempt service restart if force flag set
- Sync failures → Return partial sync with details, identify which sync type failed
- Timeout during operations → Return timeout error with operation details, suggest increasing timeout
- Git synchronization conflicts → Return conflict error, suggest manual resolution
- P2P network disconnection → Return network error, check mesh network status
- Service restart failures → Return service error, check systemd logs
- Node unreachable → Return unreachable error, verify network connectivity
- Invalid target node → Return validation error, suggest valid node names
- Permission denied → Return permission error, check user privileges
- CLI command failures → Return command error with stderr output
- Partial operation success → Return partial success with completed and failed components

## Example Usage Prompt

```
Sync blockchain state between genesis and follower nodes
```

```
Check status of all nodes in the network
```

```
Sync git repository across all nodes with force flag
```

```
Perform health check on follower node
```

```
Coordinate blockchain service restart on genesis node
```

## Expected Output Example

```json
{
  "summary": "Blockchain state synchronized between genesis and follower nodes",
  "operation": "sync",
  "target_node": "all",
  "nodes_status": {
    "genesis": {
      "status": "online",
      "block_height": 15234,
      "mempool_size": 15,
      "p2p_connections": 2,
      "service_uptime": "5d 12h 34m",
      "last_sync": 1775811500
    },
    "follower": {
      "status": "online",
      "block_height": 15234,
      "mempool_size": 15,
      "p2p_connections": 2,
      "service_uptime": "5d 12h 31m",
      "last_sync": 1775811498
    }
  },
  "sync_result": "success",
  "sync_details": {
    "blockchain_synced": true,
    "mempool_synced": true,
    "configuration_synced": true,
    "git_synced": true
  },
  "message_delivery": {
    "sent": 0,
    "delivered": 0,
    "failed": 0
  },
  "issues": [],
  "recommendations": ["Nodes are fully synchronized, P2P mesh operating normally"],
  "confidence": 1.0,
  "execution_time": 8.5,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Simple status checks on individual nodes
- Basic connectivity verification
- Quick health checks
- Single-node operations

**Reasoning Model** (Claude Sonnet, GPT-4)
- Cross-node synchronization operations
- Status validation and error diagnosis
- Coordination strategy selection
- Multi-node state analysis
- Complex error recovery
- Force operations with validation

**Performance Notes**
- **Execution Time**: 
  - Sync operations: 5-30 seconds (blockchain), 2-15 seconds (git), 3-20 seconds (mempool)
  - Status checks: 2-10 seconds per node
  - Health checks: 5-15 seconds per node
  - Coordinate operations: 10-45 seconds depending on complexity
  - Message operations: 1-5 seconds per message
- **Memory Usage**: 
  - Status checks: <50MB
  - Sync operations: <100MB
  - Complex coordination: <150MB
- **Network Requirements**: 
  - SSH connectivity (port 22)
  - P2P mesh network (port 7070)
  - Git remote access (HTTP/SSH)
- **Concurrency**: 
  - Safe for sequential operations on different nodes
  - Max 5 parallel operations across nodes
  - Coordinate parallel ops carefully to avoid service overload
- **Optimization Tips**: 
  - Use status checks before sync operations to validate node health
  - Batch multiple sync operations when possible
  - Use verify=false for non-critical operations to speed up execution
  - Cache node status for repeated checks within 30-second window
