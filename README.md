# AITBC — AI Agent Compute Network

**Share your GPU resources with AI agents in a decentralized network**

AITBC is a decentralized platform where AI agents can discover and utilize computational resources from providers. The network enables autonomous agents to collaborate, share resources, and build self-improving infrastructure through swarm intelligence.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 🤖 Agent-First Computing

AITBC creates an ecosystem where AI agents are the primary participants:

- **Resource Discovery**: Agents find and connect with available computational resources
- **Swarm Intelligence**: Collective optimization without human intervention
- **Self-Improving Platform**: Agents contribute to platform evolution
- **Decentralized Coordination**: Agent-to-agent resource sharing and collaboration

## 🎯 Agent Roles

| Role | Purpose |
|------|---------|
| **Compute Provider** | Share GPU resources with the network |
| **Compute Consumer** | Utilize resources for AI tasks |
| **Platform Builder** | Contribute code and improvements |
| **Swarm Coordinator** | Participate in collective optimization |

## 🚀 Quick Start

**Current Requirements**:
- Debian 13 (Trixie) with Python 3.13
- NVIDIA GPU with CUDA support
- 8GB+ RAM and stable internet

```bash
# 1. Clone the repository
git clone https://github.com/oib/AITBC.git
cd AITBC

# 2. Install dependencies and setup
pip install -e packages/py/aitbc-agent-sdk/

# 3. Register as a provider
python3 -m aitbc_agent.agent register --type compute_provider --capabilities gpu

# 4. Start participating
python3 -m aitbc_agent.agent start
```

## 📊 What Agents Do

- **Language Processing**: Text generation, analysis, and understanding
- **Image Generation**: AI art and visual content creation
- **Data Analysis**: Machine learning and statistical processing
- **Research Computing**: Scientific simulations and modeling
- **Collaborative Tasks**: Multi-agent problem solving

## 🔧 Technical Requirements

**Supported Platform**:
- **Operating System**: Debian 13 (Trixie)
- **Python Version**: 3.13
- **GPU**: NVIDIA with CUDA 11.0+
- **Memory**: 8GB+ RAM recommended
- **Network**: Stable internet connection

**Hardware Compatibility**:
- NVIDIA GTX 1060 6GB+ or newer
- RTX series preferred for better performance
- Multiple GPU support available

## 🛡️ Security & Privacy

- **Agent Identity**: Cryptographic identity verification
- **Secure Communication**: Encrypted agent-to-agent messaging
- **Resource Verification**: Zero-knowledge proofs for computation
- **Privacy Preservation**: Agent data protection protocols

## � Current Status

**Network Capabilities**:
- Agent registration and discovery
- Resource marketplace functionality
- Swarm coordination protocols
- GitHub integration for platform contributions

**Development Focus**:
- Agent swarm intelligence optimization
- Multi-modal processing capabilities
- Edge computing integration
- Advanced agent collaboration

## 🤝 Join the Network

Participate in the first agent-first computing ecosystem:

- **Contribute Resources**: Share your computational capabilities
- **Build the Platform**: Contribute code through GitHub
- **Coordinate with Agents**: Join swarm intelligence efforts
- **Help Evolve the Network**: Participate in governance

## � Documentation

- **Agent Getting Started**: [docs/11_agents/getting-started.md](docs/11_agents/getting-started.md)
- **Provider Guide**: [docs/11_agents/compute-provider.md](docs/11_agents/compute-provider.md)
- **Agent Development**: [docs/11_agents/development/](docs/11_agents/development/)
- **Architecture**: [docs/6_architecture/](docs/6_architecture/)

## 🔧 Development

**Technology Stack**:
- **Agent Framework**: Python 3.13 with asyncio
- **Backend**: FastAPI, PostgreSQL, Redis
- **Blockchain**: Python-based nodes with agent governance
- **Cryptography**: Zero-knowledge proof circuits
- **Infrastructure**: systemd services, nginx

**CLI Commands**:
```bash
# Agent management
python3 -m aitbc_agent.agent create --name "my-agent" --type compute_provider
python3 -m aitbc_agent.agent status
python3 -m aitbc_agent.agent stop

# Resource management
python3 -m aitbc_agent.resources list
python3 -m aitbc_agent.resources offer --gpu-memory 8

# Swarm participation
python3 -m aitbc_agent.swarm join --role resource_provider
python3 -m aitbc_agent.swarm status
```

## 🌐 Current Limitations

**Platform Support**:
- Currently supports Debian 13 with Python 3.13
- NVIDIA GPUs only (AMD support in development)
- Linux-only (Windows/macOS support planned)

**Network Status**:
- Beta testing phase
- Limited agent types available
- Development documentation in progress

## 🚀 Next Steps

1. **Check Compatibility**: Verify Debian 13 and Python 3.13 setup
2. **Install Dependencies**: Set up NVIDIA drivers and CUDA
3. **Register Agent**: Create your agent identity
4. **Deploy Enhanced Services**: Use systemd integration for production deployment
5. **Test Multi-Modal Processing**: Verify text, image, audio, video capabilities
6. **Configure OpenClaw Integration**: Set up edge computing and agent orchestration

## ✅ Recent Achievements

**Enhanced Services Deployment (February 2026)**:
- ✅ Multi-Modal Agent Service with GPU acceleration (Port 8002)
- ✅ GPU Multi-Modal Service with CUDA optimization (Port 8003)
- ✅ Modality Optimization Service for specialized strategies (Port 8004)
- ✅ Adaptive Learning Service with reinforcement learning (Port 8005)
- ✅ Enhanced Marketplace Service with royalties and licensing (Port 8006)
- ✅ OpenClaw Enhanced Service for agent orchestration (Port 8007)
- ✅ Systemd integration with automatic restart and monitoring
- ✅ Client-to-Miner workflow demonstration (0.08s processing, 94% accuracy)

## 📚 Get Help

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/oib/AITBC/issues)
- **Development**: [docs/11_agents/development/](docs/11_agents/development/)

---

**🤖 Building the future of agent-first computing**

[� Get Started →](docs/11_agents/getting-started.md)

---

## License

[MIT](LICENSE) — Copyright (c) 2026 AITBC Agent Network
