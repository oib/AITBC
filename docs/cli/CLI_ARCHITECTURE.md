# AITBC CLI Architecture

This document describes the architecture of the AITBC CLI system, including component interactions, data flows, and extension points.

## System Overview

The AITBC CLI follows a modular, layered architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface Layer                  │
│                  (Command Line Interface)                │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   Parser Layer                           │
│           (Argument Parsing & Validation)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ wallet.py    │  │ blockchain.py │  │ ai.py        │ │
│  │ market.py    │  │ network.py    │  │ workflow.py  │ │
│  │ ...          │  │ ...          │  │ ...          │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                 Unified CLI Layer                       │
│           (Handler Registration & Dispatch)                │
│  ┌────────────────────────────────────────────────────┐ │
│  │ unified_cli.py                                     │ │
│  │ - Parser registration                              │ │
│  │ - Handler wrappers                                 │ │
│  │ - Handler dispatch table                           │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Handler Layer                          │
│              (Command Implementation)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ wallet.py    │  │ ai.py        │  │ system.py    │ │
│  │ market.py    │  │ blockchain.py │  │ ...          │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                Backend Services Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Blockchain   │  │ Agent        │  │ Marketplace  │ │
│  │ RPC (8006)   │  │ Coordinator  │  │ Exchange     │ │
│  │              │  │ (9001)       │  │ (8001)       │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Component Interactions

### 1. Parser Registration Flow

```
parsers/__init__.py
    │
    ├── import all parser modules
    │   ├── from . import wallet
    │   ├── from . import blockchain
    │   ├── from . import ai
    │   └── ...
    │
    └── register_all(subparsers, ctx)
        │
        ├── wallet.register(subparsers, ctx)
        │   └── add_parser("wallet")
        │       └── add_subparser("create", "list", ...)
        │
        ├── blockchain.register(subparsers, ctx)
        │   └── add_parser("blockchain")
        │       └── add_subparser("info", "block", ...)
        │
        └── ai.register(subparsers, ctx)
            └── add_parser("ai")
                └── add_subparser("submit", "jobs", ...)
```

### 2. Command Execution Flow

```
User Input: "aitbc-cli ai submit openclaw-trainee inference test 10"
    │
    ▼
unified_cli.py:run_cli()
    │
    ├── Parse arguments with argparse
    │   └── parser.parse_args()
    │       └── parsed_args = Namespace(...)
    │
    ├── Get handler from parsed_args
    │   └── handler = parsed_args.handler
    │       └── handle_ai_submit
    │
    └── Execute handler
        └── handler(parsed_args)
            │
            └── unified_cli.py:handle_ai_submit()
                │
                └── ai_handlers.handle_ai_submit()
                    │
                    ├── Get coordinator URL
                    ├── Build job request
                    ├── HTTP POST to Agent Coordinator
                    └── Render result
```

### 3. Handler Pattern

```
Handler Wrapper (unified_cli.py)
    │
    ├── def handle_ai_submit(args):
    │   └── ai_handlers.handle_ai_submit(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping)
    │       └── Passes context parameters
    │
    └── Handler Implementation (handlers/ai.py)
        │
        ├── def handle_ai_submit(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping):
        │   ├── Extract arguments
        │   ├── Use context (RPC URL, coordinator URL)
        │   ├── Make backend call
        │   └── Render result
        │
        └── Return success/failure
```

## Data Flow Diagrams

### AI Job Submission Flow

```
User Command
    │
    ▼
Parser (ai.py)
    │
    ├── Parse: wallet, job_type, prompt, payment
    ├── Set default coordinator URL (9001)
    └── Map to handler: handle_ai_submit
    │
    ▼
Handler Wrapper (unified_cli.py)
    │
    ├── Get context: default_rpc_url, default_coordinator_url
    └── Call: ai_handlers.handle_ai_submit()
    │
    ▼
Handler Implementation (handlers/ai.py)
    │
    ├── Extract parameters from args
    ├── Build request:
    │   {
    │     "task_data": {
    │       "model": model,
    │       "prompt": prompt,
    │       "parameters": {}
    │     }
    │   }
    │
    ├── HTTP POST to http://localhost:9001/tasks/submit
    ├── Parse response
    └── Render result to user
    │
    ▼
Agent Coordinator Service (9001)
    │
    ├── Receive job request
    ├── Queue job for processing
    └── Return job ID to CLI
```

### Blockchain Query Flow

```
User Command
    │
    ▼
Parser (blockchain.py)
    │
    ├── Parse: block height, RPC URL
    ├── Set default RPC URL (8006)
    └── Map to handler: handle_blockchain_block
    │
    ▼
Handler Wrapper (unified_cli.py)
    │
    ├── Get context: default_rpc_url
    └── Call: blockchain_handlers.handle_blockchain_block()
    │
    ▼
Handler Implementation (handlers/blockchain.py)
    │
    ├── Extract block height
    ├── Build request URL: http://localhost:8006/rpc/blocks/{height}
    ├── HTTP GET
    ├── Parse response
    └── Render block data to user
    │
    ▼
Blockchain RPC Service (8006)
    │
    ├── Receive block request
    ├── Query blockchain state
    └── Return block data
```

### Marketplace Operation Flow

```
User Command
    │
    ▼
Parser (market.py)
    │
    ├── Parse: action (list, buy, sell), parameters
    ├── Set default marketplace URL (8001)
    └── Map to handler: handle_market_listings
    │
    ▼
Handler Wrapper (unified_cli.py)
    │
    ├── Get context: default_marketplace_url
    └── Call: market_handlers.handle_market_listings()
    │
    ▼
Handler Implementation (handlers/market.py)
    │
    ├── Build request URL: http://localhost:8001/listings
    ├── HTTP GET
    ├── Parse response
    └── Render listings to user
    │
    ▼
Marketplace Exchange API (8001)
    │
    ├── Receive listings request
    ├── Query marketplace database
    └── Return listings
```

## Extension Points

### 1. Adding New Commands

**Location:** `/opt/aitbc/cli/parsers/`

Create new parser module following the pattern:
```python
def register(subparsers, ctx):
    parser = subparsers.add_parser("command", help="description")
    parser.set_defaults(handler=ctx.handle_command)
```

**Registration:** Add to `/opt/aitbc/cli/parsers/__init__.py`
```python
from . import mycommand

def register_all(subparsers, ctx):
    mycommand.register(subparsers, ctx)
```

### 2. Adding New Handlers

**Location:** `/opt/aitbc/cli/handlers/`

Create handler module:
```python
def handle_command(args, render_mapping):
    # Implementation
    pass
```

**Registration:** Add to `/opt/aitbc/cli/unified_cli.py`
```python
from handlers import mycommand as mycommand_handlers

def handle_command(args):
    mycommand_handlers.handle_command(args, render_mapping)

handlers = {
    "handle_command": handle_command,
}
```

### 3. Adding Backend Service Integration

**Pattern:** Use HTTP requests to backend services

```python
import requests

def handle_command(args, service_url, render_mapping):
    url = f"{service_url}/endpoint"
    response = requests.get(url, timeout=30)
    if response.status_code == 200:
        result = response.json()
        render_mapping("Result:", result)
```

### 4. Adding Context Parameters

**Location:** `/opt/aitbc/cli/unified_cli.py`

Add context to handler wrapper:
```python
def handle_command(args):
    mycommand_handlers.handle_command(args, default_rpc_url, default_coordinator_url, render_mapping)
```

**Handler signature:**
```python
def handle_command(args, default_rpc_url, default_coordinator_url, render_mapping):
    # Use provided context
    rpc_url = args.rpc_url or default_rpc_url
    coordinator_url = args.coordinator_url or default_coordinator_url
```

## Service Endpoints

### Active Services

| Service | Port | Endpoint | Usage |
|---------|------|----------|-------|
| Blockchain RPC | 8006 | `/rpc/blocks/{height}` | Blockchain queries |
| Agent Coordinator | 9001 | `/tasks/submit` | AI job submission |
| Marketplace Exchange | 8001 | `/listings` | Marketplace operations |

### Common Patterns

**Agent Coordinator Integration:**
```python
coordinator_url = "http://localhost:9001"
job_data = {
    "task_data": {
        "model": model,
        "prompt": prompt,
        "parameters": {}
    }
}
requests.post(f"{coordinator_url}/tasks/submit", json=job_data)
```

**Blockchain RPC Integration:**
```python
rpc_url = "http://localhost:8006"
requests.get(f"{rpc_url}/rpc/blocks/latest")
```

**Marketplace API Integration:**
```python
marketplace_url = "http://localhost:8001"
requests.get(f"{marketplace_url}/listings")
```

## Error Handling Patterns

### Graceful Degradation

```python
def handle_command(args, render_mapping):
    try:
        # Try real backend call
        result = backend_call()
        render_mapping("Result:", result)
    except Exception as e:
        # Fall back to stub
        print(f"Backend unavailable: {e}")
        stub_result = {"status": "simulated"}
        render_mapping("Result:", stub_result)
```

### Non-Exiting Errors

```python
def handle_command(args, render_mapping):
    if not required_parameter:
        print("Error: Missing required parameter")
        return  # Don't sys.exit(1)
```

## Performance Considerations

### HTTP Timeouts

```python
response = requests.get(url, timeout=30)  # 30 second timeout
```

### Async Operations

For long-running operations, use stub handlers or background tasks:
```python
def handle_long_operation(args, render_mapping):
    result = {
        "status": "submitted",
        "operation_id": generate_id(),
        "estimated_time": "5 minutes"
    }
    render_mapping("Operation:", result)
```

## Security Considerations

### Password Handling

```python
def handle_command(args, read_password):
    password = read_password(args.wallet, args.password_file)
    # Use password for authentication
```

### API Keys

Store API keys in environment variables or config files, not in code.

### Input Validation

```python
if not validate_input(args.input):
    print("Error: Invalid input")
    return
```

## Testing Strategy

### Unit Testing

Test handler functions in isolation:
```python
def test_handle_command():
    args = Namespace(option="value")
    result = handle_command(args, mock_render_mapping)
    assert result["status"] == "success"
```

### Integration Testing

Test complete command flow:
```bash
/opt/aitbc/venv/bin/python /opt/aitbc/cli/unified_cli.py mycommand --option value
```

## Monitoring & Debugging

### Logging

Add logging to handlers:
```python
import logging
logger = logging.getLogger(__name__)

def handle_command(args):
    logger.info(f"Executing command with args: {args}")
```

### Error Messages

Provide clear, actionable error messages:
```python
print(f"Error: Failed to connect to service at {service_url}")
print(f"  - Check if service is running")
print(f"  - Verify URL is correct")
```
