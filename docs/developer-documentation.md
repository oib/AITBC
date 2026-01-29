# Developer Documentation - AITBC

Build on the AITBC platform: SDKs, APIs, bounties, and resources for developers.

## Quick Start

### Prerequisites

- Git
- Docker and Docker Compose
- Node.js 18+ (for frontend)
- Python 3.9+ (for AI services)
- Rust 1.70+ (for blockchain)

### Setup Development Environment

```bash
# Clone the repository
git clone https://gitea.bubuit.net/oib/aitbc.git
cd aitbc

# Start all services
docker-compose up -d

# Check status
docker-compose ps
```

## Architecture Overview

The AITBC platform consists of:

- **Blockchain Node** (Rust) - PoA/PoS consensus layer
- **Coordinator API** (Python/FastAPI) - Job orchestration
- **Marketplace Web** (TypeScript/Vite) - User interface
- **Miner Daemons** (Go) - GPU compute providers
- **Wallet Daemon** (Go) - Secure wallet management

## Contributing

### How to Contribute

1. Fork the repository on Gitea
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `make test`
6. Submit a pull request

### Code Style

- **Rust**: Use `rustfmt` and `clippy`
- **Python**: Follow PEP 8, use `black` and `flake8`
- **TypeScript**: Use Prettier and ESLint
- **Go**: Use `gofmt`

### Pull Request Process

1. Update documentation for any changes
2. Add unit tests for new features
3. Ensure CI/CD pipeline passes
4. Request review from core team
5. Address feedback promptly

## Bounty Program

Get paid to contribute to AITBC! Check open bounties on Gitea.

### Current Bounties

- **$500** - Implement REST API rate limiting
- **$750** - Add Python async SDK support
- **$1000** - Optimize ZK proof generation
- **$1500** - Implement cross-chain bridge
- **$2000** - Build mobile wallet app

### Research Grants

- **$5000** - Novel consensus mechanisms
- **$7500** - Privacy-preserving ML
- **$10000** - Quantum-resistant cryptography

### How to Apply

1. Check open issues on Gitea
2. Comment on the issue you want to work on
3. Submit your solution
4. Get reviewed by core team
5. Receive payment in AITBC tokens

> **New Contributor Bonus:** First-time contributors get a 20% bonus on their first bounty!

## Join the Community

### Developer Channels

- **Discord #dev** - General development discussion
- **Discord #core-dev** - Core protocol discussions
- **Discord #bounties** - Bounty program updates
- **Discord #research** - Research discussions

### Events & Programs

- **Weekly Dev Calls** - Every Tuesday 14:00 UTC
- **Hackathons** - Quarterly with prizes
- **Office Hours** - Meet the core team
- **Mentorship Program** - Learn from experienced devs

### Recognition

- Top contributors featured on website
- Monthly contributor rewards
- Special Discord roles
- Annual developer summit invitation
- Swag and merchandise

## Developer Resources

### Documentation

- [Full API Documentation](full-documentation.md)
- [Architecture Guide](architecture.md)
- [Protocol Specification](protocol.md)
- [Security Best Practices](security.md)

### Tools & SDKs

- [Python SDK](sdks/python.md)
- [JavaScript SDK](sdks/javascript.md)
- [Go SDK](sdks/go.md)
- [Rust SDK](sdks/rust.md)
- [CLI Tools](cli-tools.md)

### Development Environment

- [Docker Compose Setup](setup/docker-compose.md)
- [Local Testnet](setup/testnet.md)
- [Faucet for Test Tokens](setup/faucet.md)
- [Block Explorer](tools/explorer.md)

### Learning Resources

- [Video Tutorials](tutorials/videos.md)
- [Workshop Materials](tutorials/workshops.md)
- [Blog Posts](blog/index.md)
- [Research Papers](research/papers.md)

## Example: Adding a New API Endpoint

The coordinator-api uses Python with FastAPI. Here's how to add a new endpoint:

### 1. Define the Schema

```python
# File: coordinator-api/src/app/schemas.py

from pydantic import BaseModel
from typing import Optional

class NewFeatureRequest(BaseModel):
    """Request model for new feature."""
    name: str
    value: int
    options: Optional[dict] = None

class NewFeatureResponse(BaseModel):
    """Response model for new feature."""
    id: str
    status: str
    result: dict
```

### 2. Create the Router

```python
# File: coordinator-api/src/app/routers/new_feature.py

from fastapi import APIRouter, Depends, HTTPException
from ..schemas import NewFeatureRequest, NewFeatureResponse
from ..services.new_feature import NewFeatureService

router = APIRouter(prefix="/v1/features", tags=["features"])

@router.post("/", response_model=NewFeatureResponse)
async def create_feature(
    request: NewFeatureRequest,
    service: NewFeatureService = Depends()
):
    """Create a new feature."""
    try:
        result = await service.process(request)
        return NewFeatureResponse(
            id=result.id,
            status="success",
            result=result.data
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 3. Write Tests

```python
# File: coordinator-api/tests/test_new_feature.py

import pytest
from fastapi.testclient import TestClient
from src.app.main import app

client = TestClient(app)

def test_create_feature_success():
    """Test successful feature creation."""
    response = client.post(
        "/v1/features/",
        json={"name": "test", "value": 123}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "id" in data

def test_create_feature_invalid():
    """Test validation error."""
    response = client.post(
        "/v1/features/",
        json={"name": ""}  # Missing required field
    )
    assert response.status_code == 422
```

> **💡 Pro Tip:** Run `make test` locally before pushing. The CI pipeline will also run all tests automatically on your PR.

## Frequently Asked Questions

### General

- **How do I start contributing?** - Check our "Getting Started" guide and pick an issue that interests you.
- **Do I need to sign anything?** - Yes, you'll need to sign our CLA (Contributor License Agreement).
- **Can I be paid for contributions?** - Yes! Check our bounty program or apply for grants.

### Technical

- **What's the tech stack?** - Rust for blockchain, Go for services, Python for AI, TypeScript for frontend.
- **How do I run tests?** - Use `make test` or check specific component documentation.
- **Where can I ask questions?** - Discord #dev channel is the best place.

### Process

- **How long does PR review take?** - Usually 1-3 business days.
- **Can I work on multiple issues?** - Yes, but submit one PR per feature.
- **What if I need help?** - Ask in Discord or create a "help wanted" issue.

## Getting Help

- **Documentation**: [https://docs.aitbc.bubuit.net](https://docs.aitbc.bubuit.net)
- **Discord**: [Join our server](https://discord.gg/aitbc)
- **Email**: [aitbc@bubuit.net](mailto:aitbc@bubuit.net)
- **Issues**: [Report on Gitea](https://gitea.bubuit.net/oib/aitbc/issues)
