# Pool Hub

## Purpose & Scope

Matchmaking gateway between coordinator job requests and available miners. See `docs/bootstrap/pool_hub.md` for architectural guidance.

## Development Setup

- Create a Python virtual environment under `apps/pool-hub/.venv`.
- Install FastAPI, Redis (optional), and PostgreSQL client dependencies once requirements are defined.
- Implement routers and registry as described in the bootstrap document.
