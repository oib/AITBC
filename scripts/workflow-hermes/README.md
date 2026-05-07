# hermes Multi-Node Blockchain Workflow Scripts

This directory contains hermes-enabled versions of the multi-node blockchain setup scripts that interact with hermes agents instead of executing manual commands.

## Overview

The hermes workflow scripts transform the manual multi-node blockchain deployment into an intelligent, automated, and coordinated agent-based system.

## Scripts

### 1. `01_preflight_setup_hermes.sh`
**Purpose**: Pre-flight setup with hermes agent deployment
**Agent**: CoordinatorAgent, GenesisAgent, FollowerAgent, WalletAgent
**Tasks**:
- Deploy hermes agents
- Stop existing services via agents
- Update systemd configurations
- Setup central configuration
- Initialize agent communication channels

### 2. `02_genesis_authority_setup_hermes.sh`
**Purpose**: Setup genesis authority node using hermes agents
**Agent**: GenesisAgent, WalletAgent, CoordinatorAgent
**Tasks**:
- Initialize GenesisAgent
- Pull latest code
- Update environment configuration
- Create genesis block
- Create genesis wallets
- Start blockchain services
- Verify genesis state

### 3. `03_follower_node_setup_hermes.sh`
**Purpose**: Setup follower node using hermes agents
**Agent**: FollowerAgent, CoordinatorAgent
**Tasks**:
- Initialize FollowerAgent
- Connect to aitbc1 node
- Update follower configuration
- Start follower services
- Establish genesis connection
- Monitor and verify sync

### 4. `04_wallet_operations_hermes.sh`
**Purpose**: Execute wallet operations across nodes using hermes agents
**Agent**: WalletAgent, CoordinatorAgent
**Tasks**:
- Create cross-node wallets
- Fund wallets from genesis
- Execute cross-node transactions
- Verify transaction confirmations
- Test wallet switching

### 5. `05_complete_workflow_hermes.sh`
**Purpose**: Orchestrate complete multi-node deployment using all hermes agents
**Agent**: CoordinatorAgent (orchestrates all other agents)
**Tasks**:
- Execute all workflow phases
- Comprehensive verification
- Performance testing
- Network health checks
- Generate final reports

## hermes Agent Architecture

### Agent Types

#### **CoordinatorAgent**
- **Role**: Orchestrates all agent activities
- **Capabilities**: Orchestration, monitoring, coordination
- **Access**: Agent communication, task distribution

#### **GenesisAgent**
- **Role**: Manages genesis authority node (aitbc)
- **Capabilities**: System admin, blockchain genesis, service management
- **Access**: SSH, systemctl, file system

#### **FollowerAgent**
- **Role**: Manages follower node (aitbc1)
- **Capabilities**: System admin, blockchain sync, service management
- **Access**: SSH, systemctl, file system

#### **WalletAgent**
- **Role**: Manages wallet operations across nodes
- **Capabilities**: Wallet management, transaction processing
- **Access**: CLI commands, blockchain RPC

## Usage

### Quick Start
```bash
# Run complete workflow with hermes agents
./05_complete_workflow_hermes.sh

# Run individual phases
./01_preflight_setup_hermes.sh
./02_genesis_authority_setup_hermes.sh
./03_follower_node_setup_hermes.sh
./04_wallet_operations_hermes.sh
```

### hermes Commands
```bash
# Deploy agents
hermes deploy --config /tmp/hermes_agents.json

# Monitor agents
hermes status --agent all

# Execute specific agent tasks
hermes execute --agent GenesisAgent --task create_genesis_block
hermes execute --agent FollowerAgent --task sync_with_genesis
hermes execute --agent WalletAgent --task create_cross_node_wallets

# Generate reports
hermes report --workflow multi_node --format json
```

## Key Features

### ✅ **Intelligent Coordination**
- Agents communicate via structured message protocol
- Automatic task distribution and monitoring
- Real-time status updates between agents
- Coordinated error recovery

### ✅ **Automated Execution**
- No manual command execution required
- Agents handle all operations automatically
- Consistent execution across deployments
- Reduced human error

### ✅ **Error Handling and Recovery**
- Built-in error detection and recovery
- Automatic retry mechanisms
- Service health monitoring
- Comprehensive logging and reporting

### ✅ **Scalability**
- Easy to add more nodes and agents
- Parallel execution where possible
- Modular agent design
- Dynamic task distribution

## Agent Communication

### Message Format
```json
{
    "agent_id": "GenesisAgent",
    "message_type": "status_update",
    "target_agent": "CoordinatorAgent",
    "payload": {
        "status": "genesis_block_created",
        "details": {
            "block_height": 1,
            "genesis_hash": "0x...",
            "timestamp": "2026-03-30T12:40:00Z"
        }
    },
    "timestamp": "2026-03-30T12:40:00Z"
}
```

### Communication Flow
1. **CoordinatorAgent** deploys all agents
2. **GenesisAgent** sets up genesis authority
3. **FollowerAgent** configures follower node
4. **WalletAgent** manages wallet operations
5. **CoordinatorAgent** monitors and verifies completion

## Reports and Monitoring

### Report Types
- **Preflight Report**: `/tmp/hermes_preflight_report.json`
- **Genesis Report**: `/tmp/hermes_genesis_report.json`
- **Follower Report**: `/tmp/hermes_follower_report.json`
- **Wallet Report**: `/tmp/hermes_wallet_report.json`
- **Complete Report**: `/tmp/hermes_complete_report.json`

### Monitoring Commands
```bash
# Monitor agent status
hermes monitor --agent all

# Monitor workflow progress
hermes monitor --workflow multi_node --real-time

# Check agent health
hermes health --agent all
```

## Troubleshooting

### Common Issues

#### hermes CLI Not Found
```bash
# Install hermes
pip install hermes-agent

# Or use mock mode (development)
export hermes_MOCK_MODE=1
```

#### Agent Communication Failure
```bash
# Check agent status
hermes status --agent all

# Restart communication
hermes restart --communication

# Verify network connectivity
ping -c 1 aitbc1
```

#### Service Start Failures
```bash
# Check service logs via agents
hermes execute --agent GenesisAgent --task show_service_logs

# Manual service check
systemctl status aitbc-blockchain-node.service
```

### Debug Mode
```bash
# Enable debug logging
export hermes_DEBUG=1

# Run with verbose output
./05_complete_workflow_hermes.sh --verbose

# Check agent logs
hermes logs --agent all --tail 50
```

## Comparison with Manual Scripts

| Feature | Manual Scripts | hermes Scripts |
|---------|----------------|-------------------|
| Execution | Manual commands | Agent-automated |
| Coordination | Human coordination | Agent coordination |
| Error Handling | Manual intervention | Automatic recovery |
| Monitoring | Manual checks | Real-time monitoring |
| Scalability | Limited | Highly scalable |
| Consistency | Variable | Consistent |
| Reporting | Manual | Automated |

## Prerequisites

### System Requirements
- hermes CLI installed
- SSH access to both nodes (aitbc, aitbc1)
- Python virtual environment at `/opt/aitbc/venv`
- AITBC CLI tool available
- Network connectivity between nodes

### hermes Installation
```bash
# Install hermes
pip install hermes-agent

# Verify installation
hermes --version

# Initialize hermes
hermes init --workspace /opt/aitbc
```

## Next Steps

1. **Run the complete workflow**: `./05_complete_workflow_hermes.sh`
2. **Monitor agent activity**: `hermes monitor --agent all`
3. **Verify deployment**: Check generated reports
4. **Test operations**: Execute test transactions
5. **Scale deployment**: Add more nodes and agents

## Support

For issues with hermes scripts:
1. Check agent status: `hermes status --agent all`
2. Review agent logs: `hermes logs --agent all`
3. Verify network connectivity
4. Check hermes configuration
5. Run in debug mode for detailed logging
