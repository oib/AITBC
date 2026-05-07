---
description: Legacy Hermes AITBC integration - see split skills for focused operations
title: Hermes AITBC Integration (Legacy)
version: 6.0 - DEPRECATED
---

# Hermes AITBC Integration (Legacy - See Split Skills)

⚠️ **This skill has been split into focused skills for better organization:**

## 📚 Current Active Hermes Skills

This legacy bundle now maps to the current atomic Hermes skill files:

- **`hermes-agent-communicator.md`** — agent message handling and responses
- **`hermes-session-manager.md`** — session creation and context management
- **`hermes-coordination-orchestrator.md`** — multi-agent workflow coordination
- **`hermes-performance-optimizer.md`** — agent performance tuning and optimization
- **`hermes-error-handler.md`** — error detection and recovery procedures
- **`hermes-agent-testing-skill.md`** — agent communication validation and performance testing

### Archived Blockchain Companion
**File**: `aitbc-blockchain.md`

**Focus**: AITBC blockchain operations and integration retained as an archived companion
- Wallet management and transactions
- AI operations and marketplace
- Node coordination and monitoring
- Smart contract messaging
- Cross-node operations

**Use for**: Blockchain operations, AI jobs, marketplace participation, node management

## Migration Guide

### From Legacy to Split Skills

**Before (Legacy)**:
```bash
# Mixed Hermes + AITBC operations
hermes agent --agent main --message "Check blockchain and process data" --thinking high
cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli chain
```

**After (Split Skills)**:

**Hermes Agent Management**:
```bash
# Pure agent coordination
hermes agent --agent coordinator --message "Coordinate blockchain monitoring workflow" --thinking high

# Agent workflow orchestration
SESSION_ID="blockchain-monitor-$(date +%s)"
hermes agent --agent monitor --session-id $SESSION_ID --message "Monitor blockchain health" --thinking medium
```

**AITBC Blockchain Operations**:
```bash
# Pure blockchain operations
cd /opt/aitbc && source venv/bin/activate
./aitbc-cli chain
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Generate image" --payment 100
```

## Why the Split?

### Benefits of Focused Skills

1. **Clearer Separation of Concerns**
   - Hermes: Agent coordination and workflow management
   - AITBC: Blockchain operations and data management

2. **Better Documentation Organization**
   - Each skill focuses on its domain expertise
   - Reduced cognitive load when learning
   - Easier maintenance and updates

3. **Improved Reusability**
   - Hermes skills can be used with any system
   - AITBC skills can be used with any agent framework
   - Modular combination possible

4. **Enhanced Searchability**
   - Find relevant commands faster
   - Domain-specific troubleshooting
   - Focused best practices

### When to Use Each Skill

**Use Hermes Agent Management Skill for**:
- Multi-agent workflow coordination
- Agent communication patterns
- Session management and context
- Agent performance optimization
- Error handling and debugging

**Use AITBC Blockchain Operations Skill for**:
- Wallet and transaction management
- AI job submission and monitoring
- Marketplace operations
- Node health and synchronization
- Smart contract messaging

**Combine Both Skills for**:
- Complete Hermes + AITBC integration
- Agent-driven blockchain operations
- Automated blockchain workflows
- Cross-node agent coordination

## Legacy Content (Deprecated)

The following content from the original combined skill is now deprecated and moved to the appropriate split skills:

- ~~Agent command syntax~~ → **Hermes Agent Management**
- ~~AITBC CLI commands~~ → **AITBC Blockchain Operations**  
- ~~AI operations~~ → **AITBC Blockchain Operations**
- ~~Blockchain coordination~~ → **AITBC Blockchain Operations**
- ~~Agent workflows~~ → **Hermes Agent Management**

## Migration Checklist

### ✅ Completed
- [x] Created Hermes Agent Management skill
- [x] Created AITBC Blockchain Operations skill
- [x] Updated all command references
- [x] Added migration guide

### 🔄 In Progress
- [ ] Update workflow scripts to use split skills
- [ ] Update documentation references
- [ ] Test split skills independently

### 📋 Next Steps
- [ ] Remove legacy content after validation
- [ ] Update integration examples
- [ ] Create combined usage examples

## Quick Reference

### Hermes Agent Management
```bash
# Agent coordination
hermes agent --agent coordinator --message "Coordinate workflow" --thinking high

# Session-based workflow
SESSION_ID="task-$(date +%s)"
hermes agent --agent worker --session-id $SESSION_ID --message "Execute task" --thinking medium
```

### AITBC Blockchain Operations  
```bash
# Blockchain status
cd /opt/aitbc && source venv/bin/activate
./aitbc-cli chain

# AI operations
./aitbc-cli ai-submit --wallet wallet --type inference --prompt "Generate image" --payment 100
```

---

**Recommendation**: Use the new split skills for all new development. This legacy skill is maintained for backward compatibility but will be deprecated in future versions.

## Quick Links to Current Active Skills

- **Hermes Agent Communicator**: [../hermes-agent-communicator.md](../hermes-agent-communicator.md)
- **Hermes Session Manager**: [../hermes-session-manager.md](../hermes-session-manager.md)
- **Hermes Coordination Orchestrator**: [../hermes-coordination-orchestrator.md](../hermes-coordination-orchestrator.md)
- **Hermes Performance Optimizer**: [../hermes-performance-optimizer.md](../hermes-performance-optimizer.md)
- **Hermes Error Handler**: [../hermes-error-handler.md](../hermes-error-handler.md)
- **Hermes Agent Testing Skill**: [../hermes-agent-testing-skill.md](../hermes-agent-testing-skill.md)

## Archived Blockchain Companion

- **AITBC Blockchain Operations**: [aitbc-blockchain.md](aitbc-blockchain.md)
