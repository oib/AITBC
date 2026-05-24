# AITBC Agent Core

Shared agent service logic with protocol-based dependency injection.

## Purpose

This package provides shared business logic for agent integration and orchestration across multiple AITBC applications. It uses protocol-based dependency injection to avoid coupling to app-specific implementations, enabling code reuse while maintaining flexibility.

## Architecture

### Protocol-Based Design

The package defines abstract protocols (interfaces) for all dependencies:

- **Domain Protocols**: `IAgentExecution`, `IAgentStepExecution` - Domain model interfaces
- **Security Protocols**: `ISecurityManager`, `IAuditor` - Security and auditing interfaces
- **Orchestration Protocol**: `IAgentOrchestrator` - Workflow orchestration interface
- **ZK Proof Protocol**: `IZKProofService` - Zero-knowledge proof generation/verification
- **Database Protocol**: `ISessionProvider` - Database session management

### Core Service

`AgentIntegrationService` contains pure business logic that:
- Deploys agents with configuration
- Generates verification proofs
- Verifies execution proofs
- Queries execution status

All dependencies are injected via constructor, enabling app-specific adapters.

## Usage

### App-Specific Adapters

Each app implements protocols for its domain models and services:

```python
# Example adapter for agent-management
from aitbc_agent_core.protocols import ISecurityManager
from app.services.agent_security import AgentSecurityManager

class AgentSecurityManagerAdapter(ISecurityManager):
    def __init__(self, manager: AgentSecurityManager):
        self._manager = manager
    
    async def validate_operation(self, operation: str, context: dict) -> bool:
        return await self._manager.validate_operation(operation, context)
    
    async def audit_event(self, event_type: str, details: dict) -> None:
        await self._manager.audit_event(event_type, details)
```

### Factory Pattern

Create the shared service with app-specific adapters:

```python
from aitbc_agent_core import AgentIntegrationService
from .adapters import (
    SessionProviderAdapter,
    SecurityManagerAdapter,
    AuditorAdapter,
    OrchestratorAdapter,
)

def create_agent_integration_service():
    return AgentIntegrationService(
        session_provider=SessionProviderAdapter(get_session),
        security_manager=SecurityManagerAdapter(AgentSecurityManager()),
        auditor=AuditorAdapter(AgentAuditor()),
        orchestrator=OrchestratorAdapter(AIAgentOrchestrator()),
        zk_proof_service=ZKProofServiceAdapter(ZKProofService()),
    )
```

## Installation

```bash
poetry add aitbc-agent-core
```

## Development

### Running Tests

```bash
poetry install --with test
poetry run pytest
```

### Type Checking

```bash
poetry run mypy src
```

## License

Proprietary - AITBC Project
