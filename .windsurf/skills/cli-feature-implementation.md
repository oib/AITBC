---
description: Autonomous AI skill for implementing new CLI commands and features using AITBC parser/handler infrastructure
title: CLI Feature Implementation
version: 1.0
---

# CLI Feature Implementation Skill

## Purpose
Autonomous AI skill for implementing new CLI commands and features for the AITBC CLI tool using the parser/handler infrastructure or Click-based commands.

## Activation
Activate this skill when:
- Adding new CLI commands (e.g., `aitbc oracle store`, `aitbc ipfs upload`)
- Adding subcommands to existing command groups
- Implementing new CLI features for scenarios
- Adding CLI wrappers for existing API functionality
- Extending parser/handler architecture
- Using Click-based commands for agent operations

## Input Schema
```json
{
  "command_group": {
    "type": "string",
    "description": "Command group name (e.g., oracle, ipfs, marketplace)"
  },
  "subcommands": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "name": {"type": "string", "description": "Subcommand name (e.g., store, retrieve)"},
        "description": {"type": "string", "description": "Subcommand description"},
        "arguments": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "type": {"type": "string", "enum": ["option", "argument"]},
              "required": {"type": "boolean"},
              "help": {"type": "string"}
            }
          }
        }
      }
    },
    "description": "List of subcommands to implement"
  },
  "backend_integration": {
    "type": "object",
    "properties": {
      "service_url": {"type": "string"},
      "endpoint": {"type": "string"},
      "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]}
    },
    "description": "Backend service integration details (if applicable)"
  },
  "scenario_update": {
    "type": "boolean",
    "default": true,
    "description": "Update scenario documentation after implementation"
  },
  "scenario_file": {
    "type": "string",
    "description": "Path to scenario file to update"
  }
}
```

## Output Schema
```json
{
  "implementation_status": {
    "type": "string",
    "enum": ["successful", "partial", "failed"]
  },
  "parser_file": {
    "type": "string",
    "description": "Path to created/updated parser file"
  },
  "handler_file": {
    "type": "string",
    "description": "Path to created/updated handler file"
  },
  "commands_implemented": {
    "type": "array",
    "items": {"type": "string"},
    "description": "List of implemented command names"
  },
  "registration_status": {
    "type": "object",
    "properties": {
      "parser_registered": {"type": "boolean"},
      "handler_registered": {"type": "boolean"}
    }
  },
  "test_results": {
    "type": "object",
    "properties": {
      "help_test": {"type": "boolean"},
      "execution_test": {"type": "boolean"}
    }
  },
  "scenario_updated": {
    "type": "boolean"
  },
  "errors": {
    "type": "array",
    "items": {"type": "string"}
  },
  "warnings": {
    "type": "array",
    "items": {"type": "string"}
  }
}
```

## Process

### 1. Analyze Requirements
```bash
# Check if command group exists
python3 /opt/aitbc/cli/unified_cli.py <command_group> --help

# Check parser file existence
ls -la /opt/aitbc/cli/parsers/<command_group>.py

# Check handler file existence
ls -la /opt/aitbc/cli/handlers/<command_group>.py

# Review existing patterns
ls -la /opt/aitbc/cli/parsers/
ls -la /opt/aitbc/cli/handlers/
```

### 2. Create Parser
```bash
# Copy parser template
cp /opt/aitbc/cli/templates/parser_template.py /opt/aitbc/cli/parsers/<command_group>.py

# Edit parser to add subcommands
# Use argparse pattern with subparsers
# Set handler for each subcommand using set_defaults(handler=ctx.handle_<command>_<subcommand>)
```

Parser template pattern:
```python
def register(subparsers, ctx):
    parser = subparsers.add_parser("<command_group>", help="Command group description")
    sub = parser.add_subparsers(dest="action", help="Subcommand")
    
    # Add subcommands
    sub_<subcommand> = sub.add_parser("<subcommand>", help="Subcommand description")
    sub_<subcommand>.add_argument("--option", required=True, help="Option description")
    sub_<subcommand>.set_defaults(handler=ctx.handle_<command_group>_<subcommand>)
```

### 3. Create Handler
```bash
# Copy handler template
cp /opt/aitbc/cli/templates/handler_template.py /opt/aitbc/cli/handlers/<command_group>.py

# Edit handler to implement logic
# Follow signature: handle_<command>(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping)
```

Handler template pattern:
```python
def handle_<command_group>_<subcommand>(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping):
    """Handle <command_group> <subcommand> command"""
    try:
        # Implementation logic
        result = {
            "status": "success",
            "data": {...}
        }
        render_mapping("Result:", result)
    except Exception as e:
        print(f"Error: {e}")
        return
```

### 4. Register Parser
```bash
# Edit /opt/aitbc/cli/parsers/__init__.py
# Add import: from . import <command_group>
# Add to register_all(): <command_group>.register(subparsers, ctx)
```

### 5. Register Handler
```bash
# Edit /opt/aitbc/cli/unified_cli.py
# Add import: from handlers import <command_group> as <command_group>_handlers
# Add handler wrapper function for each subcommand
# Add to handlers dict
```

Handler wrapper pattern:
```python
from handlers import <command_group> as <command_group>_handlers

def handle_<command_group>_<subcommand>(args):
    <command_group>_handlers.handle_<command_group>_<subcommand>(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping)

handlers = {
    "handle_<command_group>_<subcommand>": handle_<command_group>_<subcommand>,
    # ... existing handlers
}
```

### 6. Implement Handler Logic
Use provided context parameters:
- `default_rpc_url`: Default blockchain RPC URL (port 8006)
- `default_coordinator_url`: Default coordinator URL (port 9001)
- `first`: First execution flag
- `read_password`: Password reading function
- `render_mapping`: Output rendering function

Common patterns:
- File storage: Use `Path.home() / ".aitbc" / "<filename>.json"`
- API calls: Use `requests` for HTTP calls
- Messaging: Note to use `aitbc messaging post --topic X --message Y`
- IPFS: Note IPFS service location and dependencies
- Click commands: Can import from commands/ as utility modules

### 7. Test Commands
```bash
# Test help
python3 /opt/aitbc/cli/unified_cli.py <command_group> --help
python3 /opt/aitbc/cli/unified_cli.py <command_group> <subcommand> --help

# Test execution
python3 /opt/aitbc/cli/unified_cli.py <command_group> <subcommand> --option value

# Verify data storage
ls -la ~/.aitbc/
cat ~/.aitbc/<data_file>.json
```

### 8. Update Documentation (if scenario_update=true)
```bash
# Find scenarios using the command
grep -r "aitbc <command_group>" /opt/aitbc/docs/scenarios/

# Update scenario version
# Add CLI Command Notice if needed
# Verify all commands in scenario exist
```

## Constraints
- Must follow AITBC CLI parser/handler architecture (production standard)
- Handler signature must include all context parameters
- Must use `render_mapping()` for output (not print directly)
- Error handling must return instead of sys.exit()
- Data storage must use `~/.aitbc/` directory
- Cannot modify existing CLI commands without confirmation
- Must test all commands before marking complete
- Must update scenario documentation if scenario_update=true

## Environment Assumptions
- CLI templates exist at `/opt/aitbc/cli/templates/`
- Parser directory: `/opt/aitbc/cli/parsers/`
- Handler directory: `/opt/aitbc/cli/handlers/`
- Unified CLI: `/opt/aitbc/cli/unified_cli.py`
- Data storage: `~/.aitbc/`
- Scenario directory: `/opt/aitbc/docs/scenarios/`
- Python 3.13+ available
- argparse library available (standard library)

## Error Handling

### Parser Registration Failure
- Check if parser file exists
- Verify import in `parsers/__init__.py`
- Check syntax errors in parser file
- Verify argparse syntax is correct

### Handler Registration Failure
- Check if handler file exists
- Verify import in `unified_cli.py`
- Check function signatures match expected pattern
- Verify handler is added to handlers dict

### Command Not Found
- Verify parser is registered
- Check handler wrapper is added
- Verify handler is in handlers dict
- Check for typos in command name

### Import Errors
- Verify module paths are correct
- Check for circular dependencies
- Verify all required imports exist
- Check Python path configuration

### Test Failures
- Check command syntax
- Verify argument parsing
- Check handler logic
- Verify backend service availability (if applicable)

## Example Usage Prompts

### Basic Command Implementation
"Implement a new CLI command group 'oracle' with subcommands: store, announce, retrieve, listings."

### Single Subcommand
"Add a 'store' subcommand to the existing 'oracle' command group with --wallet and --file options."

### Backend Integration
"Implement a 'marketplace' command group that integrates with the marketplace API on port 8001."

### Scenario Update
"Implement CLI commands for Scenario 23 data oracle and update the scenario documentation."

### Fix Non-Compliant Implementation
"The oracle commands in /opt/aitbc/cli/commands/oracle.py use Click instead of parser/handler pattern. Fix this to follow AITBC CLI architecture."

## Expected Output Example
```json
{
  "implementation_status": "successful",
  "parser_file": "/opt/aitbc/cli/parsers/oracle.py",
  "handler_file": "/opt/aitbc/cli/handlers/oracle.py",
  "commands_implemented": [
    "handle_oracle_store",
    "handle_oracle_announce",
    "handle_oracle_retrieve",
    "handle_oracle_listings"
  ],
  "registration_status": {
    "parser_registered": true,
    "handler_registered": true
  },
  "test_results": {
    "help_test": true,
    "execution_test": true
  },
  "scenario_updated": true,
  "errors": [],
  "warnings": [
    "Note: In production, use 'aitbc messaging post --topic data-availability' to broadcast"
  ]
}
```

## Model Routing
- **Fast Model**: Use for simple command additions with clear requirements
- **Reasoning Model**: Use for complex command groups with backend integration
- **Reasoning Model**: Use when fixing non-compliant implementations
- **Reasoning Model**: Use when scenario documentation updates are needed

## Performance Notes
- **Implementation Time**: 5-15 minutes per command group
- **Test Time**: 1-3 minutes per command
- **File Operations**: Minimal I/O (creating/editing small files)
- **Memory Usage**: <100MB during implementation
- **Network Impact**: None (unless testing backend integration)
- **Concurrency**: Can implement multiple command groups sequentially
- **Optimization**: Use templates to speed up implementation
- **Validation**: Always test commands before marking complete

## Related Skills
- [cli-enhancement](/cli-enhancement.md) - For general CLI enhancement tasks
- [code-quality](/code-quality.md) - For code quality checks after implementation

## Related Workflows
- [CLI Enhancement](/cli-enhancement.md) - General CLI enhancement workflow
- [Code Quality](/code-quality.md) - Code quality validation workflow

## Architecture Reference
For detailed information about the AITBC CLI architecture, see:
- `/opt/aitbc/docs/cli/CLI_ARCHITECTURE.md` - Complete architecture documentation
- `/opt/aitbc/docs/cli/CLI_DEVELOPER_GUIDE.md` - Developer guide for CLI development

## AITBC CLI Architecture

**Production CLI Flow:**
```
/opt/aitbc/aitbc-cli → cli/aitbc_cli.py (wrapper)
    ↓
unified_cli.py (parser/handler architecture)
    ↓
parsers/ + handlers/ + commands/ (as utilities)
```

**Key Components:**
- **Parsers** (`/opt/aitbc/cli/parsers/`): Argument parsing with argparse
- **Handlers** (`/opt/aitbc/cli/handlers/`): Command implementation logic
- **Unified CLI** (`/opt/aitbc/cli/unified_cli.py`): Handler registration & dispatch
- **Commands** (`/opt/aitbc/cli/commands/`): Utility modules imported by handlers
- **Templates**: `/opt/aitbc/cli/templates/parser_template.py`, `/opt/aitbc/cli/templates/handler_template.py`

**Handler Signature Pattern:**
```python
def handle_<command>(args, default_rpc_url, default_coordinator_url, first, read_password, render_mapping):
    """Handle <command> command"""
    # Extract arguments from args Namespace
    # Use context parameters (default_rpc_url, default_coordinator_url)
    # Implement logic
    # Render results with render_mapping()
```

**Always use the parser/handler pattern for AITBC CLI development.**
