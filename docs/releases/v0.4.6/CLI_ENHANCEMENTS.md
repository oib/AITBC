# CLI Enhancements - v0.4.6

**Release**: v0.4.6
**Date**: June 4, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.6 introduces new CLI commands for AI job management, agent communication, and reputation management.

## AI Job Management (NEW)

```bash
# Submit AI job
aitbc ai submit --type inference --prompt "Generate text"

# List AI jobs
aitbc ai jobs --limit 20

# Get job status
aitbc ai status --job-id job_abc123

# List AI services
aitbc ai service list

# Check service status
aitbc ai service status --name whisper

# Test service endpoint
aitbc ai service test --name whisper

# Get job results
aitbc ai results --job-id job_abc123

# Cancel job
aitbc ai cancel --job-id job_abc123 --wallet wallet_name

# AI service statistics
aitbc ai stats

# Task distribution statistics
aitbc ai distribution-stats
```

## Agent Communication

```bash
# Discover agents
aitbc agent discover agents --capability whisper --min-health 0.8

# View inbox
aitbc agent inbox --agent-id agent_001 --unread-only

# Subscribe to topic
aitbc agent subscribe --agent-id agent_001 --topic "gpu_available"

# Create workflow
aitbc agent workflow create --name "pipeline" --steps-file workflow.json

# Execute workflow
aitbc agent workflow execute --workflow-id wf_abc123 --input-file inputs.json

# Get workflow status
aitbc agent workflow status --workflow-id wf_abc123

# List workflows
aitbc agent workflow list
```

## Reputation Management

```bash
aitbc reputation rate --agent agent_abc123 --rating 5

aitbc reputation review --agent agent_abc123 --rating 5 --review "Excellent"

aitbc reputation query --agent agent_abc123

aitbc reputation reviews --agent agent_abc123

aitbc reputation top --service whisper --limit 10
```

## New Commands

- ✅ `aitbc ai submit` — submit AI job (NEW)
- ✅ `aitbc ai jobs` — list AI jobs (NEW)
- ✅ `aitbc ai status` — show AI job status (NEW)
- ✅ `aitbc ai service list` — list AI services (NEW)
- ✅ `aitbc ai service status` — check service status (NEW)
- ✅ `aitbc ai service test` — test service endpoint (NEW)
- ✅ `aitbc ai results` — show job results (NEW)
- ✅ `aitbc ai cancel` — cancel AI job (NEW)
- ✅ `aitbc ai stats` — AI service statistics (NEW)
- ✅ `aitc ai distribution-stats` — task distribution stats (NEW)
- ✅ `aitbc agent discover agents` — discover agents by capability
- ✅ `aitbc agent inbox` — view agent inbox
- ✅ `aitbc agent subscribe` — subscribe to topic
- ✅ `aitbc agent workflow create` — create workflow
- ✅ `aitbc agent workflow execute` — execute workflow
- ✅ `aitbc agent workflow status` — get workflow status
- ✅ `aitbc agent workflow list` — list workflows

---

*Last Updated: 2026-06-04*
