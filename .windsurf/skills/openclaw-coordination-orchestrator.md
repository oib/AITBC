---
description: Atomic OpenClaw multi-agent workflow coordination with deterministic outputs
title: openclaw-coordination-orchestrator
version: 1.1
---

# OpenClaw Coordination Orchestrator

## Purpose
Coordinate multi-agent workflows, manage agent task distribution, and orchestrate complex operations across multiple OpenClaw agents.

## Activation
Trigger when user requests multi-agent coordination: task distribution, workflow orchestration, agent collaboration, or parallel execution management.

## Input
```json
{
  "operation": "distribute|orchestrate|collaborate|monitor",
  "agents": ["agent1", "agent2", "..."],
  "task_type": "analysis|execution|validation|testing",
  "workflow": "string (optional for orchestrate)",
  "parallel": "boolean (optional, default: true)"
}
```

## Output
```json
{
  "summary": "Multi-agent coordination completed successfully",
  "operation": "distribute|orchestrate|collaborate|monitor",
  "agents_assigned": ["agent1", "agent2", "..."],
  "task_distribution": {
    "agent1": "task_description",
    "agent2": "task_description"
  },
  "workflow_status": "active|completed|failed",
  "collaboration_results": {},
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate agent availability
- Check agent connectivity
- Assess task complexity
- Determine optimal distribution strategy

### 2. Plan
- Select coordination approach
- Define task allocation
- Set execution order
- Plan fallback mechanisms

### 3. Execute
- Distribute tasks to agents
- Monitor agent progress
- Coordinate inter-agent communication
- Aggregate results

### 4. Validate
- Verify task completion
- Check result consistency
- Validate workflow integrity
- Confirm agent satisfaction

## Constraints
- **MUST NOT** modify agent configurations without approval
- **MUST NOT** exceed 120 seconds for complex workflows
- **MUST** validate agent availability before distribution
- **MUST** handle agent failures gracefully
- **MUST** respect agent capacity limits

## Environment Assumptions
- OpenClaw agents operational and accessible
- Agent communication channels available
- Task queue system functional
- Agent status monitoring active
- Collaboration protocol established

## Error Handling
- Agent offline → Reassign task to available agent
- Task timeout → Retry with different agent
- Communication failure → Use fallback coordination
- Agent capacity exceeded → Queue task for later execution

## Example Usage Prompt

```
Orchestrate parallel analysis workflow across main and trading agents
```

## Expected Output Example

```json
{
  "summary": "Multi-agent workflow orchestrated successfully across 2 agents",
  "operation": "orchestrate",
  "agents_assigned": ["main", "trading"],
  "task_distribution": {
    "main": "Analyze blockchain state and transaction patterns",
    "trading": "Analyze marketplace pricing and order flow"
  },
  "workflow_status": "completed",
  "collaboration_results": {
    "main": {"status": "completed", "result": "analysis_complete"},
    "trading": {"status": "completed", "result": "analysis_complete"}
  },
  "issues": [],
  "recommendations": ["Consider adding GPU agent for compute-intensive analysis"],
  "confidence": 1.0,
  "execution_time": 45.2,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Reasoning Model** (Claude Sonnet, GPT-4)
- Complex workflow orchestration
- Task distribution strategy
- Agent capacity planning
- Collaboration protocol management

**Performance Notes**
- **Execution Time**: 10-60 seconds for distribution, 30-120 seconds for complex workflows
- **Memory Usage**: <200MB for coordination operations
- **Network Requirements**: Agent communication channels
- **Concurrency**: Safe for multiple parallel workflows
