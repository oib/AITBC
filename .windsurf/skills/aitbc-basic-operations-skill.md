---
description: Atomic AITBC basic operations testing with deterministic validation and health checks
title: aitbc-basic-operations-skill
version: 1.0
---

# AITBC Basic Operations Skill

## Purpose
Test and validate AITBC basic CLI functionality, core blockchain operations, wallet operations, and service connectivity with deterministic health checks.

## Activation
Trigger when user requests basic AITBC operations testing: CLI validation, wallet operations, blockchain status, or service health checks.

## Input
```json
{
  "operation": "test-cli|test-wallet|test-blockchain|test-services|comprehensive",
  "test_wallet": "string (optional for wallet testing)",
  "test_password": "string (optional for wallet testing)",
  "service_ports": "array (optional for service testing, default: [8000, 8001, 8006])",
  "timeout": "number (optional, default: 30 seconds)",
  "verbose": "boolean (optional, default: false)"
}
```

## Output
```json
{
  "summary": "Basic operations testing completed successfully",
  "operation": "test-cli|test-wallet|test-blockchain|test-services|comprehensive",
  "test_results": {
    "cli_version": "string",
    "cli_help": "boolean",
    "wallet_operations": "boolean",
    "blockchain_status": "boolean",
    "service_connectivity": "boolean"
  },
  "service_health": {
    "coordinator_api": "boolean",
    "exchange_api": "boolean",
    "blockchain_rpc": "boolean"
  },
  "wallet_info": {
    "wallet_created": "boolean",
    "wallet_listed": "boolean",
    "balance_retrieved": "boolean"
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
- Validate test parameters and operation type
- Check environment prerequisites
- Verify service availability
- Assess testing scope requirements

### 2. Plan
- Prepare test execution sequence
- Define success criteria for each test
- Set timeout and error handling strategy
- Configure validation checkpoints

### 3. Execute
- Execute CLI version and help tests
- Perform wallet creation and operations testing
- Test blockchain status and network operations
- Validate service connectivity and health

### 4. Validate
- Verify test completion and results
- Check service health and connectivity
- Validate wallet operations success
- Confirm overall system health

## Constraints
- **MUST NOT** perform destructive operations without explicit request
- **MUST NOT** exceed timeout limits for service checks
- **MUST** validate all service ports before connectivity tests
- **MUST** handle test failures gracefully with detailed diagnostics
- **MUST** preserve existing wallet data during testing
- **MUST** provide deterministic test results with clear pass/fail criteria

## Environment Assumptions
- AITBC CLI accessible at `/opt/aitbc/aitbc-cli`
- Python venv activated for CLI operations
- Services running on ports 8000, 8001, 8006
- Working directory: `/opt/aitbc`
- Default test wallet: "test-wallet" with password "test123"

## Error Handling
- CLI command failures → Return command error details and troubleshooting
- Service connectivity issues → Return service status and restart recommendations
- Wallet operation failures → Return wallet diagnostics and recovery steps
- Timeout errors → Return timeout details and retry suggestions

## Example Usage Prompt

```
Run comprehensive basic operations testing for AITBC system including CLI, wallet, blockchain, and service health checks
```

## Expected Output Example

```json
{
  "summary": "Comprehensive basic operations testing completed with all systems healthy",
  "operation": "comprehensive",
  "test_results": {
    "cli_version": "aitbc-cli v1.0.0",
    "cli_help": true,
    "wallet_operations": true,
    "blockchain_status": true,
    "service_connectivity": true
  },
  "service_health": {
    "coordinator_api": true,
    "exchange_api": true,
    "blockchain_rpc": true
  },
  "wallet_info": {
    "wallet_created": true,
    "wallet_listed": true,
    "balance_retrieved": true
  },
  "issues": [],
  "recommendations": ["All systems operational", "Regular health checks recommended", "Monitor service performance"],
  "confidence": 1.0,
  "execution_time": 12.4,
  "validation_status": "success"
}
```

## Model Routing Suggestion

**Fast Model** (Claude Haiku, GPT-3.5-turbo)
- Simple CLI version checking
- Basic service health checks
- Quick wallet operations testing

**Reasoning Model** (Claude Sonnet, GPT-4)
- Comprehensive testing with detailed validation
- Service connectivity troubleshooting
- Complex test result analysis and recommendations

## Performance Notes
- **Execution Time**: 5-15 seconds for basic tests, 15-30 seconds for comprehensive testing
- **Memory Usage**: <100MB for basic operations testing
- **Network Requirements**: Service connectivity for health checks
- **Concurrency**: Safe for multiple simultaneous basic operations tests
- **Test Coverage**: CLI functionality, wallet operations, blockchain status, service health
