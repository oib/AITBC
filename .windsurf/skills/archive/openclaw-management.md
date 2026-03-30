---
description: OpenClaw agent management and coordination capabilities
title: OpenClaw Agent Management Skill
version: 1.0
---

# OpenClaw Agent Management Skill

This skill provides comprehensive OpenClaw agent management, communication, and coordination capabilities. Focus on agent operations, session management, and cross-agent workflows.

## Prerequisites

- OpenClaw 2026.3.24+ installed and gateway running
- Agent workspace configured: `~/.openclaw/workspace/`
- Network connectivity for multi-agent coordination

## Critical: Correct OpenClaw Syntax

### Agent Commands
```bash
# CORRECT — always use --message (long form), not -m
openclaw agent --agent main --message "Your task here" --thinking medium

# Session-based communication (maintains context across calls)
SESSION_ID="workflow-$(date +%s)"
openclaw agent --agent main --session-id $SESSION_ID --message "Initialize task" --thinking low
openclaw agent --agent main --session-id $SESSION_ID --message "Continue task" --thinking medium

# Thinking levels: off | minimal | low | medium | high | xhigh
```

> **WARNING**: The `-m` short form does NOT work reliably. Always use `--message`.
> **WARNING**: `--session-id` is required to maintain conversation context across multiple agent calls.

### Agent Status and Management
```bash
# Check agent status
openclaw status --agent all
openclaw status --agent main

# List available agents
openclaw list --agents

# Agent workspace management
openclaw workspace --setup
openclaw workspace --status
```

## Agent Communication Patterns

### Single Agent Tasks
```bash
# Simple task execution
openclaw agent --agent main --message "Analyze the system logs and report any errors" --thinking high

# Task with specific parameters
openclaw agent --agent main --message "Process this data: /path/to/data.csv" --thinking medium --parameters "format:csv,mode:analyze"
```

### Session-Based Workflows
```bash
# Initialize session
SESSION_ID="data-analysis-$(date +%s)"

# Step 1: Data collection
openclaw agent --agent main --session-id $SESSION_ID --message "Collect data from API endpoints" --thinking low

# Step 2: Data processing  
openclaw agent --agent main --session-id $SESSION_ID --message "Process collected data and generate insights" --thinking medium

# Step 3: Report generation
openclaw agent --agent main --session-id $SESSION_ID --message "Create comprehensive report with visualizations" --thinking high
```

### Multi-Agent Coordination
```bash
# Coordinator agent manages workflow
openclaw agent --agent coordinator --message "Coordinate data processing across multiple agents" --thinking high

# Worker agents execute specific tasks
openclaw agent --agent worker-1 --message "Process dataset A" --thinking medium
openclaw agent --agent worker-2 --message "Process dataset B" --thinking medium

# Aggregator combines results
openclaw agent --agent aggregator --message "Combine results from worker-1 and worker-2" --thinking high
```

## Agent Types and Roles

### Coordinator Agent
```bash
# Setup coordinator for complex workflows
openclaw agent --agent coordinator --message "Initialize as workflow coordinator. Manage task distribution, monitor progress, aggregate results." --thinking high

# Use coordinator for orchestration
openclaw agent --agent coordinator --message "Orchestrate data pipeline: extract → transform → load → validate" --thinking high
```

### Worker Agent
```bash
# Setup worker for specific tasks
openclaw agent --agent worker --message "Initialize as data processing worker. Execute assigned tasks efficiently." --thinking medium

# Assign specific work
openclaw agent --agent worker --message "Process customer data file: /data/customers.json" --thinking medium
```

### Monitor Agent
```bash
# Setup monitor for oversight
openclaw agent --agent monitor --message "Initialize as system monitor. Track performance, detect anomalies, report status." --thinking low

# Continuous monitoring
openclaw agent --agent monitor --message "Monitor system health and report any issues" --thinking minimal
```

## Agent Workflows

### Data Processing Workflow
```bash
SESSION_ID="data-pipeline-$(date +%s)"

# Phase 1: Data Extraction
openclaw agent --agent extractor --session-id $SESSION_ID --message "Extract data from sources" --thinking medium

# Phase 2: Data Transformation
openclaw agent --agent transformer --session-id $SESSION_ID --message "Transform extracted data" --thinking medium

# Phase 3: Data Loading
openclaw agent --agent loader --session-id $SESSION_ID --message "Load transformed data to destination" --thinking medium

# Phase 4: Validation
openclaw agent --agent validator --session-id $SESSION_ID --message "Validate loaded data integrity" --thinking high
```

### Monitoring Workflow
```bash
SESSION_ID="monitoring-$(date +%s)"

# Continuous monitoring loop
while true; do
    openclaw agent --agent monitor --session-id $SESSION_ID --message "Check system health" --thinking minimal
    sleep 300  # Check every 5 minutes
done
```

### Analysis Workflow
```bash
SESSION_ID="analysis-$(date +%s)"

# Initial analysis
openclaw agent --agent analyst --session-id $SESSION_ID --message "Perform initial data analysis" --thinking high

# Deep dive analysis
openclaw agent --agent analyst --session-id $SESSION_ID --message "Deep dive into anomalies and patterns" --thinking high

# Report generation
openclaw agent --agent analyst --session-id $SESSION_ID --message "Generate comprehensive analysis report" --thinking high
```

## Agent Configuration

### Agent Parameters
```bash
# Agent with specific parameters
openclaw agent --agent main --message "Process data" --thinking medium \
    --parameters "input_format:json,output_format:csv,mode:batch"

# Agent with timeout
openclaw agent --agent main --message "Long running task" --thinking high \
    --parameters "timeout:3600,retry_count:3"

# Agent with resource constraints
openclaw agent --agent main --message "Resource-intensive task" --thinking high \
    --parameters "max_memory:4GB,max_cpu:2,max_duration:1800"
```

### Agent Context Management
```bash
# Set initial context
openclaw agent --agent main --message "Initialize with context: data_analysis_v2" --thinking low \
    --context "project:data_analysis,version:2.0,dataset:customer_data"

# Maintain context across calls
openclaw agent --agent main --session-id $SESSION_ID --message "Continue with previous context" --thinking medium

# Update context
openclaw agent --agent main --session-id $SESSION_ID --message "Update context: new_phase" --thinking medium \
    --context-update "phase:processing,status:active"
```

## Agent Communication

### Cross-Agent Messaging
```bash
# Agent A sends message to Agent B
openclaw agent --agent agent-a --message "Send results to agent-b" --thinking medium \
    --send-to "agent-b" --message-type "results"

# Agent B receives and processes
openclaw agent --agent agent-b --message "Process received results" --thinking medium \
    --receive-from "agent-a"
```

### Agent Collaboration
```bash
# Setup collaboration team
TEAM_ID="team-analytics-$(date +%s)"

# Team leader coordination
openclaw agent --agent team-lead --session-id $TEAM_ID --message "Coordinate team analytics workflow" --thinking high

# Team member tasks
openclaw agent --agent analyst-1 --session-id $TEAM_ID --message "Analyze customer segment A" --thinking high
openclaw agent --agent analyst-2 --session-id $TEAM_ID --message "Analyze customer segment B" --thinking high

# Team consolidation
openclaw agent --agent team-lead --session-id $TEAM_ID --message "Consolidate team analysis results" --thinking high
```

## Agent Error Handling

### Error Recovery
```bash
# Agent with error handling
openclaw agent --agent main --message "Process data with error handling" --thinking medium \
    --parameters "error_handling:retry_on_failure,max_retries:3,fallback_mode:graceful_degradation"

# Monitor agent errors
openclaw agent --agent monitor --message "Check for agent errors and report" --thinking low \
    --parameters "check_type:error_log,alert_threshold:5"
```

### Agent Debugging
```bash
# Debug mode
openclaw agent --agent main --message "Debug task execution" --thinking high \
    --parameters "debug:true,log_level:verbose,trace_execution:true"

# Agent state inspection
openclaw agent --agent main --message "Report current state and context" --thinking low \
    --parameters "report_type:state,include_context:true"
```

## Agent Performance Optimization

### Efficient Agent Usage
```bash
# Batch processing
openclaw agent --agent processor --message "Process data in batches" --thinking medium \
    --parameters "batch_size:100,parallel_processing:true"

# Resource optimization
openclaw agent --agent optimizer --message "Optimize resource usage" --thinking high \
    --parameters "memory_efficiency:true,cpu_optimization:true"
```

### Agent Scaling
```bash
# Scale out work
for i in {1..5}; do
    openclaw agent --agent worker-$i --message "Process batch $i" --thinking medium &
done

# Scale in coordination
openclaw agent --agent coordinator --message "Coordinate scaled-out workers" --thinking high
```

## Agent Security

### Secure Agent Operations
```bash
# Agent with security constraints
openclaw agent --agent secure-agent --message "Process sensitive data" --thinking high \
    --parameters "security_level:high,data_encryption:true,access_log:true"

# Agent authentication
openclaw agent --agent authenticated-agent --message "Authenticated operation" --thinking medium \
    --parameters "auth_required:true,token_expiry:3600"
```

## Agent Monitoring and Analytics

### Performance Monitoring
```bash
# Monitor agent performance
openclaw agent --agent monitor --message "Monitor agent performance metrics" --thinking low \
    --parameters "metrics:cpu,memory,tasks_per_second,error_rate"

# Agent analytics
openclaw agent --agent analytics --message "Generate agent performance report" --thinking medium \
    --parameters "report_type:performance,period:last_24h"
```

## Troubleshooting Agent Issues

### Common Agent Problems
1. **Session Loss**: Use consistent `--session-id` across calls
2. **Context Loss**: Maintain context with `--context` parameter
3. **Performance Issues**: Optimize `--thinking` level and task complexity
4. **Communication Failures**: Check agent status and network connectivity

### Debug Commands
```bash
# Check agent status
openclaw status --agent all

# Test agent communication
openclaw agent --agent main --message "Ping test" --thinking minimal

# Check workspace
openclaw workspace --status

# Verify agent configuration
openclaw config --show --agent main
```

## Best Practices

### Session Management
- Use meaningful session IDs: `task-type-$(date +%s)`
- Maintain context across related tasks
- Clean up sessions when workflows complete

### Thinking Level Optimization
- **off**: Simple, repetitive tasks
- **minimal**: Quick status checks, basic operations
- **low**: Data processing, routine analysis
- **medium**: Complex analysis, decision making
- **high**: Strategic planning, complex problem solving
- **xhigh**: Critical decisions, creative tasks

### Agent Organization
- Use descriptive agent names: `data-processor`, `monitor`, `coordinator`
- Group related agents in workflows
- Implement proper error handling and recovery

### Performance Tips
- Batch similar operations
- Use appropriate thinking levels
- Monitor agent resource usage
- Implement proper session cleanup

This OpenClaw Agent Management skill provides the foundation for effective agent coordination, communication, and workflow orchestration across any domain or application.
