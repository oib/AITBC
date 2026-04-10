---
description: Atomic OpenClaw agent performance tuning and optimization with deterministic outputs
title: openclaw-performance-optimizer
version: 1.0
---

# OpenClaw Performance Optimizer

## Purpose
Optimize agent performance, tune execution parameters, and improve efficiency for OpenClaw agents through systematic analysis and adjustment.

## Activation
Trigger when user requests performance optimization: agent tuning, parameter adjustment, efficiency improvements, or performance benchmarking.

## Input
```json
{
  "operation": "tune|benchmark|optimize|profile",
  "agent": "agent_name",
  "target": "speed|memory|throughput|latency|all",
  "parameters": {
    "max_tokens": "number (optional)",
    "temperature": "number (optional)",
    "timeout": "number (optional)"
  }
}
```

## Output
```json
{
  "summary": "Agent performance optimization completed successfully",
  "operation": "tune|benchmark|optimize|profile",
  "agent": "agent_name",
  "target": "speed|memory|throughput|latency|all",
  "before_metrics": {
    "execution_time": "number",
    "memory_usage": "number",
    "throughput": "number",
    "latency": "number"
  },
  "after_metrics": {
    "execution_time": "number",
    "memory_usage": "number",
    "throughput": "number",
    "latency": "number"
  },
  "improvement": {
    "speed": "percentage",
    "memory": "percentage",
    "throughput": "percentage",
    "latency": "percentage"
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
- Profile current agent performance
- Identify bottlenecks
- Assess optimization opportunities
- Validate agent state

### 2. Plan
- Select optimization strategy
- Define parameter adjustments
- Set performance targets
- Plan validation approach

### 3. Execute
- Apply parameter adjustments
- Run performance benchmarks
- Measure improvements
- Validate stability

### 4. Validate
- Verify performance gains
- Check for regressions
- Validate parameter stability
- Confirm agent functionality

## Constraints
- **MUST NOT** modify agent core functionality
- **MUST NOT** exceed 90 seconds for optimization
- **MUST** validate parameter ranges
- **MUST** preserve agent behavior
- **MUST** rollback on critical failures

## Environment Assumptions
- Agent operational and accessible
- Performance monitoring available
- Parameter configuration accessible
- Benchmarking tools available
- Agent state persistence functional

## Error Handling
- Parameter validation failure → Revert to previous parameters
- Performance regression → Rollback optimization
- Agent instability → Restore baseline configuration
- Timeout during optimization → Return partial results

## Example Usage Prompt

```
Optimize main agent for speed and memory efficiency
```

## Expected Output Example

```json
{
  "summary": "Main agent optimized for speed and memory efficiency",
  "operation": "optimize",
  "agent": "main",
  "target": "all",
  "before_metrics": {
    "execution_time": 15.2,
    "memory_usage": 250,
    "throughput": 8.5,
    "latency": 2.1
  },
  "after_metrics": {
    "execution_time": 11.8,
    "memory_usage": 180,
    "throughput": 12.3,
    "latency": 1.5
  },
  "improvement": {
    "speed": "22%",
    "memory": "28%",
    "throughput": "45%",
    "latency": "29%"
  },
  "issues": [],
  "recommendations": ["Consider further optimization for memory-intensive tasks"],
  "confidence": 1.0,
  "execution_time": 35.7,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Reasoning Model** (Claude Sonnet, GPT-4)
- Complex parameter optimization
- Performance analysis and tuning
- Benchmark interpretation
- Regression detection

**Performance Notes**
- **Execution Time**: 20-60 seconds for optimization, 5-15 seconds for benchmarking
- **Memory Usage**: <200MB for optimization operations
- **Network Requirements**: Agent communication for profiling
- **Concurrency**: Safe for sequential optimization of different agents
