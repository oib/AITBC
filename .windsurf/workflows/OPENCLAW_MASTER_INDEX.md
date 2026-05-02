---
description: Master index for OpenClaw workflows - links to all modules and provides navigation
title: OpenClaw Workflows - Master Index
version: 1.0
---

# OpenClaw Workflows - Master Index

This master index provides navigation to all OpenClaw agent workflows and documentation. Each workflow focuses on specific aspects of OpenClaw agent training, coordination, and testing.

## 📚 Module Overview

### 🎓 Agent Training Modules

#### Cross-Node Communication Training
**File**: `openclaw-cross-node-communication.md`
**Purpose**: Specialized training for agent-to-agent cross-node communication via AITBC blockchain
**Audience**: OpenClaw agents learning multi-node coordination
**Prerequisites**: Stage 2 of Mastery Plan, both nodes synchronized

**Key Topics**:
- Agent registration on multiple blockchain nodes
- Peer discovery across blockchain state
- Cross-node messaging via blockchain transactions
- Distributed task execution
- Event monitoring and message parsing

**Quick Start**:
```bash
cd /opt/aitbc/scripts/training
./openclaw_cross_node_comm.sh
```

---

### 🧪 Agent Testing Modules

#### Ollama GPU Provider Test (OpenClaw)
**File**: `ollama-gpu-test-openclaw.md`
**Purpose**: Complete end-to-end test for Ollama GPU inference jobs using OpenClaw agents
**Audience**: QA engineers, OpenClaw developers
**Prerequisites**: OpenClaw 2026.3.24+, all services running, enhanced CLI

**Key Topics**:
- Environment validation with OpenClaw agents
- Wallet setup and management
- Service health verification
- GPU test execution and monitoring
- Payment processing and validation
- Blockchain transaction recording
- Comprehensive test reporting

**Quick Start**:
```bash
SESSION_ID="ollama-gpu-test-$(date +%s)"
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Initialize complete Ollama GPU test workflow" \
    --thinking high
```

---

### 🤖 Agent Coordination Modules

#### Agent Coordination Plan Enhancement
**File**: `agent-coordination-enhancement.md`
**Purpose**: Advanced multi-agent communication patterns, distributed decision making, and scalable architectures
**Audience**: OpenClaw developers, system architects
**Prerequisites**: Advanced AI Teaching Plan completed

**Key Topics**:
- Hierarchical, peer-to-peer, and broadcast communication patterns
- Consensus-based and weighted decision making
- Microservices, load balancing, and federated architectures
- Multi-agent task orchestration
- Performance metrics and monitoring
- Implementation guidelines

**Quick Start**:
```bash
SESSION_ID="coordination-$(date +%s)"
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "BROADCAST: System-wide resource optimization initiated" \
    --thinking high
```

---

## 🗺️ Module Dependencies

```
Cross-Node Communication Training (Foundation)
├── Ollama GPU Provider Test (Testing)
└── Agent Coordination Enhancement (Advanced)
```

## 🚀 Recommended Learning Path

### For New OpenClaw Users
1. **Cross-Node Communication Training** - Learn basic multi-node messaging
2. **Ollama GPU Provider Test** - Practice agent-based testing
3. **Agent Coordination Enhancement** - Master advanced coordination

### For OpenClaw Developers
1. **Cross-Node Communication Training** - Understand multi-node architecture
2. **Agent Coordination Enhancement** - Master coordination patterns
3. **Ollama GPU Provider Test** - Learn testing methodology

### For System Architects
1. **Cross-Node Communication Training** - Understand distributed messaging
2. **Agent Coordination Enhancement** - Design scalable architectures
3. **Ollama GPU Provider Test** - Learn testing patterns

## 🎯 Quick Navigation

### By Task

| Task | Recommended Module |
|---|---|
| **Multi-Node Messaging** | Cross-Node Communication Training |
| **Agent-Based Testing** | Ollama GPU Provider Test |
| **Advanced Coordination** | Agent Coordination Enhancement |
| **Distributed Decision Making** | Agent Coordination Enhancement |
| **Performance Monitoring** | Agent Coordination Enhancement |

### By Role

| Role | Essential Modules |
|---|---|
| **OpenClaw Developer** | Cross-Node Communication Training, Agent Coordination Enhancement |
| **QA Engineer** | Ollama GPU Provider Test, Cross-Node Communication Training |
| **System Architect** | Agent Coordination Enhancement, Cross-Node Communication Training |
| **DevOps Engineer** | Ollama GPU Provider Test, Agent Coordination Enhancement |

### By Complexity

| Level | Modules |
|---|---|
| **Beginner** | Cross-Node Communication Training |
| **Intermediate** | Ollama GPU Provider Test |
| **Advanced** | Agent Coordination Enhancement |
| **Expert** | All modules |

## 🔍 Quick Reference Commands

### Cross-Node Communication
```bash
# Register agent on genesis node
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli agent create \
  --name "openclaw-genesis-commander" \
  --description "Primary coordinator agent" \
  --verification full

# Send cross-node message
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli agent message \
  --to $FOLLOWER_AGENT_ID \
  --content "{\"cmd\":\"STATUS_REPORT\",\"priority\":\"high\"}"
```

### Ollama GPU Testing
```bash
# Initialize test coordinator
SESSION_ID="ollama-test-$(date +%s)"
openclaw agent --agent test-coordinator --session-id $SESSION_ID \
    --message "Initialize Ollama GPU provider test workflow" \
    --thinking high

# Submit inference job
openclaw agent --agent client-agent --session-id $SESSION_ID \
    --message "Submit Ollama GPU inference job" \
    --parameters "prompt:What is the capital of France?,model:llama3.2:latest"
```

### Agent Coordination
```bash
# Hierarchical communication
SESSION_ID="hierarchy-$(date +%s)"
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "Broadcast: Execute distributed AI workflow" \
    --thinking high

# Consensus voting
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "VOTE $PROPOSAL_ID: YES - Dynamic allocation optimizes AI performance" \
    --thinking medium
```

## 📊 System Overview

### OpenClaw Architecture
```
OpenClaw Agent Ecosystem:
├── Genesis Node (aitbc) - Primary development server
├── Follower Node (aitbc1) - Secondary node
├── Agent Gateway - OpenClaw communication layer
├── Blockchain Messaging - Transaction-based agent communication
├── Smart Contracts - Agent messaging and governance
├── GPU Services - Ollama inference and resource management
└── Monitoring - Agent performance and coordination metrics
```

### Key Components
- **Agent Gateway**: OpenClaw communication and coordination
- **Blockchain Messaging**: Transaction-based cross-node communication
- **Smart Contracts**: Agent messaging, reputation, and governance
- **GPU Services**: Ollama inference, resource allocation
- **Monitoring**: Agent performance, communication metrics

## 🎯 Success Metrics

### Training Success
- [ ] Agents registered on multiple nodes
- [ ] Cross-node messaging functional
- [ ] Distributed task execution working
- [ ] Event monitoring operational

### Testing Success
- [ ] Environment validation passing
- [ ] GPU test execution successful
- [ ] Payment processing validated
- [ ] Blockchain recording verified

### Coordination Success
- [ ] Communication latency <100ms
- [ ] Decision accuracy >95%
- [ ] Scalability: 10+ concurrent agents
- [ ] Fault tolerance >99% availability

## 🔧 Troubleshooting Quick Reference

### Common Issues
| Issue | Module | Solution |
|---|---|---|
| Agent registration fails | Cross-Node Communication Training | Check node sync, verify wallet |
| Cross-node messages not delivered | Cross-Node Communication Training | Verify agent IDs, check blockchain sync |
| GPU test fails | Ollama GPU Provider Test | Check Ollama service, GPU availability |
| Coordination timeout | Agent Coordination Enhancement | Check agent gateway, session management |

### Emergency Procedures
1. **Agent Recovery**: Restart OpenClaw gateway, check agent status
2. **Network Recovery**: Check node connectivity, restart P2P service
3. **Blockchain Recovery**: Check node sync, verify transaction pool
4. **Service Recovery**: Restart Agent Coordinator, Ollama, GPU miner

## 📚 Additional Resources

### Documentation Files
- **OpenClaw Agent Capabilities**: `docs/openclaw/OPENCLAW_AGENT_CAPABILITIES_ADVANCED.md`
- **Agent Communication Guide**: `docs/openclaw/guides/openclaw_agent_fix_summary.md`
- **Messaging Implementation**: `docs/openclaw/guides/openclaw_messaging_implementation_guide.md`
- **Cross-Node Communication**: `docs/openclaw/guides/openclaw_cross_node_communication.md`

### Workflow Scripts
- **Cross-Node Training**: `/opt/aitbc/scripts/training/openclaw_cross_node_comm.sh`
- **Ollama GPU Test**: `ollama_gpu_test_openclaw.sh`
- **Agent Communication Fix**: `/opt/aitbc/scripts/workflow-openclaw/fix_agent_communication.sh`

## 🔄 Version History

### v1.0 (Current)
- Created master index for OpenClaw workflows
- Organized workflows by training, testing, and coordination
- Added navigation and learning paths
- Included quick reference commands and troubleshooting

## 🤝 Contributing

### Updating Documentation
1. Update specific module files
2. Update this master index if needed
3. Update cross-references between modules
4. Test all links and commands
5. Commit changes with descriptive message

### Module Creation
1. Follow established template structure
2. Include prerequisites and dependencies
3. Add quick start commands
4. Include troubleshooting section
5. Update this master index

---

**Note**: This master index is your starting point for all OpenClaw workflow operations. Choose the appropriate module based on your current task and expertise level.

For immediate help, see the **Cross-Node Communication Training** module for foundational knowledge, or the **Agent Coordination Enhancement** module for advanced patterns.
