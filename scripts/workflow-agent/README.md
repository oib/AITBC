# agent Multi-Node Blockchain Workflow Scripts

This directory contains agent-enabled versions of the multi-node blockchain setup scripts that interact with agent agents instead of executing manual commands.

## Overview

The agent workflow scripts transform the manual multi-node blockchain deployment into an intelligent, automated, and coordinated agent-based system.

## Scripts

### 1. `01_preflight_setup_agent.sh`
**Purpose**: Pre-flight setup with agent agent deployment
**Agent**: CoordinatorAgent, GenesisAgent, FollowerAgent, WalletAgent
**Tasks**:
- Deploy agent agents
- Stop existing services via agents
- Update systemd configurations
- Setup central configuration
- Initialize agent communication channels

### 2. `02_genesis_authority_setup_agent.sh`
**Purpose**: Setup genesis authority node using agent agents
**Agent**: GenesisAgent, WalletAgent, CoordinatorAgent
**Tasks**:
- Initialize GenesisAgent
- Pull latest code
- Update environment configuration
- Create genesis block
- Create genesis wallets
- Start blockchain services
- Verify genesis state

### 3. `03_follower_node_setup_agent.sh`
**Purpose**: Setup follower node using agent agents
**Agent**: FollowerAgent, CoordinatorAgent
**Tasks**:
- Initialize FollowerAgent
- Connect to aitbc1 node
- Update follower configuration
- Start follower services
- Establish genesis connection
- Monitor and verify sync

### 4. `04_wallet_operations_agent.sh`
**Purpose**: Execute wallet operations across nodes using agent agents
**Agent**: WalletAgent, CoordinatorAgent
**Tasks**:
- Create cross-node wallets
- Fund wallets from genesis
- Execute cross-node transactions
- Verify transaction confirmations
- Test wallet switching

### 5. `05_complete_workflow_agent.sh`
**Purpose**: Orchestrate complete multi-node deployment using all agent agents
**Agent**: CoordinatorAgent (orchestrates all other agents)
**Tasks**:
- Execute all workflow phases
- Comprehensive verification
- Performance testing
- Network health checks
- Generate final reports

## agent Agent Architecture

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
# Run complete workflow with agent agents
./05_complete_workflow_agent.sh

# Run individual phases
./01_preflight_setup_agent.sh
./02_genesis_authority_setup_agent.sh
./03_follower_node_setup_agent.sh
./04_wallet_operations_agent.sh
```

### agent Commands
```bash
# Deploy agents
agent deploy --config /tmp/agent_agents.json

# Monitor agents
agent status --agent all

# Execute specific agent tasks
agent execute --agent GenesisAgent --task create_genesis_block
agent execute --agent FollowerAgent --task sync_with_genesis
agent execute --agent WalletAgent --task create_cross_node_wallets

# Generate reports
agent report --workflow multi_node --format json
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
- **Preflight Report**: `/tmp/agent_preflight_report.json`
- **Genesis Report**: `/tmp/agent_genesis_report.json`
- **Follower Report**: `/tmp/agent_follower_report.json`
- **Wallet Report**: `/tmp/agent_wallet_report.json`
- **Complete Report**: `/tmp/agent_complete_report.json`

### Monitoring Commands
```bash
# Monitor agent status
agent monitor --agent all

# Monitor workflow progress
agent monitor --workflow multi_node --real-time

# Check agent health
agent health --agent all
```

## Troubleshooting

### Common Issues

#### agent CLI Not Found
```bash
# Install agent
pip install agent-agent

# Or use mock mode (development)
export agent_MOCK_MODE=1
```

#### Agent Communication Failure
```bash
# Check agent status
agent status --agent all

# Restart communication
agent restart --communication

# Verify network connectivity
ping -c 1 aitbc1
```

#### Service Start Failures
```bash
# Check service logs via agents
agent execute --agent GenesisAgent --task show_service_logs

# Manual service check
systemctl status aitbc-blockchain-node.service
```

### Debug Mode
```bash
# Enable debug logging
export agent_DEBUG=1

# Run with verbose output
./05_complete_workflow_agent.sh --verbose

# Check agent logs
agent logs --agent all --tail 50
```

## Comparison with Manual Scripts

| Feature | Manual Scripts | agent Scripts |
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
- agent CLI installed
- SSH access to both nodes (aitbc, aitbc1)
- Python virtual environment at `/opt/aitbc/venv`
- AITBC CLI tool available
- Network connectivity between nodes

### agent Installation
```bash
# Install agent
pip install agent-agent

# Verify installation
agent --version

# Initialize agent
agent init --workspace /opt/aitbc
```

## Next Steps

1. **Run the complete workflow**: `./05_complete_workflow_agent.sh`
2. **Monitor agent activity**: `agent monitor --agent all`
3. **Verify deployment**: Check generated reports
4. **Test operations**: Execute test transactions
5. **Scale deployment**: Add more nodes and agents

## Support

For issues with agent scripts:
1. Check agent status: `agent status --agent all`
2. Review agent logs: `agent logs --agent all`
3. Verify network connectivity
4. Check agent configuration
5. Run in debug mode for detailed logging
