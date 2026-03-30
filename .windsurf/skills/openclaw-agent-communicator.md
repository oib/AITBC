---
description: Atomic OpenClaw agent communication with deterministic message handling and response validation
title: openclaw-agent-communicator
version: 1.0
---

# OpenClaw Agent Communicator

## Purpose
Handle OpenClaw agent message delivery, response processing, and communication validation with deterministic outcome tracking.

## Activation
Trigger when user requests agent communication: message sending, response analysis, or communication validation.

## Input
```json
{
  "operation": "send|receive|analyze|validate",
  "agent": "main|specific_agent_name",
  "message": "string (for send)",
  "session_id": "string (optional for send/validate)",
  "thinking_level": "off|minimal|low|medium|high|xhigh",
  "response": "string (for receive/analyze)",
  "expected_response": "string (optional for validate)",
  "timeout": "number (optional, default 30 seconds)",
  "context": "string (optional for send)"
}
```

## Output
```json
{
  "summary": "Agent communication operation completed successfully",
  "operation": "send|receive|analyze|validate",
  "agent": "string",
  "session_id": "string",
  "message": "string (for send)",
  "response": "string (for receive/analyze)",
  "thinking_level": "string",
  "response_time": "number",
  "response_quality": "number (0-1)",
  "context_preserved": "boolean",
  "communication_issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate agent availability
- Check message format and content
- Verify thinking level compatibility
- Assess communication requirements

### 2. Plan
- Prepare message parameters
- Set session management strategy
- Define response validation criteria
- Configure timeout handling

### 3. Execute
- Execute OpenClaw agent command
- Capture agent response
- Measure response time
- Analyze response quality

### 4. Validate
- Verify message delivery success
- Check response completeness
- Validate context preservation
- Assess communication effectiveness

## Constraints
- **MUST NOT** send messages to unavailable agents
- **MUST NOT** exceed message length limits (4000 characters)
- **MUST** validate thinking level compatibility
- **MUST** handle communication timeouts gracefully
- **MUST** preserve session context when specified
- **MUST** validate response format and content

## Environment Assumptions
- OpenClaw 2026.3.24+ installed and gateway running
- Agent workspace configured at `~/.openclaw/workspace/`
- Network connectivity for agent communication
- Default agent available: "main"
- Session management functional

## Error Handling
- Agent unavailable → Return agent status and availability recommendations
- Communication timeout → Return timeout details and retry suggestions
- Invalid thinking level → Return valid thinking level options
- Message too long → Return truncation recommendations

## Example Usage Prompt

```
Send message to main agent with medium thinking level: "Analyze the current blockchain status and provide optimization recommendations for better performance"
```

## Expected Output Example

```json
{
  "summary": "Message sent to main agent successfully with comprehensive blockchain analysis response",
  "operation": "send",
  "agent": "main",
  "session_id": "session_1774883100",
  "message": "Analyze the current blockchain status and provide optimization recommendations for better performance",
  "response": "Current blockchain status: Chain height 12345, active nodes 2, block time 15s. Optimization recommendations: 1) Increase block size for higher throughput, 2) Implement transaction batching, 3) Optimize consensus algorithm for faster finality.",
  "thinking_level": "medium",
  "response_time": 8.5,
  "response_quality": 0.9,
  "context_preserved": true,
  "communication_issues": [],
  "recommendations": ["Consider implementing suggested optimizations", "Monitor blockchain performance after changes", "Test optimizations in staging environment"],
  "confidence": 1.0,
  "execution_time": 8.7,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Simple message sending with low thinking
- Basic response validation
- Communication status checking

**Reasoning Model** (Claude Sonnet, GPT-4)
- Complex message sending with high thinking
- Response analysis and quality assessment
- Communication optimization recommendations
- Error diagnosis and recovery

## Performance Notes
- **Execution Time**: 1-3 seconds for simple messages, 5-15 seconds for complex analysis
- **Memory Usage**: <100MB for agent communication
- **Network Requirements**: OpenClaw gateway connectivity
- **Concurrency**: Safe for multiple simultaneous agent communications
- **Session Management**: Automatic context preservation across multiple messages
