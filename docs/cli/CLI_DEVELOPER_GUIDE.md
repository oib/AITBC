# AITBC CLI Developer Guide

This guide explains how to extend the AITBC CLI by adding new commands, handlers, and parsers following the established architecture patterns.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Command Registration Flow](#command-registration-flow)
3. [Handler Execution Flow](#handler-execution-flow)
4. [Creating a New Command](#creating-a-new-command)
5. [Common Patterns](#common-patterns)
6. [Best Practices](#best-practices)

## Architecture Overview

The AITBC CLI follows a modular architecture with three main components:

- **Parsers** (`/opt/aitbc/cli/parsers/`) - Define command structure and arguments using argparse
- **Handlers** (`/opt/aitbc/cli/handlers/`) - Implement command logic and backend interactions
- **Unified CLI** (`/opt/aitbc/cli/unified_cli.py`) - Entry point that coordinates parsers and handlers

```
User Input → Parser → Handler Wrapper → Handler Implementation → Backend Service
```

## Command Registration Flow

### Step 1: Create Parser Module

Create a new parser file in `/opt/aitbc/cli/parsers/`:

```python
# /opt/aitbc/cli/parsers/mycommand.py
"""My command registration for the unified CLI."""

import argparse
from parser_context import ParserContext

def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
    mycommand_parser = subparsers.add_parser("mycommand", help="My command description")
    mycommand_parser.set_defaults(handler=lambda parsed, parser=mycommand_parser: parser.print_help())
    mycommand_subparsers = mycommand_parser.add_subparsers(dest="mycommand_action")
    
    # Add subcommands
    mycommand_action_parser = mycommand_subparsers.add_parser("action", help="Action description")
    mycommand_action_parser.add_argument("--option", help="Option description")
    mycommand_action_parser.set_defaults(handler=ctx.handle_mycommand_action)
```

### Step 2: Register Parser in __init__.py

Add your parser to the import list and registration function:

```python
# /opt/aitbc/cli/parsers/__init__.py
from . import ai, agent, analytics, blockchain, mycommand  # Add import

def register_all(subparsers, ctx):
    # ... existing registrations ...
    mycommand.register(subparsers, ctx)  # Add registration
```

### Step 3: Create Handler Module

Create a handler file in `/opt/aitbc/cli/handlers/`:

```python
# /opt/aitbc/cli/handlers/mycommand.py
"""My command handlers."""

def handle_mycommand_action(args, render_mapping):
    """Handle mycommand action."""
    option_value = getattr(args, "option", "default")
    
    result = {
        "action": "mycommand",
        "option": option_value,
        "status": "success"
    }
    
    print(f"My command executed with option: {option_value}")
    render_mapping("Result:", result)
```

### Step 4: Register Handler in Unified CLI

Add handler import, wrapper function, and registration:

```python
# /opt/aitbc/cli/unified_cli.py
from handlers import mycommand as mycommand_handlers  # Add import

# In the wrapper functions section
def handle_mycommand_action(args):
    mycommand_handlers.handle_mycommand_action(args, render_mapping)

# In the handlers dictionary
handlers = {
    # ... existing handlers ...
    "handle_mycommand_action": handle_mycommand_action,
}
```

## Handler Execution Flow

When a user runs a command:

1. **Parser** (`unified_cli.py:run_cli`) - argparse processes command line arguments
2. **Handler Lookup** - Get handler from parsed arguments
3. **Wrapper Execution** - Call wrapper function with context
4. **Handler Implementation** - Execute actual command logic
5. **Backend Call** - Make HTTP request to service if needed
6. **Output** - Render structured result to user

### Example: AI Job Submission

```python
# Parser defines arguments
ai_submit_parser.add_argument("wallet_name")
ai_submit_parser.add_argument("job_type_arg")
ai_submit_parser.add_argument("prompt_arg")
ai_submit_parser.add_argument("payment_arg")
ai_submit_parser.add_argument("--coordinator-url", default=ctx.default_coordinator_url)

# Wrapper passes context
def handle_ai_submit(args):
    ai_handlers.handle_ai_submit(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping)

# Handler makes backend call
def handle_ai_submit(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping):
    coordinator_url = getattr(args, 'coordinator_url', default_coordinator_url) or default_coordinator_url
    
    job_data = {
        "task_data": {
            "model": model,
            "prompt": prompt,
            "parameters": {}
        }
    }
    
    response = requests.post(f"{coordinator_url}/tasks/submit", json=job_data, timeout=30)
```

## Creating a New Command

### Complete Example: Adding a "status" Command

**1. Create Parser** (`/opt/aitbc/cli/parsers/status.py`):

```python
"""Status command registration for the unified CLI."""

import argparse
from parser_context import ParserContext

def register(subparsers: argparse._SubParsersAction, ctx: ParserContext) -> None:
    status_parser = subparsers.add_parser("status", help="System status information")
    status_parser.set_defaults(handler=ctx.handle_status)
```

**2. Register Parser** (`/opt/aitbc/cli/parsers/__init__.py`):

```python
from . import status

def register_all(subparsers, ctx):
    # ...
    status.register(subparsers, ctx)
```

**3. Create Handler** (`/opt/aitbc/cli/handlers/status.py`):

```python
"""Status command handlers."""

def handle_status(args, render_mapping):
    """Handle status command."""
    status_data = {
        "system": "healthy",
        "version": "1.0.0",
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    
    render_mapping("System Status:", status_data)
```

**4. Register Handler** (`/opt/aitbc/cli/unified_cli.py`):

```python
from handlers import status as status_handlers

def handle_status(args):
    status_handlers.handle_status(args, render_mapping)

handlers = {
    "handle_status": handle_status,
}
```

## Common Patterns

### Pattern 1: Real Backend Integration

Make HTTP calls to backend services:

```python
import requests

def handle_command_with_backend(args, service_url, render_mapping):
    response = requests.get(f"{service_url}/endpoint", timeout=30)
    if response.status_code == 200:
        result = response.json()
        render_mapping("Result:", result)
    else:
        print(f"Error: {response.status_code}")
        return  # Graceful degradation
```

### Pattern 2: Stub Handler for Unavailable Services

Return structured data when service is unavailable:

```python
def handle_command_stub(args, render_mapping):
    stub_data = {
        "status": "simulated",
        "data": "stub response",
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    
    render_mapping("Result:", stub_data)
```

### Pattern 3: Agent Coordinator Integration

Use coordinator URL and task_data format:

```python
def handle_ai_task(args, default_coordinator_url, render_mapping):
    coordinator_url = getattr(args, 'coordinator_url', default_coordinator_url)
    
    task_data = {
        "task_data": {
            "model": model,
            "prompt": prompt,
            "parameters": {}
        }
    }
    
    response = requests.post(f"{coordinator_url}/tasks/submit", json=task_data)
```

### Pattern 4: Blockchain RPC Integration

Use blockchain RPC endpoint:

```python
def handle_blockchain_command(args, default_rpc_url, render_mapping):
    rpc_url = args.rpc_url or default_rpc_url
    
    response = requests.get(f"{rpc_url}/rpc/blocks/latest", timeout=30)
    if response.status_code == 200:
        block_data = response.json()
        render_mapping("Block:", block_data)
```

### Pattern 5: Marketplace API Integration

Use marketplace exchange API:

```python
def handle_marketplace_command(args, marketplace_url, render_mapping):
    marketplace_url = args.marketplace_url or "http://localhost:8001"
    
    response = requests.get(f"{marketplace_url}/listings", timeout=30)
    if response.status_code == 200:
        listings = response.json()
        render_mapping("Listings:", listings)
```

## Best Practices

### Command Naming

- Use lowercase, hyphenated names: `my-command`
- Use descriptive names: `gpu-status` not `stat`
- Group related commands under category: `cluster status`, `cluster sync`

### Argument Design

- Use `--long-name` for options
- Use positional arguments for required values
- Provide sensible defaults
- Use `choices` for enum-like values

```python
parser.add_argument("--format", choices=["json", "csv"], default="json")
parser.add_argument("--verbose", action="store_true")
parser.add_argument("required_arg")
```

### Handler Signatures

Pass context parameters needed for backend calls:

```python
def handle_command(args, default_rpc_url, default_coordinator_url, render_mapping):
    # Use provided context
    rpc_url = args.rpc_url or default_rpc_url
    coordinator_url = args.coordinator_url or default_coordinator_url
```

### Error Handling

Use graceful degradation instead of sys.exit():

```python
def handle_command(args, render_mapping):
    try:
        # Try real backend call
        result = backend_call()
        render_mapping("Result:", result)
    except Exception as e:
        # Fall back to stub
        print(f"Backend unavailable, using stub: {e}")
        stub_result = {"status": "simulated"}
        render_mapping("Result:", stub_result)
```

### Structured Output

Use render_mapping for consistent output:

```python
def handle_command(args, render_mapping):
    result = {
        "key1": "value1",
        "key2": "value2"
    }
    
    render_mapping("Command Result:", result)
```

### Documentation

Add help text for commands and arguments:

```python
parser = subparsers.add_parser("mycommand", help="Description of what this command does")
parser.add_argument("--option", help="Description of this option")
```

## Testing Commands

Test your command implementation:

```bash
# Test help
/opt/aitbc/venv/bin/python /opt/aitbc/cli/unified_cli.py mycommand --help

# Test execution
/opt/aitbc/venv/bin/python /opt/aitbc/cli/unified_cli.py mycommand action --option value

# Verify exit code
echo $?
```

## Troubleshooting

### Command Not Found

- Check parser is imported in `parsers/__init__.py`
- Check parser is registered in `register_all()`
- Check handler is registered in `unified_cli.py` handlers dictionary

### Handler Not Called

- Check parser `set_defaults(handler=ctx.handle_xxx)` matches handler name
- Check handler wrapper function exists in `unified_cli.py`
- Check handler is in handlers dictionary

### Backend Call Failing

- Check service URL is correct
- Check service is running
- Check request format matches API expectations
- Add error logging to debug

## Resources

- Parser templates: `/opt/aitbc/cli/templates/`
- Handler templates: `/opt/aitbc/cli/templates/`
- Command generator: `/opt/aitbc/cli/tools/generate_command.py`
- Command validator: `/opt/aitbc/cli/tools/validate_command.py`
