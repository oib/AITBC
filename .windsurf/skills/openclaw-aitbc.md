---
description: Legacy OpenClaw AITBC integration - see split skills for focused operations
title: OpenClaw AITBC Integration (Legacy)
version: 6.0 - DEPRECATED
---

# OpenClaw AITBC Integration (Legacy - See Split Skills)

⚠️ **This skill has been split into focused skills for better organization:**

## 📚 New Split Skills

### 1. OpenClaw Agent Management Skill
**File**: `openclaw-management.md`

**Focus**: Pure OpenClaw agent operations, communication, and coordination
- Agent creation and management
- Session-based workflows  
- Cross-agent communication
- Performance optimization
- Error handling and debugging

**Use for**: Agent orchestration, workflow coordination, multi-agent systems

### 2. AITBC Blockchain Operations Skill  
**File**: `aitbc-blockchain.md`

**Focus**: Pure AITBC blockchain operations and integration
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
# Mixed OpenClaw + AITBC operations
openclaw agent --agent main --message "Check blockchain and process data" --thinking high
cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli chain
```

**After (Split Skills)**:

**OpenClaw Agent Management**:
```bash
# Pure agent coordination
openclaw agent --agent coordinator --message "Coordinate blockchain monitoring workflow" --thinking high

# Agent workflow orchestration
SESSION_ID="blockchain-monitor-$(date +%s)"
openclaw agent --agent monitor --session-id $SESSION_ID --message "Monitor blockchain health" --thinking medium
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
   - OpenClaw: Agent coordination and workflow management
   - AITBC: Blockchain operations and data management

2. **Better Documentation Organization**
   - Each skill focuses on its domain expertise
   - Reduced cognitive load when learning
   - Easier maintenance and updates

3. **Improved Reusability**
   - OpenClaw skills can be used with any system
   - AITBC skills can be used with any agent framework
   - Modular combination possible

4. **Enhanced Searchability**
   - Find relevant commands faster
   - Domain-specific troubleshooting
   - Focused best practices

### When to Use Each Skill

**Use OpenClaw Agent Management Skill for**:
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
- Complete OpenClaw + AITBC integration
- Agent-driven blockchain operations
- Automated blockchain workflows
- Cross-node agent coordination

## Legacy Content (Deprecated)

The following content from the original combined skill is now deprecated and moved to the appropriate split skills:

- ~~Agent command syntax~~ → **OpenClaw Agent Management**
- ~~AITBC CLI commands~~ → **AITBC Blockchain Operations**  
- ~~AI operations~~ → **AITBC Blockchain Operations**
- ~~Blockchain coordination~~ → **AITBC Blockchain Operations**
- ~~Agent workflows~~ → **OpenClaw Agent Management**

## Migration Checklist

### ✅ Completed
- [x] Created OpenClaw Agent Management skill
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

### OpenClaw Agent Management
```bash
# Agent coordination
openclaw agent --agent coordinator --message "Coordinate workflow" --thinking high

# Session-based workflow
SESSION_ID="task-$(date +%s)"
openclaw agent --agent worker --session-id $SESSION_ID --message "Execute task" --thinking medium
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

## Quick Links to New Skills

- **OpenClaw Agent Management**: [openclaw-management.md](openclaw-management.md)
- **AITBC Blockchain Operations**: [aitbc-blockchain.md](aitbc-blockchain.md)
