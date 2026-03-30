---
description: Atomic AITBC AI job operations with deterministic monitoring and optimization
title: aitbc-ai-operator
version: 1.0
---

# AITBC AI Operator

## Purpose
Submit, monitor, and optimize AITBC AI jobs with deterministic performance tracking and resource management.

## Activation
Trigger when user requests AI operations: job submission, status monitoring, results retrieval, or resource optimization.

## Input
```json
{
  "operation": "submit|status|results|list|optimize|cancel",
  "wallet": "string (for submit/optimize)",
  "job_type": "inference|parallel|ensemble|multimodal|resource-allocation|performance-tuning|economic-modeling|marketplace-strategy|investment-strategy",
  "prompt": "string (for submit)",
  "payment": "number (for submit)",
  "job_id": "string (for status/results/cancel)",
  "agent_id": "string (for optimize)",
  "cpu": "number (for optimize)",
  "memory": "number (for optimize)",
  "duration": "number (for optimize)",
  "limit": "number (optional for list)"
}
```

## Output
```json
{
  "summary": "AI operation completed successfully",
  "operation": "submit|status|results|list|optimize|cancel",
  "job_id": "string (for submit/status/results/cancel)",
  "job_type": "string",
  "status": "submitted|processing|completed|failed|cancelled",
  "progress": "number (0-100)",
  "estimated_time": "number (seconds)",
  "wallet": "string (for submit/optimize)",
  "payment": "number (for submit)",
  "result": "string (for results)",
  "jobs": "array (for list)",
  "resource_allocation": "object (for optimize)",
  "performance_metrics": "object",
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate AI job parameters
- Check wallet balance for payment
- Verify job type compatibility
- Assess resource requirements

### 2. Plan
- Calculate appropriate payment amount
- Prepare job submission parameters
- Set monitoring strategy for job tracking
- Define optimization criteria (if applicable)

### 3. Execute
- Execute AITBC CLI AI command
- Capture job ID and initial status
- Monitor job progress and completion
- Retrieve results upon completion
- Parse performance metrics

### 4. Validate
- Verify job submission success
- Check job status progression
- Validate result completeness
- Confirm resource allocation accuracy

## Constraints
- **MUST NOT** submit jobs without sufficient wallet balance
- **MUST NOT** exceed resource allocation limits
- **MUST** validate job type compatibility
- **MUST** monitor jobs until completion or timeout (300 seconds)
- **MUST** set minimum payment based on job type
- **MUST** validate prompt length (max 4000 characters)

## Environment Assumptions
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- AI services operational (Ollama, exchange, coordinator)
- Sufficient wallet balance for job payments
- Resource allocation system operational
- Job queue processing functional

## Error Handling
- Insufficient balance → Return error with required amount
- Invalid job type → Return job type validation error
- Service unavailable → Return service status and retry recommendations
- Job timeout → Return timeout status with troubleshooting steps

## Example Usage Prompt

```
Submit an AI job for customer feedback analysis using multimodal processing with payment 500 AIT from trading-wallet
```

## Expected Output Example

```json
{
  "summary": "Multimodal AI job submitted successfully for customer feedback analysis",
  "operation": "submit",
  "job_id": "ai_job_1774883000",
  "job_type": "multimodal",
  "status": "submitted",
  "progress": 0,
  "estimated_time": 45,
  "wallet": "trading-wallet",
  "payment": 500,
  "result": null,
  "jobs": null,
  "resource_allocation": null,
  "performance_metrics": null,
  "issues": [],
  "recommendations": ["Monitor job progress for completion", "Prepare to analyze multimodal results"],
  "confidence": 1.0,
  "execution_time": 3.1,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Job status checking
- Job listing
- Result retrieval for completed jobs

**Reasoning Model** (Claude Sonnet, GPT-4)
- Job submission with optimization
- Resource allocation optimization
- Complex AI job analysis
- Error diagnosis and recovery

**Coding Model** (Claude Sonnet, GPT-4)
- AI job parameter optimization
- Performance tuning recommendations
- Resource allocation algorithms

## Performance Notes
- **Execution Time**: 2-5 seconds for submit/list, 10-60 seconds for monitoring, 30-300 seconds for job completion
- **Memory Usage**: <200MB for AI operations
- **Network Requirements**: AI service connectivity (Ollama, exchange, coordinator)
- **Concurrency**: Safe for multiple simultaneous jobs from different wallets
- **Resource Monitoring**: Real-time job progress tracking and performance metrics
