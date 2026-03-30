---
description: Atomic AITBC AI operations testing with deterministic job submission and validation
title: aitbc-ai-operations-skill
version: 1.0
---

# AITBC AI Operations Skill

## Purpose
Test and validate AITBC AI job submission, processing, resource management, and AI service integration with deterministic performance metrics.

## Activation
Trigger when user requests AI operations testing: job submission validation, AI service testing, resource allocation testing, or AI job monitoring.

## Input
```json
{
  "operation": "test-job-submission|test-job-monitoring|test-resource-allocation|test-ai-services|comprehensive",
  "job_type": "inference|parallel|ensemble|multimodal|resource-allocation|performance-tuning",
  "test_wallet": "string (optional, default: genesis-ops)",
  "test_prompt": "string (optional for job submission)",
  "test_payment": "number (optional, default: 100)",
  "job_id": "string (optional for job monitoring)",
  "resource_type": "cpu|memory|gpu|all (optional for resource testing)",
  "timeout": "number (optional, default: 60 seconds)",
  "monitor_duration": "number (optional, default: 30 seconds)"
}
```

## Output
```json
{
  "summary": "AI operations testing completed successfully",
  "operation": "test-job-submission|test-job-monitoring|test-resource-allocation|test-ai-services|comprehensive",
  "test_results": {
    "job_submission": "boolean",
    "job_processing": "boolean",
    "resource_allocation": "boolean",
    "ai_service_integration": "boolean"
  },
  "job_details": {
    "job_id": "string",
    "job_type": "string",
    "submission_status": "success|failed",
    "processing_status": "pending|processing|completed|failed",
    "execution_time": "number"
  },
  "resource_metrics": {
    "cpu_utilization": "number",
    "memory_usage": "number",
    "gpu_utilization": "number",
    "allocation_efficiency": "number"
  },
  "service_status": {
    "ollama_service": "boolean",
    "coordinator_api": "boolean",
    "exchange_api": "boolean",
    "blockchain_rpc": "boolean"
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
- Validate AI operation parameters and job type
- Check AI service availability and health
- Verify wallet balance for job payments
- Assess resource availability and allocation

### 2. Plan
- Prepare AI job submission parameters
- Define testing sequence and validation criteria
- Set monitoring strategy for job processing
- Configure resource allocation testing

### 3. Execute
- Submit AI job with specified parameters
- Monitor job processing and completion
- Test resource allocation and utilization
- Validate AI service integration and performance

### 4. Validate
- Verify job submission success and processing
- Check resource allocation efficiency
- Validate AI service connectivity and performance
- Confirm overall AI operations health

## Constraints
- **MUST NOT** submit jobs without sufficient wallet balance
- **MUST NOT** exceed resource allocation limits
- **MUST** validate AI service availability before job submission
- **MUST** monitor jobs until completion or timeout
- **MUST** handle job failures gracefully with detailed diagnostics
- **MUST** provide deterministic performance metrics

## Environment Assumptions
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- AI services operational (Ollama, coordinator, exchange)
- Sufficient wallet balance for job payments
- Resource allocation system functional
- Default test wallet: "genesis-ops"

## Error Handling
- Job submission failures → Return submission error and wallet status
- Service unavailability → Return service health and restart recommendations
- Resource allocation failures → Return resource diagnostics and optimization suggestions
- Job processing timeouts → Return timeout details and troubleshooting steps

## Example Usage Prompt

```
Run comprehensive AI operations testing including job submission, processing, resource allocation, and AI service integration validation
```

## Expected Output Example

```json
{
  "summary": "Comprehensive AI operations testing completed with all systems operational",
  "operation": "comprehensive",
  "test_results": {
    "job_submission": true,
    "job_processing": true,
    "resource_allocation": true,
    "ai_service_integration": true
  },
  "job_details": {
    "job_id": "ai_job_1774884000",
    "job_type": "inference",
    "submission_status": "success",
    "processing_status": "completed",
    "execution_time": 15.2
  },
  "resource_metrics": {
    "cpu_utilization": 45.2,
    "memory_usage": 2.1,
    "gpu_utilization": 78.5,
    "allocation_efficiency": 92.3
  },
  "service_status": {
    "ollama_service": true,
    "coordinator_api": true,
    "exchange_api": true,
    "blockchain_rpc": true
  },
  "issues": [],
  "recommendations": ["All AI services operational", "Resource allocation optimal", "Job processing efficient"],
  "confidence": 1.0,
  "execution_time": 45.8,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Simple job status checking
- Basic AI service health checks
- Quick resource allocation testing

**Reasoning Model** (Claude Sonnet, GPT-4)
- Comprehensive AI operations testing
- Job submission and monitoring validation
- Resource allocation optimization analysis
- Complex AI service integration testing

**Coding Model** (Claude Sonnet, GPT-4)
- AI job parameter optimization
- Resource allocation algorithm testing
- Performance tuning recommendations

## Performance Notes
- **Execution Time**: 10-30 seconds for basic tests, 30-90 seconds for comprehensive testing
- **Memory Usage**: <200MB for AI operations testing
- **Network Requirements**: AI service connectivity (Ollama, coordinator, exchange)
- **Concurrency**: Safe for multiple simultaneous AI operations tests
- **Job Monitoring**: Real-time job progress tracking and performance metrics
