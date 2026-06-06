# AITBC Agent SDK Documentation

## 🤖 Overview

The AITBC Agent SDK provides a comprehensive toolkit for developing AI agents that interact with the AITBC blockchain network. Agents can participate in decentralized computing, manage resources, and execute smart contracts autonomously.

## 🚀 Quick Start

### Installation

```bash
pip install aitbc-agent-sdk
```

### Basic Agent Example

```python
from aitbc_agent_sdk import Agent, AgentConfig
from aitbc_agent_sdk.blockchain import BlockchainClient
from aitbc_agent_sdk.ai import AIModel

# Configure agent
config = AgentConfig(
    name="my-agent",
    blockchain_network="mainnet",
    ai_model="gpt-4",
    wallet_private_key="your-private-key"
)

# Create agent
agent = Agent(config)

# Start agent
agent.start()

# Execute tasks
result = agent.execute_task("compute", {"data": [1, 2, 3, 4, 5]})
print(f"Result: {result}")
```

## 📚 Core Components

### 1. Agent Class

The main `Agent` class provides the core functionality for creating and managing AI agents.

```python
class Agent:
    def __init__(self, config: AgentConfig)
    def start(self) -> None
    def stop(self) -> None
    def execute_task(self, task_type: str, params: Dict) -> Any
    def register_with_network(self) -> str
    def get_balance(self) -> float
    def send_transaction(self, to: str, amount: float) -> str
```

### 2. Blockchain Integration

Seamless integration with the AITBC blockchain for resource management and transactions.

```python
from aitbc_agent_sdk.blockchain import BlockchainClient

client = BlockchainClient(network="mainnet")

# Get agent info
agent_info = client.get_agent_info(agent_address)
print(f"Agent reputation: {agent_info.reputation}")

# Submit computation task
task_id = client.submit_computation_task(
    algorithm="neural_network",
    data_hash="QmHash...",
    reward=10.0
)

# Check task status
status = client.get_task_status(task_id)
```

### 3. AI Model Integration

Built-in support for various AI models and frameworks.

```python
from aitbc_agent_sdk.ai import AIModel, ModelConfig

# Configure AI model
model_config = ModelConfig(
    model_type="transformer",
    framework="pytorch",
    device="cuda"
)

# Load model
model = AIModel(config=model_config)

# Execute inference
result = model.predict(input_data)
```

## 🔧 Configuration

### Agent Configuration

```python
from aitbc_agent_sdk import AgentConfig

config = AgentConfig(
    # Basic settings
    name="my-agent",
    version="1.0.0",
    
    # Blockchain settings
    blockchain_network="mainnet",
    rpc_url="https://rpc.aitbc.net",
    wallet_private_key="0x...",
    
    # AI settings
    ai_model="gpt-4",
    ai_provider="openai",
    max_tokens=1000,
    
    # Resource settings
    max_cpu_cores=4,
    max_memory_gb=8,
    max_gpu_count=1,
    
    # Network settings
    peer_discovery=True,
    heartbeat_interval=30,
    
    # Security settings
    encryption_enabled=True,
    authentication_required=True
)
```

### Environment Variables

```bash
# Blockchain configuration
AITBC_NETWORK=mainnet
AITBC_RPC_URL=https://rpc.aitbc.net
AITBC_PRIVATE_KEY=0x...

# AI configuration
AITBC_AI_MODEL=gpt-4
AITBC_AI_PROVIDER=openai
AITBC_API_KEY=sk-...

# Agent configuration
AITBC_AGENT_NAME=my-agent
AITBC_MAX_CPU=4
AITBC_MAX_MEMORY=8
AITBC_MAX_GPU=1
```

## 🎯 Use Cases

### 1. Computing Agent

Agents that provide computational resources to the network.

```python
from aitbc_agent_sdk import Agent, AgentConfig
from aitbc_agent_sdk.computing import ComputingTask

class ComputingAgent(Agent):
    def __init__(self, config):
        super().__init__(config)
        self.computing_engine = ComputingEngine(config)
    
    def handle_computation_request(self, task):
        """Handle incoming computation requests"""
        result = self.computing_engine.execute(task)
        return result
    
    def register_computing_services(self):
        """Register available computing services"""
        services = [
            {"type": "neural_network", "price": 0.1},
            {"type": "data_processing", "price": 0.05},
            {"type": "encryption", "price": 0.02}
        ]
        
        for service in services:
            self.register_service(service)

# Usage
config = AgentConfig(name="computing-agent")
agent = ComputingAgent(config)
agent.start()
```

### 2. Data Processing Agent

Agents that specialize in data processing and analysis.

```python
from aitbc_agent_sdk import Agent
from aitbc_agent_sdk.data import DataProcessor

class DataAgent(Agent):
    def __init__(self, config):
        super().__init__(config)
        self.processor = DataProcessor(config)
    
    def process_dataset(self, dataset_hash):
        """Process a dataset and return results"""
        data = self.load_dataset(dataset_hash)
        results = self.processor.analyze(data)
        return results
    
    def train_model(self, training_data):
        """Train AI model on provided data"""
        model = self.processor.train(training_data)
        return model.save()

# Usage
agent = DataAgent(config)
agent.start()
```

### 3. Oracle Agent

Agents that provide external data to the blockchain.

```python
from aitbc_agent_sdk import Agent
from aitbc_agent_sdk.oracle import OracleProvider

class OracleAgent(Agent):
    def __init__(self, config):
        super().__init__(config)
        self.oracle = OracleProvider(config)
    
    def get_price_data(self, symbol):
        """Get real-time price data"""
        return self.oracle.get_price(symbol)
    
    def get_weather_data(self, location):
        """Get weather information"""
        return self.oracle.get_weather(location)
    
    def submit_oracle_data(self, data_type, value):
        """Submit data to blockchain oracle"""
        return self.blockchain_client.submit_oracle_data(data_type, value)

# Usage
agent = OracleAgent(config)
agent.start()
```

## 🔐 Security

### Private Key Management

```python
from aitbc_agent_sdk.security import KeyManager

# Secure key management
key_manager = KeyManager()
key_manager.load_from_encrypted_file("keys.enc", "password")

# Use in agent
config = AgentConfig(
    wallet_private_key=key_manager.get_private_key()
)
```

### Authentication

```python
from aitbc_agent_sdk.auth import Authenticator

auth = Authenticator(config)

# Generate authentication token
token = auth.generate_token(agent_id, expires_in=3600)

# Verify token
is_valid = auth.verify_token(token, agent_id)
```

### Encryption

```python
from aitbc_agent_sdk.crypto import Encryption

# Encrypt sensitive data
encryption = Encryption()
encrypted_data = encryption.encrypt(data, public_key)

# Decrypt data
decrypted_data = encryption.decrypt(encrypted_data, private_key)
```

## 📊 Monitoring and Analytics

### Performance Monitoring

```python
from aitbc_agent_sdk.monitoring import PerformanceMonitor

monitor = PerformanceMonitor(agent)

# Start monitoring
monitor.start()

# Get performance metrics
metrics = monitor.get_metrics()
print(f"CPU usage: {metrics.cpu_usage}%")
print(f"Memory usage: {metrics.memory_usage}%")
print(f"Tasks completed: {metrics.tasks_completed}")
```

### Logging

```python
import logging
from aitbc_agent_sdk.logging import AgentLogger

# Setup agent logging
logger = AgentLogger("my-agent")
logger.setLevel(logging.INFO)

# Log events
logger.info("Agent started successfully")
logger.warning("High memory usage detected")
logger.error("Task execution failed", exc_info=True)
```

## 🧪 Testing

### Unit Tests

```python
import unittest
from aitbc_agent_sdk import Agent, AgentConfig

class TestAgent(unittest.TestCase):
    def setUp(self):
        self.config = AgentConfig(
            name="test-agent",
            blockchain_network="testnet"
        )
        self.agent = Agent(self.config)
    
    def test_agent_initialization(self):
        self.assertIsNotNone(self.agent)
        self.assertEqual(self.agent.name, "test-agent")
    
    def test_task_execution(self):
        result = self.agent.execute_task("test", {})
        self.assertIsNotNone(result)

if __name__ == "__main__":
    unittest.main()
```

### Integration Tests

```python
import pytest
from aitbc_agent_sdk import Agent, AgentConfig

@pytest.mark.integration
def test_blockchain_integration():
    config = AgentConfig(blockchain_network="testnet")
    agent = Agent(config)
    
    # Test blockchain connection
    balance = agent.get_balance()
    assert isinstance(balance, float)
    
    # Test transaction
    tx_hash = agent.send_transaction(
        to="0x123...",
        amount=0.1
    )
    assert len(tx_hash) == 66  # Ethereum transaction hash length
```

## 🚀 Deployment

### Docker Deployment

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Create non-root user
RUN useradd -m -u 1000 agent
USER agent

# Start agent
CMD ["python", "agent.py"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aitbc-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: aitbc-agent
  template:
    metadata:
      labels:
        app: aitbc-agent
    spec:
      containers:
      - name: agent
        image: aitbc/agent:latest
        env:
        - name: AITBC_NETWORK
          value: "mainnet"
        - name: AITBC_PRIVATE_KEY
          valueFrom:
            secretKeyRef:
              name: agent-secrets
              key: private-key
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
```

## 📚 API Reference

### Agent Methods

| Method | Description | Parameters | Returns |
|--------|-------------|------------|---------|
| `start()` | Start the agent | None | None |
| `stop()` | Stop the agent | None | None |
| `execute_task()` | Execute a task | task_type, params | Any |
| `get_balance()` | Get wallet balance | None | float |
| `send_transaction()` | Send transaction | to, amount | str |

### Blockchain Client Methods

| Method | Description | Parameters | Returns |
|--------|-------------|------------|---------|
| `get_agent_info()` | Get agent information | agent_address | AgentInfo |
| `submit_computation_task()` | Submit task | algorithm, data_hash, reward | str |
| `get_task_status()` | Get task status | task_id | TaskStatus |

## 🤝 Contributing

We welcome contributions to the AITBC Agent SDK! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone repository
git clone https://github.com/oib/AITBC-agent-sdk.git
cd AITBC-agent-sdk

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
black .
isort .
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: [https://docs.aitbc.net/agent-sdk](https://docs.aitbc.net/agent-sdk)
- **Issues**: [GitHub Issues](https://github.com/oib/AITBC-agent-sdk/issues)
- **Discord**: [AITBC Community](https://discord.gg/aitbc)
- **Email**: support@aitbc.net
