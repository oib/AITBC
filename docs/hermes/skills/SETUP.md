# AITBC Skills Setup for Agent Systems

**Last Updated:** 2026-05-28

This document describes how to set up AITBC skills as loadable agent skills in `/root/.hermes/skills/`.

## Overview

The AITBC skill files in `docs/hermes/skills/` contain comprehensive operational knowledge for AITBC. To make them usable by agent systems, they need to be:

1. Symlinked into `/root/.hermes/skills/` with proper category organization
2. Enhanced with SKILL.yml frontmatter for agent discovery
3. Registered in the agent skills manifest

## Setup Script

Run the setup script to automatically configure agent skills:

```bash
/opt/aitbc/docs/hermes/skills/setup_agent_skills.sh
```

## Manual Setup

If you prefer manual setup:

### 1. Create Category Directory

```bash
mkdir -p /root/.hermes/skills/aitbc
```

### 2. Add Frontmatter to Each Skill

Each skill file needs YAML frontmatter at the top:

```yaml
---
name: aitbc-basic-operations
description: "Basic AITBC CLI operations, wallet management, and blockchain status checks"
version: 1.0.0
author: AITBC
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [aitbc, cli, wallet, blockchain, operations]
    category: aitbc
---
```

### 3. Symlink Skills

```bash
ln -s /opt/aitbc/docs/hermes/skills/aitbc-basic-operations.md /root/.hermes/skills/aitbc/aitbc-basic-operations.md
# Repeat for all skill files
```

### 4. Reload Agent Skills

```bash
hermes reload-skills
```

## Available Skills

- `aitbc-basic-operations.md` - Basic CLI operations, wallet management, blockchain status
- `aitbc-marketplace.md` - Marketplace operations, GPU provider registration, trading
- `aitbc-node-coordination.md` - Multi-node coordination, git synchronization, blockchain sync
- `aitbc-wallet-management.md` - Wallet creation, import/export, balance checks, deletion
- `aitbc-ai-operations.md` - AI job submission, monitoring, resource allocation, GPU testing
- `aitbc-blockchain-troubleshooting.md` - Blockchain troubleshooting, sync issues, P2P problems
- `aitbc-multi-node-operations.md` - Multi-node operations, git sync, service restart, blockchain sync
- `aitbc-cli.md` - CLI tool reference for training agents and workflow operations
- `aitbc.md` - Comprehensive AITBC reference

## Verification

After setup, verify skills are loaded:

```bash
hermes skills list | grep aitbc
```

## Usage

Once loaded, OWL will automatically invoke these skills when relevant AITBC tasks are encountered. The skills provide comprehensive operational knowledge for:
- CLI command usage
- Blockchain operations
- Marketplace interactions
- AI job management
- Troubleshooting procedures
- Multi-node coordination
