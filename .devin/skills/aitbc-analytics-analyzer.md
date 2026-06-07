---
description: Atomic AITBC blockchain analytics and performance metrics with deterministic outputs
title: aitbc-analytics-analyzer
version: 1.1
---

# AITBC Analytics Analyzer

## Purpose
Analyze blockchain performance metrics, generate analytics reports, and provide insights on blockchain health and efficiency.

## Activation
Trigger when user requests analytics: performance metrics, blockchain health reports, transaction analysis, or system diagnostics.

## Input
```json
{
  "operation": "metrics|health|transactions|diagnostics",
  "time_range": "1h|24h|7d|30d (optional, default: 24h)",
  "node": "genesis|follower|all (optional, default: all)",
  "metric_type": "throughput|latency|block_time|mempool|all (optional)"
}
```

## Output
```json
{
  "summary": "Analytics analysis completed successfully",
  "operation": "metrics|health|transactions|diagnostics",
  "time_range": "string",
  "node": "genesis|follower|all",
  "metrics": {
    "block_height": "number",
    "block_time_avg": "number",
    "tx_throughput": "number",
    "mempool_size": "number",
    "p2p_connections": "number"
  },
  "health_status": "healthy|degraded|critical",
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate time range parameters
- Check node accessibility
- Verify log file availability
- Assess analytics requirements

### 2. Plan
- Select appropriate data sources
- Define metric collection strategy
- Prepare analysis parameters
- Set aggregation methods

### 3. Execute
- Query blockchain logs for metrics
- Calculate performance statistics
- Analyze transaction patterns
- Generate health assessment

### 4. Validate
- Verify metric accuracy
- Validate health status calculation
- Check data completeness
- Confirm analysis consistency

## Constraints
- **MUST NOT** access private keys or sensitive data
- **MUST NOT** exceed 45 seconds execution time
- **MUST** validate time range parameters
- **MUST** handle missing log data gracefully
- **MUST** aggregate metrics correctly across nodes

## Environment Assumptions
- Blockchain logs available at `/var/log/aitbc/`
- CLI accessible at `/opt/aitbc/aitbc-cli`
- Log rotation configured for historical data
- P2P network status queryable
- Mempool accessible via CLI

## Error Handling
- Missing log files → Return partial metrics with warning
- Log parsing errors → Return error with affected time range
- Node offline → Exclude from aggregate metrics
- Timeout during analysis → Return partial results

## Example Usage Prompt

```
Generate blockchain performance metrics for the last 24 hours on all nodes
```

## Expected Output Example

```json
{
  "summary": "Blockchain analytics analysis completed for 24h period",
  "operation": "metrics",
  "time_range": "24h",
  "node": "all",
  "metrics": {
    "block_height": 15234,
    "block_time_avg": 30.2,
    "tx_throughput": 15.3,
    "mempool_size": 15,
    "p2p_connections": 2
  },
  "health_status": "healthy",
  "issues": [],
  "recommendations": ["Block time within optimal range", "P2P connectivity stable"],
  "confidence": 1.0,
  "execution_time": 12.5,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Reasoning Model** (Claude Sonnet, GPT-4)
- Complex metric calculations and aggregations
- Health status assessment
- Performance trend analysis
- Diagnostic reasoning

**Performance Notes**
- **Execution Time**: 5-20 seconds for metrics, 10-30 seconds for diagnostics
- **Memory Usage**: <150MB for analytics operations
- **Network Requirements**: Local log access, CLI queries
- **Concurrency**: Safe for multiple concurrent analytics queries
