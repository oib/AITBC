---
description: Atomic Ollama GPU inference testing with deterministic performance validation and benchmarking
title: ollama-gpu-testing-skill
version: 1.0
---

# Ollama GPU Testing Skill

## Purpose
Test and validate Ollama GPU inference performance, GPU provider integration, payment processing, and blockchain recording with deterministic benchmarking metrics.

## Activation
Trigger when user requests Ollama GPU testing: inference performance validation, GPU provider testing, payment processing validation, or end-to-end workflow testing.

## Input
```json
{
  "operation": "test-gpu-inference|test-payment-processing|test-blockchain-recording|test-end-to-end|comprehensive",
  "model_name": "string (optional, default: llama2)",
  "test_prompt": "string (optional for inference testing)",
  "test_wallet": "string (optional, default: test-client)",
  "payment_amount": "number (optional, default: 100)",
  "gpu_provider": "string (optional, default: aitbc-host-gpu-miner)",
  "benchmark_duration": "number (optional, default: 30 seconds)",
  "inference_count": "number (optional, default: 5)"
}
```

## Output
```json
{
  "summary": "Ollama GPU testing completed successfully",
  "operation": "test-gpu-inference|test-payment-processing|test-blockchain-recording|test-end-to-end|comprehensive",
  "test_results": {
    "gpu_inference": "boolean",
    "payment_processing": "boolean",
    "blockchain_recording": "boolean",
    "end_to_end_workflow": "boolean"
  },
  "inference_metrics": {
    "model_name": "string",
    "inference_time": "number",
    "tokens_per_second": "number",
    "gpu_utilization": "number",
    "memory_usage": "number",
    "inference_success_rate": "number"
  },
  "payment_details": {
    "wallet_balance_before": "number",
    "payment_amount": "number",
    "payment_status": "success|failed",
    "transaction_id": "string",
    "miner_payout": "number"
  },
  "blockchain_details": {
    "transaction_recorded": "boolean",
    "block_height": "number",
    "confirmations": "number",
    "recording_time": "number"
  },
  "gpu_provider_status": {
    "provider_online": "boolean",
    "gpu_available": "boolean",
    "provider_response_time": "number",
    "service_health": "boolean"
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
- Validate GPU testing parameters and operation type
- Check Ollama service availability and GPU status
- Verify wallet balance for payment processing
- Assess GPU provider availability and health

### 2. Plan
- Prepare GPU inference testing scenarios
- Define payment processing validation criteria
- Set blockchain recording verification strategy
- Configure end-to-end workflow testing

### 3. Execute
- Test Ollama GPU inference performance and benchmarks
- Validate payment processing and wallet transactions
- Verify blockchain recording and transaction confirmation
- Test complete end-to-end workflow integration

### 4. Validate
- Verify GPU inference performance metrics
- Check payment processing success and miner payouts
- Validate blockchain recording and transaction confirmation
- Confirm end-to-end workflow integration and performance

## Constraints
- **MUST NOT** submit inference jobs without sufficient wallet balance
- **MUST** validate Ollama service availability before testing
- **MUST** monitor GPU utilization during inference testing
- **MUST** handle payment processing failures gracefully
- **MUST** verify blockchain recording completion
- **MUST** provide deterministic performance benchmarks

## Environment Assumptions
- Ollama service running on port 11434
- GPU provider service operational (aitbc-host-gpu-miner)
- AITBC CLI accessible for payment and blockchain operations
- Test wallets configured with sufficient balance
- GPU resources available for inference testing

## Error Handling
- Ollama service unavailable → Return service status and restart recommendations
- GPU provider offline → Return provider status and troubleshooting steps
- Payment processing failures → Return payment diagnostics and wallet status
- Blockchain recording failures → Return blockchain status and verification steps

## Example Usage Prompt

```
Run comprehensive Ollama GPU testing including inference performance, payment processing, blockchain recording, and end-to-end workflow validation
```

## Expected Output Example

```json
{
  "summary": "Comprehensive Ollama GPU testing completed with optimal performance metrics",
  "operation": "comprehensive",
  "test_results": {
    "gpu_inference": true,
    "payment_processing": true,
    "blockchain_recording": true,
    "end_to_end_workflow": true
  },
  "inference_metrics": {
    "model_name": "llama2",
    "inference_time": 2.3,
    "tokens_per_second": 45.2,
    "gpu_utilization": 78.5,
    "memory_usage": 4.2,
    "inference_success_rate": 100.0
  },
  "payment_details": {
    "wallet_balance_before": 1000.0,
    "payment_amount": 100.0,
    "payment_status": "success",
    "transaction_id": "tx_7f8a9b2c3d4e5f6",
    "miner_payout": 95.0
  },
  "blockchain_details": {
    "transaction_recorded": true,
    "block_height": 12345,
    "confirmations": 1,
    "recording_time": 5.2
  },
  "gpu_provider_status": {
    "provider_online": true,
    "gpu_available": true,
    "provider_response_time": 1.2,
    "service_health": true
  },
  "issues": [],
  "recommendations": ["GPU inference optimal", "Payment processing efficient", "Blockchain recording reliable"],
  "confidence": 1.0,
  "execution_time": 67.8,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Basic GPU availability checking
- Simple inference performance testing
- Quick service health validation

**Reasoning Model** (Claude Sonnet, GPT-4)
- Comprehensive GPU benchmarking and performance analysis
- Payment processing validation and troubleshooting
- End-to-end workflow integration testing
- Complex GPU optimization recommendations

**Coding Model** (Claude Sonnet, GPT-4)
- GPU performance optimization algorithms
- Inference parameter tuning
- Benchmark analysis and improvement strategies

## Performance Notes
- **Execution Time**: 10-30 seconds for basic tests, 60-120 seconds for comprehensive testing
- **Memory Usage**: <300MB for GPU testing operations
- **Network Requirements**: Ollama service, GPU provider, blockchain RPC connectivity
- **Concurrency**: Safe for multiple simultaneous GPU tests with different models
- **Benchmarking**: Real-time performance metrics and optimization recommendations
