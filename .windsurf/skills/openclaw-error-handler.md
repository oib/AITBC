---
description: Atomic OpenClaw error detection and recovery procedures with deterministic outputs
title: openclaw-error-handler
version: 1.0
---

# OpenClaw Error Handler

## Purpose
Detect, diagnose, and recover from errors in OpenClaw agent operations with systematic error handling and recovery procedures.

## Activation
Trigger when user requests error handling: error diagnosis, recovery procedures, error analysis, or system health checks.

## Input
```json
{
  "operation": "detect|diagnose|recover|analyze",
  "agent": "agent_name",
  "error_type": "execution|communication|configuration|timeout|unknown",
  "error_context": "string (optional)",
  "recovery_strategy": "auto|manual|rollback|retry"
}
```

## Output
```json
{
  "summary": "Error handling operation completed successfully",
  "operation": "detect|diagnose|recover|analyze",
  "agent": "agent_name",
  "error_detected": {
    "type": "string",
    "severity": "critical|high|medium|low",
    "timestamp": "number",
    "context": "string"
  },
  "diagnosis": {
    "root_cause": "string",
    "affected_components": ["component1", "component2"],
    "impact_assessment": "string"
  },
  "recovery_applied": {
    "strategy": "string",
    "actions_taken": ["action1", "action2"],
    "success": "boolean"
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
- Scan agent logs for errors
- Identify error patterns
- Assess error severity
- Determine error scope

### 2. Diagnose
- Analyze root cause
- Trace error propagation
- Identify affected components
- Assess impact

### 3. Execute Recovery
- Select recovery strategy
- Apply recovery actions
- Monitor recovery progress
- Validate recovery success

### 4. Validate
- Verify error resolution
- Check system stability
- Validate agent functionality
- Confirm no side effects

## Constraints
- **MUST NOT** modify critical system files
- **MUST NOT** exceed 60 seconds for error diagnosis
- **MUST** preserve error logs for analysis
- **MUST** validate recovery before applying
- **MUST** rollback on recovery failure

## Environment Assumptions
- Agent logs accessible at `/var/log/aitbc/`
- Error tracking system functional
- Recovery procedures documented
- Agent state persistence available
- System monitoring active

## Error Handling
- Recovery failure → Attempt alternative recovery strategy
- Multiple errors → Prioritize by severity
- Unknown error type → Apply generic recovery procedure
- System instability → Emergency rollback

## Example Usage Prompt

```
Diagnose and recover from execution errors in main agent
```

## Expected Output Example

```json
{
  "summary": "Error diagnosed and recovered successfully in main agent",
  "operation": "recover",
  "agent": "main",
  "error_detected": {
    "type": "execution",
    "severity": "high",
    "timestamp": 1775811500,
    "context": "Transaction processing timeout during blockchain sync"
  },
  "diagnosis": {
    "root_cause": "Network latency causing P2P sync timeout",
    "affected_components": ["p2p_network", "transaction_processor"],
    "impact_assessment": "Delayed transaction processing, no data loss"
  },
  "recovery_applied": {
    "strategy": "retry",
    "actions_taken": ["Increased timeout threshold", "Retried transaction processing"],
    "success": true
  },
  "issues": [],
  "recommendations": ["Monitor network latency for future occurrences", "Consider implementing adaptive timeout"],
  "confidence": 1.0,
  "execution_time": 18.3,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Reasoning Model** (Claude Sonnet, GPT-4)
- Complex error diagnosis
- Root cause analysis
- Recovery strategy selection
- Impact assessment

**Performance Notes**
- **Execution Time**: 5-30 seconds for detection, 15-45 seconds for diagnosis, 10-60 seconds for recovery
- **Memory Usage**: <150MB for error handling operations
- **Network Requirements**: Agent communication for error context
- **Concurrency**: Safe for sequential error handling on different agents
