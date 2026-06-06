---
description: Atomic AITBC marketplace operations with deterministic pricing and listing management
title: aitbc-marketplace-participant
version: 1.1
---

# AITBC Marketplace Participant

## Purpose
Create, manage, and optimize AITBC marketplace listings with deterministic pricing strategies and competitive analysis.

## Activation
Trigger when user requests marketplace operations: listing creation, price optimization, market analysis, or trading operations.

## Input
```json
{
  "operation": "create|list|analyze|optimize|trade|status|gpu-provider-register|gpu-provider-status",
  "service_type": "ai-inference|ai-training|resource-compute|resource-storage|data-processing|gpu-provider",
  "name": "string (for create/gpu-provider-register)",
  "description": "string (for create)",
  "price": "number (for create/optimize)",
  "wallet": "string (for create/trade/gpu-provider-register)",
  "listing_id": "string (for status/trade)",
  "provider_id": "string (for gpu-provider-status)",
  "quantity": "number (for create/trade)",
  "duration": "number (for create, hours)",
  "gpu_model": "string (for gpu-provider-register)",
  "gpu_count": "number (for gpu-provider-register)",
  "models": "array (optional for gpu-provider-register, e.g., [\"llama2\", \"mistral\"])",
  "competitor_analysis": "boolean (optional for analyze)",
  "market_trends": "boolean (optional for analyze)"
}
```

## Output
```json
{
  "summary": "Marketplace operation completed successfully",
  "operation": "create|list|analyze|optimize|trade|status|gpu-provider-register|gpu-provider-status",
  "listing_id": "string (for create/status/trade)",
  "provider_id": "string (for gpu-provider-register/gpu-provider-status)",
  "service_type": "string",
  "name": "string (for create/gpu-provider-register)",
  "price": "number",
  "wallet": "string (for create/trade/gpu-provider-register)",
  "quantity": "number",
  "gpu_model": "string (for gpu-provider-register/gpu-provider-status)",
  "gpu_count": "number (for gpu-provider-register/gpu-provider-status)",
  "models": "array (for gpu-provider-register/gpu-provider-status)",
  "market_data": "object (for analyze)",
  "competitor_analysis": "array (for analyze)",
  "pricing_recommendations": "array (for optimize)",
  "trade_details": "object (for trade)",
  "provider_status": "object (for gpu-provider-status)",
  "issues": [],
  "recommendations": [],
  "confidence": 1.0,
  "execution_time": "number",
  "validation_status": "success|partial|failed"
}
```

## Process

### 1. Analyze
- Validate marketplace parameters
- Check service type compatibility
- Verify pricing strategy feasibility
- Assess market conditions

### 2. Plan
- Research competitor pricing
- Analyze market demand trends
- Calculate optimal pricing strategy
- Prepare listing parameters

### 3. Execute
- Execute AITBC CLI marketplace command
- Capture listing ID and status
- Monitor listing performance
- Analyze market response

### 4. Validate
- Verify listing creation success
- Check pricing competitiveness
- Validate market analysis accuracy
- Confirm trade execution details

## Constraints
- **MUST NOT** create listings without valid wallet
- **MUST NOT** set prices below minimum thresholds
- **MUST** validate service type compatibility
- **MUST** monitor listings for performance metrics
- **MUST** set minimum duration (1 hour)
- **MUST** validate quantity limits (1-1000 units)

## Environment Assumptions
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Marketplace service operational
- Exchange API accessible for pricing data
- GPU provider marketplace operational for resource allocation
- Ollama GPU providers can register with model specifications
- Sufficient wallet balance for listing fees
- Market data available for analysis
- GPU providers have unique p2p_node_id for P2P connectivity

## Error Handling
- Invalid service type → Return service type validation error
- Insufficient balance → Return error with required amount
- Market data unavailable → Return market status and retry recommendations
- Listing creation failure → Return detailed error and troubleshooting steps

## Example Usage Prompt

```
Create a marketplace listing for AI inference service named "Medical Diagnosis AI" with price 100 AIT per hour, duration 24 hours, quantity 10 from trading-wallet
```

## Expected Output Example

```json
{
  "summary": "Marketplace listing 'Medical Diagnosis AI' created successfully",
  "operation": "create",
  "listing_id": "listing_7f8a9b2c3d4e5f6",
  "service_type": "ai-inference",
  "name": "Medical Diagnosis AI",
  "price": 100,
  "wallet": "trading-wallet",
  "quantity": 10,
  "market_data": null,
  "competitor_analysis": null,
  "pricing_recommendations": null,
  "trade_details": null,
  "issues": [],
  "recommendations": ["Monitor listing performance", "Consider dynamic pricing based on demand", "Track competitor pricing changes"],
  "confidence": 1.0,
  "execution_time": 4.2,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Marketplace listing status checking
- Basic market listing retrieval
- Simple trade operations

**Reasoning Model** (Claude Sonnet, GPT-4)
- Marketplace listing creation with optimization
- Market analysis and competitor research
- Pricing strategy optimization
- Complex trade analysis

**Coding Model** (Claude Sonnet, GPT-4)
- Pricing algorithm optimization
- Market data analysis and modeling
- Trading strategy development

## Performance Notes
- **Execution Time**: 2-5 seconds for status/list, 5-15 seconds for create/trade, 10-30 seconds for analysis
- **Memory Usage**: <150MB for marketplace operations
- **Network Requirements**: Exchange API connectivity, marketplace service access
- **Concurrency**: Safe for multiple simultaneous listings from different wallets
- **Market Monitoring**: Real-time price tracking and competitor analysis
