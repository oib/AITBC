---
description: Atomic OpenClaw session management with deterministic context preservation and workflow coordination
title: openclaw-session-manager
version: 1.1
---

# OpenClaw Session Manager

## Purpose
Create, manage, and optimize OpenClaw agent sessions with deterministic context preservation and workflow coordination.

## Activation
Trigger when user requests session operations: creation, management, context analysis, or session optimization.

## Input
```json
{
  "operation": "create|list|analyze|optimize|cleanup|merge",
  "session_id": "string (for analyze/optimize/cleanup/merge)",
  "agent": "main|specific_agent_name (for create)",
  "context": "string (optional for create)",
  "duration": "number (optional for create, hours)",
  "max_messages": "number (optional for create)",
  "merge_sessions": "array (for merge)",
  "cleanup_criteria": "object (optional for cleanup)"
}
```

## Output
```json
{
  "summary": "Session operation completed successfully",
  "operation": "create|list|analyze|optimize|cleanup|merge",
  "session_id": "string",
  "agent": "string (for create)",
  "context": "string (for create/analyze)",
  "message_count": "number",
  "duration": "number",
  "session_health": "object (for analyze)",
  "optimization_recommendations": "array (for optimize)",
  "merged_sessions": "array (for merge)",
  "cleanup_results": "object (for cleanup)",
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate session parameters
- Check agent availability
- Assess context requirements
- Evaluate session management needs

### 2. Plan
- Design session strategy
- Set context preservation rules
- Define session boundaries
- Prepare optimization criteria

### 3. Execute
- Execute OpenClaw session operations
- Monitor session health
- Track context preservation
- Analyze session performance

### 4. Validate
- Verify session creation success
- Check context preservation effectiveness
- Validate session optimization results
- Confirm session cleanup completion

## Constraints
- **MUST NOT** create sessions without valid agent
- **MUST NOT** exceed session duration limits (24 hours)
- **MUST** preserve context integrity across operations
- **MUST** validate session ID format (alphanumeric, hyphens, underscores)
- **MUST** handle session cleanup gracefully
- **MUST** track session resource usage

## Environment Assumptions
- OpenClaw 2026.3.24+ installed and gateway running
- Agent workspace configured at `~/.openclaw/workspace/`
- Session storage functional
- Context preservation mechanisms operational
- Default session duration: 4 hours

## Error Handling
- Invalid agent → Return agent availability status
- Session creation failure → Return detailed error and troubleshooting
- Context loss → Return context recovery recommendations
- Session cleanup failure → Return cleanup status and manual steps

## Example Usage Prompt

```
Create a new session for main agent with context about blockchain optimization workflow, duration 6 hours, maximum 50 messages
```

## Expected Output Example

```json
{
  "summary": "Session created successfully for blockchain optimization workflow",
  "operation": "create",
  "session_id": "session_1774883200",
  "agent": "main",
  "context": "blockchain optimization workflow focusing on performance improvements and consensus algorithm enhancements",
  "message_count": 0,
  "duration": 6,
  "session_health": null,
  "optimization_recommendations": null,
  "merged_sessions": null,
  "cleanup_results": null,
  "issues": [],
  "recommendations": ["Start with blockchain status analysis", "Monitor session performance regularly", "Consider splitting complex workflows into multiple sessions"],
  "confidence": 1.0,
  "execution_time": 2.1,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Simple session creation
- Session listing
- Basic session status checking

**Reasoning Model** (Claude Sonnet, GPT-4)
- Complex session optimization
- Context analysis and preservation
- Session merging strategies
- Session health diagnostics

**Coding Model** (Claude Sonnet, GPT-4)
- Session optimization algorithms
- Context preservation mechanisms
- Session cleanup automation

## Performance Notes
- **Execution Time**: 1-3 seconds for create/list, 5-15 seconds for analysis/optimization
- **Memory Usage**: <150MB for session management
- **Network Requirements**: OpenClaw gateway connectivity
- **Concurrency**: Safe for multiple simultaneous sessions with different agents
- **Context Preservation**: Automatic context tracking and integrity validation
