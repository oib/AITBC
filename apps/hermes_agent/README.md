# hermes_agent

## Status

**active**

## Description

One-shot Hermes Agent offer for the AITBC marketplace. Buyers send a prompt; the shop runs `hermes -z` and returns the final response. Pricing is per minute of wall-clock execution time. The shop node supplies the Hermes binary, configuration, and provider API keys.

## Node Type

island / shop

## GPU Required

**No**

## Service

1 systemd service(s): aitbc-hermes-agent.service

## Core Service

no

## Source

`main.py` entry point

## Configuration

Create `/etc/aitbc/hermes.env` to set shop defaults and allowlists. Do not commit this file.

```bash
# Required provider key(s) — Hermes reads these from the process environment.
OPENROUTER_API_KEY=...
# OPENAI_API_KEY=...
# ANTHROPIC_API_KEY=...

# Optional defaults
HERMES_DEFAULT_MODEL=anthropic/claude-sonnet-4.6
HERMES_DEFAULT_PROVIDER=anthropic
HERMES_DEFAULT_REASONING=medium
HERMES_DEFAULT_TOOLSETS=core

# Optional allowlists (empty means "use default only")
HERMES_ALLOWED_MODELS=anthropic/claude-sonnet-4.6,openai/gpt-4o
HERMES_ALLOWED_PROVIDERS=anthropic,openai
HERMES_ALLOWED_TOOLSETS=core

HERMES_MAX_TIME_DEFAULT=300
HERMES_MAX_TIME_LIMIT=1800
```

## Ports

- HTTP: `8270`
- nginx path: `/hermes/`

---
*Last updated: 2026-09-02*
