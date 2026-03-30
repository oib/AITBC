---
description: OpenClaw agent functionality and coordination testing module
title: OpenClaw Agent Testing Module
version: 1.0
---

# OpenClaw Agent Testing Module

This module covers OpenClaw agent functionality testing, multi-agent coordination, session management, and agent workflow validation.

## Prerequisites

### Required Setup
- Working directory: `/opt/aitbc`
- OpenClaw 2026.3.24+ installed
- OpenClaw gateway running
- Basic Testing Module completed

### Environment Setup
```bash
cd /opt/aitbc
source venv/bin/activate
openclaw --version
openclaw gateway status
```

## 1. OpenClaw Agent Basic Testing

### Agent Registration and Status
```bash
# Check OpenClaw gateway status
openclaw gateway status

# List available agents
openclaw agent list

# Check agent capabilities
openclaw agent --agent GenesisAgent --session-id test --message "Status check" --thinking low
```

### Expected Results
- Gateway should be running and responsive
- Agent list should show available agents
- Agent should respond to basic messages

### Troubleshooting Agent Issues
```bash
# Restart OpenClaw gateway
sudo systemctl restart openclaw-gateway

# Check gateway logs
sudo journalctl -u openclaw-gateway -f

# Verify agent configuration
openclaw config show
```

## 2. Single Agent Testing

### Genesis Agent Testing
```bash
# Test Genesis Agent with different thinking levels
SESSION_ID="genesis-test-$(date +%s)"

echo "Testing Genesis Agent with minimal thinking..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Test message - minimal thinking" --thinking minimal

echo "Testing Genesis Agent with low thinking..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Test message - low thinking" --thinking low

echo "Testing Genesis Agent with medium thinking..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Test message - medium thinking" --thinking medium

echo "Testing Genesis Agent with high thinking..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Test message - high thinking" --thinking high
```

### Follower Agent Testing
```bash
# Test Follower Agent
SESSION_ID="follower-test-$(date +%s)"

echo "Testing Follower Agent..."
openclaw agent --agent FollowerAgent --session-id $SESSION_ID --message "Test follower agent response" --thinking low

# Test follower agent coordination
openclaw agent --agent FollowerAgent --session-id $SESSION_ID --message "Coordinate with genesis node" --thinking medium
```

### Coordinator Agent Testing
```bash
# Test Coordinator Agent
SESSION_ID="coordinator-test-$(date +%s)"

echo "Testing Coordinator Agent..."
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID --message "Test coordination capabilities" --thinking high

# Test multi-agent coordination
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID --message "Coordinate multi-agent workflow" --thinking high
```

## 3. Multi-Agent Coordination Testing

### Cross-Agent Communication
```bash
# Test cross-agent communication
SESSION_ID="cross-agent-$(date +%s)"

# Genesis agent initiates
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Initiating cross-agent coordination test" --thinking high

# Follower agent responds
openclaw agent --agent FollowerAgent --session-id $SESSION_ID --message "Responding to genesis agent coordination" --thinking medium

# Coordinator agent orchestrates
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID --message "Orchestrating multi-agent coordination" --thinking high
```

### Session Management Testing
```bash
# Test session persistence
SESSION_ID="session-test-$(date +%s)"

# Multiple messages in same session
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "First message in session" --thinking low
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Second message in session" --thinking low
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Third message in session" --thinking low

# Test session with different agents
openclaw agent --agent FollowerAgent --session-id $SESSION_ID --message "Follower response in same session" --thinking medium
```

## 4. Advanced Agent Capabilities Testing

### AI Workflow Orchestration Testing
```bash
# Test AI workflow orchestration
SESSION_ID="ai-workflow-$(date +%s)"

# Genesis agent designs complex AI pipeline
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "Design complex AI pipeline for medical diagnosis with parallel processing and error handling" \
    --thinking high

# Follower agent participates in pipeline
openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "Participate in complex AI pipeline execution with resource monitoring" \
    --thinking medium

# Coordinator agent orchestrates workflow
openclaw agent --agent CoordinatorAgent --session-id $SESSION_ID \
    --message "Orchestrate complex AI pipeline execution across multiple agents" \
    --thinking high
```

### Multi-Modal AI Processing Testing
```bash
# Test multi-modal AI coordination
SESSION_ID="multimodal-$(date +%s)"

# Genesis agent designs multi-modal system
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "Design multi-modal AI system for customer feedback analysis with cross-modal attention" \
    --thinking high

# Follower agent handles specific modality
openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "Handle text analysis modality in multi-modal AI system" \
    --thinking medium
```

### Resource Optimization Testing
```bash
# Test resource optimization coordination
SESSION_ID="resource-opt-$(date +%s)"

# Genesis agent optimizes resources
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "Optimize GPU resource allocation for AI service provider with demand forecasting" \
    --thinking high

# Follower agent monitors resources
openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "Monitor resource utilization and report optimization opportunities" \
    --thinking medium
```

## 5. Agent Performance Testing

### Response Time Testing
```bash
# Test agent response times
SESSION_ID="perf-test-$(date +%s)"

echo "Testing agent response times..."

# Measure Genesis Agent response time
start_time=$(date +%s.%N)
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Quick response test" --thinking low
end_time=$(date +%s.%N)
genesis_time=$(echo "$end_time - $start_time" | bc)
echo "Genesis Agent response time: ${genesis_time}s"

# Measure Follower Agent response time
start_time=$(date +%s.%N)
openclaw agent --agent FollowerAgent --session-id $SESSION_ID --message "Quick response test" --thinking low
end_time=$(date +%s.%N)
follower_time=$(echo "$end_time - $start_time" | bc)
echo "Follower Agent response time: ${follower_time}s"
```

### Concurrent Session Testing
```bash
# Test multiple concurrent sessions
echo "Testing concurrent sessions..."

# Create multiple concurrent sessions
for i in {1..5}; do
    SESSION_ID="concurrent-$i-$(date +%s)"
    openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Concurrent test $i" --thinking low &
done

# Wait for all to complete
wait
echo "Concurrent session tests completed"
```

## 6. Agent Communication Testing

### Message Format Testing
```bash
# Test different message formats
SESSION_ID="format-test-$(date +%s)"

# Test short message
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Short" --thinking low

# Test medium message
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "This is a medium length message to test agent processing capabilities" --thinking low

# Test long message
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "This is a longer message that tests the agent's ability to process more complex requests and provide detailed responses. It should demonstrate the agent's capability to handle substantial input and generate comprehensive output." --thinking medium
```

### Special Character Testing
```bash
# Test special characters and formatting
SESSION_ID="special-test-$(date +%s)"

# Test special characters
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Test special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?" --thinking low

# Test code blocks
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Test code: \`print('Hello World')\` and \`\`\`python\ndef hello():\n    print('Hello')\`\`\`" --thinking low
```

## 7. Agent Error Handling Testing

### Invalid Agent Testing
```bash
# Test invalid agent names
echo "Testing invalid agent handling..."
openclaw agent --agent InvalidAgent --session-id test --message "Test message" --thinking low 2>/dev/null && echo "ERROR: Invalid agent accepted" || echo "✅ Invalid agent properly rejected"
```

### Invalid Session Testing
```bash
# Test session handling
echo "Testing session handling..."
openclaw agent --agent GenesisAgent --session-id "" --message "Test message" --thinking low 2>/dev/null && echo "ERROR: Empty session accepted" || echo "✅ Empty session properly rejected"
```

## 8. Agent Integration Testing

### AI Operations Integration
```bash
# Test agent integration with AI operations
SESSION_ID="ai-integration-$(date +%s)"

# Agent submits AI job
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "Submit AI job for text generation: Generate a short story about AI" \
    --thinking high

# Check if AI job was submitted
./aitbc-cli ai-ops --action status --job-id latest
```

### Blockchain Integration
```bash
# Test agent integration with blockchain
SESSION_ID="blockchain-integration-$(date +%s)"

# Agent checks blockchain status
openclaw agent --agent GenesisAgent --session-id $SESSION_ID \
    --message "Check blockchain status and report current height and network conditions" \
    --thinking medium
```

### Resource Management Integration
```bash
# Test agent integration with resource management
SESSION_ID="resource-integration-$(date +%s)"

# Agent monitors resources
openclaw agent --agent FollowerAgent --session-id $SESSION_ID \
    --message "Monitor system resources and report CPU, memory, and GPU utilization" \
    --thinking medium
```

## 9. Automated Agent Testing Script

### Comprehensive Agent Test Suite
```bash
#!/bin/bash
# automated_agent_tests.sh

echo "=== OpenClaw Agent Tests ==="

# Test gateway status
echo "Testing OpenClaw gateway..."
openclaw gateway status || exit 1

# Test basic agent functionality
echo "Testing basic agent functionality..."
SESSION_ID="auto-test-$(date +%s)"
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Automated test message" --thinking low || exit 1

# Test multi-agent coordination
echo "Testing multi-agent coordination..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Initiate coordination test" --thinking low || exit 1
openclaw agent --agent FollowerAgent --session-id $SESSION_ID --message "Respond to coordination test" --thinking low || exit 1

# Test session management
echo "Testing session management..."
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Session test message 1" --thinking low || exit 1
openclaw agent --agent GenesisAgent --session-id $SESSION_ID --message "Session test message 2" --thinking low || exit 1

echo "✅ All agent tests passed!"
```

## 10. Troubleshooting Guide

### Common Agent Issues

#### Gateway Not Running
```bash
# Problem: OpenClaw gateway not responding
# Solution: Start gateway service
sudo systemctl start openclaw-gateway
sudo systemctl status openclaw-gateway
```

#### Agent Not Responding
```bash
# Problem: Agent not responding to messages
# Solution: Check agent configuration and restart
openclaw agent list
sudo systemctl restart openclaw-gateway
```

#### Session Issues
```bash
# Problem: Session not persisting
# Solution: Check session storage
openclaw config show
openclaw gateway status
```

#### Performance Issues
```bash
# Problem: Slow agent response times
# Solution: Check system resources
free -h
df -h
ps aux | grep openclaw
```

## 11. Success Criteria

### Pass/Fail Criteria
- ✅ OpenClaw gateway running and responsive
- ✅ All agents respond to basic messages
- ✅ Multi-agent coordination working
- ✅ Session management functioning
- ✅ Advanced AI capabilities operational
- ✅ Integration with AI operations working
- ✅ Error handling functioning correctly

### Performance Benchmarks
- Gateway response time: <1 second
- Agent response time: <5 seconds
- Session creation: <1 second
- Multi-agent coordination: <10 seconds
- Advanced AI operations: <30 seconds

---

**Dependencies**: [Basic Testing Module](test-basic.md)  
**Next Module**: [AI Operations Testing](test-ai-operations.md) or [Advanced AI Testing](test-advanced-ai.md)
