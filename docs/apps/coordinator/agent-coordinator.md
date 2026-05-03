# Agent Coordinator

## Status
✅ Operational

## Overview
FastAPI-based agent coordination service that manages agent discovery, load balancing, and task distribution across the AITBC network.

## Architecture

### Core Components
- **Agent Registry**: Central registry for tracking available agents
- **Agent Discovery Service**: Service for discovering and registering agents
- **Load Balancer**: Distributes tasks across agents using various strategies
- **Task Distributor**: Manages task assignment and priority queues
- **Communication Manager**: Handles inter-agent communication protocols
- **Message Processor**: Processes and routes messages between agents

### AI Integration
- **Real-time Learning**: Adaptive learning system for task optimization
- **Advanced AI**: AI integration for decision making and coordination
- **Distributed Consensus**: Consensus mechanism for agent coordination decisions

### Security
- **JWT Authentication**: Token-based authentication for API access
- **Password Management**: Secure password handling and validation
- **API Key Management**: API key generation and validation
- **Role-Based Access Control**: Fine-grained permissions and roles
- **Security Headers**: Security middleware for HTTP headers

### Monitoring
- **Prometheus Metrics**: Performance metrics and monitoring
- **Performance Monitor**: Real-time performance tracking
- **Alert Manager**: Alerting system for critical events
- **SLA Monitor**: Service Level Agreement monitoring

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- PostgreSQL database
- Redis for caching
- Valid JWT token or API key

### Installation
```bash
cd /opt/aitbc/apps/agent-coordinator
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
DATABASE_URL=postgresql://user:pass@localhost/agent_coordinator
REDIS_URL=redis://localhost:6379
JWT_SECRET_KEY=your-secret-key
API_KEY=your-api-key
```

### Running the Service
```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9001
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Set up local database: See config.py for database settings
5. Run tests: `pytest tests/`

### Project Structure
```
agent-coordinator/
├── src/app/
│   ├── ai/              # AI integration modules
│   ├── auth/             # Authentication and authorization
│   ├── consensus/        # Distributed consensus
│   ├── coordination/     # Agent coordination logic
│   ├── decision/         # Decision making modules
│   ├── lifecycle/        # Agent lifecycle management
│   ├── main.py           # FastAPI application
│   ├── monitoring/       # Monitoring and metrics
│   ├── protocols/        # Communication protocols
│   └── routing/          # Agent discovery and routing
├── tests/                # Test suite
└── pyproject.toml        # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_agent_registry.py

# Run with coverage
pytest --cov=src tests/
```

## API Reference

### Agent Management

#### Register Agent
```http
POST /api/v1/agents/register
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "agent_id": "string",
  "agent_type": "string",
  "capabilities": ["string"],
  "endpoint": "string"
}
```

#### Discover Agents
```http
GET /api/v1/agents/discover
Authorization: Bearer <jwt_token>
```

#### Get Agent Status
```http
GET /api/v1/agents/{agent_id}/status
Authorization: Bearer <jwt_token>
```

### Task Management

#### Submit Task
```http
POST /api/v1/tasks/submit
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "task_type": "string",
  "payload": {},
  "priority": "high|medium|low",
  "requirements": {}
}
```

#### Get Task Status
```http
GET /api/v1/tasks/{task_id}/status
Authorization: Bearer <jwt_token>
```

#### List Tasks
```http
GET /api/v1/tasks?status=pending&limit=10
Authorization: Bearer <jwt_token>
```

### Load Balancing

#### Get Load Balancer Status
```http
GET /api/v1/loadbalancer/status
Authorization: Bearer <jwt_token>
```

#### Configure Load Balancing Strategy
```http
PUT /api/v1/loadbalancer/strategy
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "strategy": "round_robin|least_loaded|weighted",
  "parameters": {}
}
```

## Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `JWT_SECRET_KEY`: Secret key for JWT token signing
- `API_KEY`: API key for service authentication
- `LOG_LEVEL`: Logging level (default: INFO)
- `AGENT_DISCOVERY_INTERVAL`: Interval for agent discovery (default: 30s)
- `TASK_TIMEOUT`: Task timeout in seconds (default: 300)

### Load Balancing Strategies
- **Round Robin**: Distributes tasks evenly across agents
- **Least Loaded**: Assigns tasks to the agent with lowest load
- **Weighted**: Uses agent weights for task distribution

## Troubleshooting

**Agent not discovered**: Check agent registration endpoint and network connectivity.

**Task distribution failures**: Verify load balancer configuration and agent availability.

**Authentication errors**: Ensure JWT token is valid and not expired.

**Database connection errors**: Check DATABASE_URL and database server status.

## Security Notes

- Never expose JWT_SECRET_KEY in production
- Use HTTPS in production environments
- Implement rate limiting for API endpoints
- Regularly rotate API keys and JWT secrets
- Monitor for unauthorized access attempts
