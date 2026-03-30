---
description: Atomic OpenClaw agent testing with deterministic communication validation and performance metrics
title: openclaw-agent-testing-skill
version: 1.0
---

# OpenClaw Agent Testing Skill

## Purpose
Test and validate OpenClaw agent functionality, communication patterns, session management, and performance with deterministic validation metrics.

## Activation
Trigger when user requests OpenClaw agent testing: agent functionality validation, communication testing, session management testing, or agent performance analysis.

## Input
```json
{
  "operation": "test-agent-communication|test-session-management|test-agent-performance|test-multi-agent|comprehensive",
  "agent": "main|specific_agent_name (default: main)",
  "test_message": "string (optional for communication testing)",
  "session_id": "string (optional for session testing)",
  "thinking_level": "off|minimal|low|medium|high|xhigh",
  "test_duration": "number (optional, default: 60 seconds)",
  "message_count": "number (optional, default: 5)",
  "concurrent_agents": "number (optional, default: 2)"
}
```

## Output
```json
{
  "summary": "OpenClaw agent testing completed successfully",
  "operation": "test-agent-communication|test-session-management|test-agent-performance|test-multi-agent|comprehensive",
  "test_results": {
    "agent_communication": "boolean",
    "session_management": "boolean",
    "agent_performance": "boolean",
    "multi_agent_coordination": "boolean"
  },
  "agent_details": {
    "agent_name": "string",
    "agent_status": "online|offline|error",
    "response_time": "number",
    "message_success_rate": "number"
  },
  "communication_metrics": {
    "messages_sent": "number",
    "messages_received": "number",
    "average_response_time": "number",
    "communication_success_rate": "number"
  },
  "session_metrics": {
    "sessions_created": "number",
    "session_preservation": "boolean",
    "context_maintenance": "boolean",
    "session_duration": "number"
  },
  "performance_metrics": {
    "cpu_usage": "number",
    "memory_usage": "number",
    "response_latency": "number",
    "throughput": "number"
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
- Validate agent testing parameters and operation type
- Check OpenClaw service availability and health
- Verify agent availability and status
- Assess testing scope and requirements

### 2. Plan
- Prepare agent communication test scenarios
- Define session management testing strategy
- Set performance monitoring and validation criteria
- Configure multi-agent coordination tests

### 3. Execute
- Test agent communication with various thinking levels
- Validate session creation and context preservation
- Monitor agent performance and resource utilization
- Test multi-agent coordination and communication patterns

### 4. Validate
- Verify agent communication success and response quality
- Check session management effectiveness and context preservation
- Validate agent performance metrics and resource usage
- Confirm multi-agent coordination and communication patterns

## Constraints
- **MUST NOT** test unavailable agents without explicit request
- **MUST NOT** exceed message length limits (4000 characters)
- **MUST** validate thinking level compatibility
- **MUST** handle communication timeouts gracefully
- **MUST** preserve session context during testing
- **MUST** provide deterministic performance metrics

## Environment Assumptions
- OpenClaw 2026.3.24+ installed and gateway running
- Agent workspace configured at `~/.openclaw/workspace/`
- Network connectivity for agent communication
- Default agent available: "main"
- Session management functional

## Error Handling
- Agent unavailable → Return agent status and availability recommendations
- Communication timeout → Return timeout details and retry suggestions
- Session management failures → Return session diagnostics and recovery steps
- Performance issues → Return performance metrics and optimization recommendations

## Example Usage Prompt

```
Run comprehensive OpenClaw agent testing including communication, session management, performance, and multi-agent coordination validation
```

## Expected Output Example

```json
{
  "summary": "Comprehensive OpenClaw agent testing completed with all systems operational",
  "operation": "comprehensive",
  "test_results": {
    "agent_communication": true,
    "session_management": true,
    "agent_performance": true,
    "multi_agent_coordination": true
  },
  "agent_details": {
    "agent_name": "main",
    "agent_status": "online",
    "response_time": 2.3,
    "message_success_rate": 100.0
  },
  "communication_metrics": {
    "messages_sent": 5,
    "messages_received": 5,
    "average_response_time": 2.1,
    "communication_success_rate": 100.0
  },
  "session_metrics": {
    "sessions_created": 3,
    "session_preservation": true,
    "context_maintenance": true,
    "session_duration": 45.2
  },
  "performance_metrics": {
    "cpu_usage": 15.3,
    "memory_usage": 85.2,
    "response_latency": 2.1,
    "throughput": 2.4
  },
  "issues": [],
  "recommendations": ["All agents operational", "Communication latency optimal", "Session management effective"],
  "confidence": 1.0,
  "execution_time": 67.3,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Simple agent availability checking
- Basic communication testing with low thinking
- Quick agent status validation

**Reasoning Model** (Claude Sonnet, GPT-4)
- Comprehensive agent communication testing
- Session management validation and optimization
- Multi-agent coordination testing and analysis
- Complex agent performance diagnostics

**Coding Model** (Claude Sonnet, GPT-4)
- Agent performance optimization algorithms
- Communication pattern analysis and improvement
- Session management enhancement strategies

## Performance Notes
- **Execution Time**: 5-15 seconds for basic tests, 30-90 seconds for comprehensive testing
- **Memory Usage**: <150MB for agent testing operations
- **Network Requirements**: OpenClaw gateway connectivity
- **Concurrency**: Safe for multiple simultaneous agent tests with different agents
- **Session Management**: Automatic session creation and context preservation testing
