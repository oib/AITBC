# Hermes AI Agent Skill

## Overview

Hermes is an AI assistant with tool-calling capabilities that can interact with the AITBC system. It supports chat, session management, skills, plugins, and various integrations.

Hermes is installed on both aitbc and aitbc1 nodes in the multi-node AITBC deployment.

## Installation & Setup

```bash
# Run interactive setup wizard
hermes setup

# Check system status and dependencies
hermes doctor

# View configuration
hermes config
hermes config edit

# Select default model and provider
hermes model
```

## Basic Usage

### Interactive Chat

```bash
# Start interactive chat
hermes

# Single query mode
hermes chat -q "What is the blockchain height?"

# Resume most recent session
hermes -c

# Resume session by name
hermes -c "my project"

# Resume session by ID
hermes --resume <session_id>
```

### Model Selection

```bash
# Select default model
hermes model

# Override model for this invocation
hermes -m tencent/hy3-preview:free

# Override provider for this invocation
hermes --provider openrouter

# Current AITBC configuration: tencent/hy3-preview:free via OpenRouter
```

## Session Management

```bash
# List past sessions
hermes sessions list

# Interactive session picker
hermes sessions browse

# Rename session
hermes sessions rename <ID> <TITLE>

# Export session
hermes sessions export <ID>

# Delete session
hermes sessions delete <ID>

# Prune old sessions
hermes sessions prune
```

## Skills & Plugins

### Skills

```bash
# Search for skills
hermes skills search <query>

# Install a skill
hermes skills install <skill-name>

# List installed skills
hermes skills list

# Configure skill
hermes skills configure <skill-name>

# Remove skill
hermes skills remove <skill-name>
```

### Preload Skills for Session

```bash
# Preload specific skills
hermes -s skill1,skill2

# Repeat flag for multiple skills
hermes -s skill1 -s skill2
```

### Plugins

```bash
# List plugins
hermes plugins list

# Install plugin
hermes plugins install <plugin-name>

# Update plugin
hermes plugins update <plugin-name>

# Remove plugin
hermes plugins remove <plugin-name>
```

### Skill Curator

```bash
# Check curator status
hermes curator status

# Run curator (background skill maintenance)
hermes curator run

# Pause curator
hermes curator pause

# Pin a skill (prevent curator updates)
hermes curator pin <skill-name>
```

## Authentication

```bash
# Login to inference provider
hermes login

# Logout from provider
hermes logout

# Add pooled credential
hermes auth add <provider>

# List pooled credentials
hermes auth list

# Remove pooled credential
hermes auth remove <provider> <token>

# Clear exhaustion status for provider
hermes auth reset <provider>
```

## Fallback Providers

```bash
# Show fallback provider chain
hermes fallback list

# Add fallback provider
hermes fallback add

# Remove fallback provider
hermes fallback remove
```

## Configuration

```bash
# View configuration
hermes config

# Edit configuration in editor
hermes config edit

# Set configuration value
hermes config set model gpt-4

# Set configuration value with path
hermes config set inference.model anthropic/claude-sonnet-4.6
```

## Logs & Debugging

```bash
# View last 50 lines of agent.log
hermes logs

# Follow agent.log in real-time
hermes logs -f

# View errors only
hermes logs errors

# View logs from last hour
hermes logs --since 1h

# View logs from last day
hermes logs --since 1d

# Upload debug report for support
hermes debug share

# Dump setup summary
hermes dump
```

## Advanced Usage

### One-Shot Mode

```bash
# Send single prompt, print only response (no banner/spinner)
hermes -z "What is the blockchain height?"

# With model override
hermes -m anthropic/claude-sonnet-4.6 -z "Check blockchain status"

# With toolsets
hermes -t blockchain,wallet -z "Send 10 tokens"
```

### Git Worktree Mode

```bash
# Run in isolated git worktree (for parallel agents)
hermes -w
```

### Toolsets

```bash
# Enable specific toolsets for this invocation
hermes -t blockchain,wallet,marketplace

# With oneshot mode
hermes -t blockchain -z "Get block height"
```

### TUI Mode

```bash
# Launch modern TUI instead of classic REPL
hermes --tui

# Run TypeScript sources via tsx (dev mode)
hermes --tui --dev
```

## Special Flags

```bash
# Auto-approve shell hooks (for CI/headless)
hermes --accept-hooks

# Bypass all dangerous command approvals (use at your own risk)
hermes --yolo

# Include session ID in system prompt
hermes --pass-session-id

# Ignore user config (~/.hermes/config.yaml)
hermes --ignore-user-config

# Skip auto-injection of AGENTS.md, SOUL.md, .cursorrules, memory
hermes --ignore-rules
```

## Integrations

### Webhook Management

```bash
# Manage dynamic webhook subscriptions
hermes webhook

# View webhook help
hermes webhook --help
```

## MCP (Model Context Protocol)

```bash
# Manage MCP servers
hermes mcp

# Run Hermes as MCP server
hermes mcp serve

# List MCP servers
hermes mcp list

# Add MCP server
hermes mcp add <server-config>
```

## Profiles

```bash
# Manage profiles (multiple isolated Hermes instances)
hermes profile

# Create new profile
hermes profile create <name>

# Switch profile
hermes profile switch <name>

# List profiles
hermes profile list

# Delete profile
hermes profile delete <name>
```

## Backup & Restore

```bash
# Backup Hermes home directory to zip
hermes backup

# Restore Hermes backup from zip
hermes import <backup-file.zip>
```

## Gateway

```bash
# Run messaging gateway
hermes gateway

# Install gateway background service
hermes gateway install

# Gateway management
hermes gateway --help
```

## System Commands

```bash
# Show version
hermes version

# Update to latest version
hermes update

# Uninstall Hermes
hermes uninstall

# Print shell completion script
hermes completion bash
hermes completion zsh
hermes completion fish
```

## Environment Variables

```bash
# Set default model (AITBC uses tencent/hy3-preview:free)
export HERMES_INFERENCE_MODEL=tencent/hy3-preview:free

# Set default provider (AITBC uses OpenRouter)
export HERMES_INFERENCE_PROVIDER=openrouter

# Auto-accept hooks
export HERMES_ACCEPT_HOOKS=1
```

Note: Zsh completion is already installed on the AITBC nodes.

## AITBC-Specific Workflows

### Multi-Node Operations

Hermes runs on both aitbc and aitbc1 nodes in the multi-node AITBC deployment.

```bash
# On aitbc node
ssh aitbc
hermes -s blockchain -z "Check aitbc blockchain status"

# On aitbc1 node
ssh aitbc1
hermes -s blockchain -z "Check aitbc1 blockchain status"

# Cross-node sync verification
hermes -t blockchain -z "Verify sync between aitbc and aitbc1"
```

### Blockchain Operations with Hermes

```bash
# Preload blockchain-specific skills
hermes -s blockchain,wallet -z "Check blockchain status"

# Query blockchain state
hermes -t blockchain -z "What is the current block height?"

# Send transaction
hermes -t wallet -z "Send 10 tokens to recipient-address"

# List wallets
hermes -t wallet -z "List all wallets"
```

### AI Training with Hermes

```bash
# Preload AI skills
hermes -s ai-training,coordinator -z "Submit AI training job"

# Check job status
hermes -t ai -z "Check status of job job_123"

# List AI jobs
hermes -t ai -z "List all AI jobs"
```

### Marketplace Operations

```bash
# List GPU resources
hermes -t marketplace -z "List available GPUs"

# Place bid
hermes -t marketplace -z "Place bid on listing listing_123"

# Check orders
hermes -t marketplace -z "Check my orders"
```

## Troubleshooting

### Common Issues

**Hermes not responding:**
```bash
# Check system status
hermes doctor

# View logs
hermes logs -f
```

**Authentication issues:**
```bash
# Clear credentials and re-login
hermes logout
hermes login

# Check auth status
hermes auth list
```

**Skill not loading:**
```bash
# Check curator status
hermes curator status

# Reinstall skill
hermes skills remove <skill-name>
hermes skills install <skill-name>
```

## Best Practices

1. **Session Management**: Use descriptive session names for easy resumption
2. **Skill Selection**: Only preload relevant skills to reduce overhead
3. **One-Shot Mode**: Use `-z` for scripts and automation
4. **Logging**: Use `hermes logs -f` for real-time debugging
5. **Configuration**: Store sensitive credentials via `hermes auth` not in config files
6. **Fallbacks**: Configure fallback providers for reliability
7. **Profiles**: Use separate profiles for different projects

## Resources

- Hermes documentation: Check `hermes --help` for any command
- Configuration: `~/.hermes/config.yaml`
- Logs: `~/.hermes/logs/`
- Skills directory: `~/.hermes/skills/`
