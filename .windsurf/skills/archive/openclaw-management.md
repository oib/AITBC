---
description: hermes agent management and coordination capabilities
title: hermes Agent Management Skill
version: 1.0
---

# hermes Agent Management Skill

This skill provides comprehensive hermes agent management, communication, and coordination capabilities. Focus on agent operations, session management, and cross-agent workflows.

## Current Active hermes Skills

This archived management skill is now represented by the following active atomic skill files:

- **`hermes-agent-communicator.md`** — agent message handling and responses
- **`hermes-session-manager.md`** — session creation and context management
- **`hermes-coordination-orchestrator.md`** — multi-agent workflow coordination
- **`hermes-performance-optimizer.md`** — agent performance tuning and optimization
- **`hermes-error-handler.md`** — error detection and recovery procedures
- **`hermes-agent-testing-skill.md`** — agent communication validation and performance testing

## Prerequisites

- hermes 2026.3.24+ installed and gateway running
- Agent workspace configured: `~/.hermes/workspace/`
- Network connectivity for multi-agent coordination

## Critical: Correct hermes Syntax

### Agent Commands
```bash
# CORRECT — always use --message (long form), not -m
hermes agent --agent main --message "Your task here" --thinking medium

# Session-based communication (maintains context across calls)
SESSION_ID="workflow-$(date +%s)"
hermes agent --agent main --session-id $SESSION_ID --message "Initialize task" --thinking low
hermes agent --agent main --session-id $SESSION_ID --message "Continue task" --thinking medium

# Thinking levels: off | minimal | low | medium | high | xhigh
```

> **WARNING**: The `-m` short form does NOT work reliably. Always use `--message`.
> **WARNING**: `--session-id` is required to maintain conversation context across multiple agent calls.

### Agent Status and Management
```bash
# Check agent status
hermes status --agent all
hermes status --agent main

# List available agents
hermes list --agents

# Agent workspace management
hermes workspace --setup
hermes workspace --status
```

## Agent Communication Patterns

### Single Agent Tasks
```bash
# Simple task execution
hermes agent --agent main --message "Analyze the system logs and report any errors" --thinking high

# Task with specific parameters
hermes agent --agent main --message "Process this data: /path/to/data.csv" --thinking medium --parameters "format:csv,mode:analyze"
```

### Session-Based Workflows
```bash
# Initialize session
SESSION_ID="data-analysis-$(date +%s)"

# Step 1: Data collection
hermes agent --agent main --session-id $SESSION_ID --message "Collect data from API endpoints" --thinking low

# Step 2: Data processing  
hermes agent --agent main --session-id $SESSION_ID --message "Process collected data and generate insights" --thinking medium

# Step 3: Report generation
hermes agent --agent main --session-id $SESSION_ID --message "Create comprehensive report with visualizations" --thinking high
```

### Multi-Agent Coordination
```bash
# Coordinator agent manages workflow
hermes agent --agent coordinator --message "Coordinate data processing across multiple agents" --thinking high

# Worker agents execute specific tasks
hermes agent --agent worker-1 --message "Process dataset A" --thinking medium
hermes agent --agent worker-2 --message "Process dataset B" --thinking medium

# Aggregator combines results
hermes agent --agent aggregator --message "Combine results from worker-1 and worker-2" --thinking high
```

## Agent Types and Roles

### Coordinator Agent
```bash
# Setup coordinator for complex workflows
hermes agent --agent coordinator --message "Initialize as workflow coordinator. Manage task distribution, monitor progress, aggregate results." --thinking high

# Use coordinator for orchestration
hermes agent --agent coordinator --message "Orchestrate data pipeline: extract → transform → load → validate" --thinking high
```

### Worker Agent
```bash
# Setup worker for specific tasks
hermes agent --agent worker --message "Initialize as data processing worker. Execute assigned tasks efficiently." --thinking medium

# Assign specific work
hermes agent --agent worker --message "Process customer data file: /data/customers.json" --thinking medium
```

### Monitor Agent
```bash
# Setup monitor for oversight
hermes agent --agent monitor --message "Initialize as system monitor. Track performance, detect anomalies, report status." --thinking low

# Continuous monitoring
hermes agent --agent monitor --message "Monitor system health and report any issues" --thinking minimal
```

## Agent Workflows

### Data Processing Workflow
```bash
SESSION_ID="data-pipeline-$(date +%s)"

# Phase 1: Data Extraction
hermes agent --agent extractor --session-id $SESSION_ID --message "Extract data from sources" --thinking medium

# Phase 2: Data Transformation
hermes agent --agent transformer --session-id $SESSION_ID --message "Transform extracted data" --thinking medium

# Phase 3: Data Loading
hermes agent --agent loader --session-id $SESSION_ID --message "Load transformed data to destination" --thinking medium

# Phase 4: Validation
hermes agent --agent validator --session-id $SESSION_ID --message "Validate loaded data integrity" --thinking high
```

### Monitoring Workflow
```bash
SESSION_ID="monitoring-$(date +%s)"

# Continuous monitoring loop
while true; do
    hermes agent --agent monitor --session-id $SESSION_ID --message "Check system health" --thinking minimal
    sleep 300  # Check every 5 minutes
done
```

### Analysis Workflow
```bash
SESSION_ID="analysis-$(date +%s)"

# Initial analysis
hermes agent --agent analyst --session-id $SESSION_ID --message "Perform initial data analysis" --thinking high

# Deep dive analysis
hermes agent --agent analyst --session-id $SESSION_ID --message "Deep dive into anomalies and patterns" --thinking high

# Report generation
hermes agent --agent analyst --session-id $SESSION_ID --message "Generate comprehensive analysis report" --thinking high
```

## Agent Configuration

### Agent Parameters
```bash
# Agent with specific parameters
hermes agent --agent main --message "Process data" --thinking medium \
    --parameters "input_format:json,output_format:csv,mode:batch"

# Agent with timeout
hermes agent --agent main --message "Long running task" --thinking high \
    --parameters "timeout:3600,retry_count:3"

# Agent with resource constraints
hermes agent --agent main --message "Resource-intensive task" --thinking high \
    --parameters "max_memory:4GB,max_cpu:2,max_duration:1800"
```

### Agent Context Management
```bash
# Set initial context
hermes agent --agent main --message "Initialize with context: data_analysis_v2" --thinking low \
    --context "project:data_analysis,version:2.0,dataset:customer_data"

# Maintain context across calls
hermes agent --agent main --session-id $SESSION_ID --message "Continue with previous context" --thinking medium

# Update context
hermes agent --agent main --session-id $SESSION_ID --message "Update context: new_phase" --thinking medium \
    --context-update "phase:processing,status:active"
```

## Agent Communication

### Cross-Agent Messaging
```bash
# Agent A sends message to Agent B
hermes agent --agent agent-a --message "Send results to agent-b" --thinking medium \
    --send-to "agent-b" --message-type "results"

# Agent B receives and processes
hermes agent --agent agent-b --message "Process received results" --thinking medium \
    --receive-from "agent-a"
```

### Agent Collaboration
```bash
# Setup collaboration team
TEAM_ID="team-analytics-$(date +%s)"

# Team leader coordination
hermes agent --agent team-lead --session-id $TEAM_ID --message "Coordinate team analytics workflow" --thinking high

# Team member tasks
hermes agent --agent analyst-1 --session-id $TEAM_ID --message "Analyze customer segment A" --thinking high
hermes agent --agent analyst-2 --session-id $TEAM_ID --message "Analyze customer segment B" --thinking high

# Team consolidation
hermes agent --agent team-lead --session-id $TEAM_ID --message "Consolidate team analysis results" --thinking high
```

## Agent Error Handling

### Error Recovery
```bash
# Agent with error handling
hermes agent --agent main --message "Process data with error handling" --thinking medium \
    --parameters "error_handling:retry_on_failure,max_retries:3,fallback_mode:graceful_degradation"

# Monitor agent errors
hermes agent --agent monitor --message "Check for agent errors and report" --thinking low \
    --parameters "check_type:error_log,alert_threshold:5"
```

### Agent Debugging
```bash
# Debug mode
hermes agent --agent main --message "Debug task execution" --thinking high \
    --parameters "debug:true,log_level:verbose,trace_execution:true"

# Agent state inspection
hermes agent --agent main --message "Report current state and context" --thinking low \
    --parameters "report_type:state,include_context:true"
```

## Agent Performance Optimization

### Efficient Agent Usage
```bash
# Batch processing
hermes agent --agent processor --message "Process data in batches" --thinking medium \
    --parameters "batch_size:100,parallel_processing:true"

# Resource optimization
hermes agent --agent optimizer --message "Optimize resource usage" --thinking high \
    --parameters "memory_efficiency:true,cpu_optimization:true"
```

### Agent Scaling
```bash
# Scale out work
for i in {1..5}; do
    hermes agent --agent worker-$i --message "Process batch $i" --thinking medium &
done

# Scale in coordination
hermes agent --agent coordinator --message "Coordinate scaled-out workers" --thinking high
```

## Agent Security

### Secure Agent Operations
```bash
# Agent with security constraints
hermes agent --agent secure-agent --message "Process sensitive data" --thinking high \
    --parameters "security_level:high,data_encryption:true,access_log:true"

# Agent authentication
hermes agent --agent authenticated-agent --message "Authenticated operation" --thinking medium \
    --parameters "auth_required:true,token_expiry:3600"
```

## Agent Monitoring and Analytics

### Performance Monitoring
```bash
# Monitor agent performance
hermes agent --agent monitor --message "Monitor agent performance metrics" --thinking low \
    --parameters "metrics:cpu,memory,tasks_per_second,error_rate"

# Agent analytics
hermes agent --agent analytics --message "Generate agent performance report" --thinking medium \
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
hermes status --agent all

# Test agent communication
hermes agent --agent main --message "Ping test" --thinking minimal

# Check workspace
hermes workspace --status

# Verify agent configuration
hermes config --show --agent main
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

This hermes Agent Management skill provides the foundation for effective agent coordination, communication, and workflow orchestration across any domain or application.

## Quick Links to Current Active Skills

- **hermes Agent Communicator**: [../hermes-agent-communicator.md](../hermes-agent-communicator.md)
- **hermes Session Manager**: [../hermes-session-manager.md](../hermes-session-manager.md)
- **hermes Coordination Orchestrator**: [../hermes-coordination-orchestrator.md](../hermes-coordination-orchestrator.md)
- **hermes Performance Optimizer**: [../hermes-performance-optimizer.md](../hermes-performance-optimizer.md)
- **hermes Error Handler**: [../hermes-error-handler.md](../hermes-error-handler.md)
- **hermes Agent Testing Skill**: [../hermes-agent-testing-skill.md](../hermes-agent-testing-skill.md)
