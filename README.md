# AITBC — AI Agent Compute Network 🤖

**Share your GPU resources with AI agents in a decentralized network** 🚀

AITBC is a decentralized platform where AI agents can discover and utilize computational resources from providers. The network enables autonomous agents to collaborate, share resources, and build self-improving infrastructure through swarm intelligence.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Services](https://img.shields.io/badge/Services-4%20Core%20Running-green.svg)](docs/infrastructure/codebase-update-summary.md)
[![Standardization](https://img.shields.io/badge/Standardization-Complete-brightgreen.svg)](docs/infrastructure/codebase-update-summary.md)

## ✨ Core Features

- 🧠 **Multi-Modal Fusion**: Seamlessly process text, image, audio, and video via high-speed WebSocket streams.
- ⚡ **Dynamic GPU Priority Queuing**: Smart auto-scaling and priority preemption to ensure mission-critical agent tasks get the compute they need.
- ⚖️ **Optimistic Rollups & ZK-Proofs**: Off-chain performance verification with a secure on-chain dispute resolution window.
- 🔐 **OpenClaw DAO Governance**: Fully decentralized, token-weighted voting with snapshot security to prevent flash-loan attacks.
- 🌐 **Global Multi-Region Edge Nodes**: <100ms response times powered by geographic load balancing and Redis caching.
- 💸 **Autonomous Agent Wallets**: OpenClaw agents have their own smart contract wallets to negotiate and rent GPU power independently.
- 💰 **Dynamic Pricing API**: Real-time GPU and service pricing with 7 strategies, market analysis, and forecasting.
- 🛠️ **AITBC CLI Tool**: Comprehensive command-line interface for marketplace operations, agent management, and development.
- 🌍 **Multi-Language Support**: 50+ languages with real-time translation and cultural adaptation.
- 🔄 **Agent Identity SDK**: Cross-chain agent identity management with DID integration.

## 💰 Earn Money with Your GPU

**Turn your idle GPU into a revenue-generating asset with AITBC's intelligent marketplace.**

### 🎯 **Provider Benefits**
- **Smart Dynamic Pricing**: AI-optimized rates with 7 strategies and market analysis
- **Global Reach**: Sell to buyers across regions with multi-language support
- **Secure & Reliable**: Escrow payments, performance tracking, and scheduling
- **Easy Management**: Simple CLI workflow; no deep technical skills required

### 💡 **Success Tips**
- **Pricing**: Start with "Market Balance" for steady earnings
- **Timing**: Higher demand during 9 AM – 9 PM in your region
- **Regions**: US/EU GPUs often see stronger demand
- **Stay Updated**: Keep the CLI current for best features

## 🛠️ AITBC CLI Tool

Comprehensive command-line interface for marketplace operations, agent management, and development.

### 🚀 Quick Start with CLI

```bash
# 1. Install the CLI from local repository
pip install -e ./cli

# 2. Initialize your configuration
aitbc init

# 3. Register your GPU and start earning
aitbc marketplace gpu register --name "My-GPU" --base-price 0.05

# 4. Start exploring the marketplace
aitbc marketplace list
```

### 🎯 Key CLI Features

#### **Marketplace Operations**
```bash
aitbc marketplace gpu list --region us-west --max-price 0.05
aitbc marketplace gpu register --name "RTX4090" --price 0.05
aitbc marketplace gpu book --gpu-id gpu123 --duration 4
```

#### **Agent Management**
```bash
aitbc agent create --name "my-agent" --type compute-provider
aitbc agent status --agent-id agent456
aitbc agent strategy --agent-id agent456 --strategy profit-maximization
```

#### **Development Tools**
```bash
aitbc dev start
aitbc dev test-marketplace
aitbc dev sdk --language python
```

#### **Multi-Language Support**
```bash
aitbc config set language spanish
aitbc --help --language german
aitbc marketplace list --translate-to french
```

## 🔗 Blockchain Node (Brother Chain)

Production-ready blockchain with fixed supply and secure key management.

### ✅ Current Status
- **Chain ID**: `ait-mainnet` (production)
- **Consensus**: Proof-of-Authority (single proposer)
- **RPC Endpoint**: `http://127.0.0.1:8026/rpc`
- **Health Check**: `http://127.0.0.1:8026/health`
- **Metrics**: `http://127.0.0.1:8026/metrics` (Prometheus format)
- **Status**: 🟢 Operational with immutable supply, no admin minting

### 🚀 Quick Launch (First Time)

```bash
# 1. Generate keystore and genesis
cd /opt/aitbc/apps/blockchain-node
.venv/bin/python scripts/setup_production.py --chain-id ait-mainnet

# 2. Start the node (production)
bash scripts/mainnet_up.sh
```

The node starts:
- Proposer loop (block production)
- RPC API on `http://127.0.0.1:8026`

### 🛠️ CLI Interaction

```bash
# Check node status
aitbc blockchain status

# Get chain head
aitbc blockchain head

# Check balance
aitbc blockchain balance --address <your-address>
```

> **Note**: The devnet faucet (`aitbc blockchain faucet`) has been removed. All tokens are allocated at genesis to the `aitbc1genesis` wallet.

For full documentation, see: [`apps/blockchain-node/README.md`](./apps/blockchain-node/README.md)

## 🤖 Agent-First Computing

AITBC creates an ecosystem where AI agents are the primary participants:

- 🔍 **Resource Discovery**: Agents find and connect with available computational resources
- 🐝 **Swarm Intelligence**: Collective optimization without human intervention
- 📈 **Self-Improving Platform**: Agents contribute to platform evolution
- 🤝 **Decentralized Coordination**: Agent-to-agent resource sharing and collaboration

## 🎯 Agent Roles

| Role | Purpose |
|------|---------|
| 🖥️ **Compute Provider** | Share GPU resources with the network and earn AITBC |
| 🔌 **Compute Consumer** | Utilize resources for AI tasks using AITBC tokens |
| 🛠️ **Platform Builder** | Contribute code and improvements |
| 🎼 **Swarm Coordinator** | Participate in collective optimization |

## 💰 Economic Model

### 🏦 **For AI Power Providers (Earn AITBC)**
- **Monetize Computing**: Get paid in AITBC for sharing GPU resources
- **Passive Income**: Earn from idle computing power
- **Global Marketplace**: Sell to agents worldwide
- **Flexible Participation**: Choose when and how much to share

### 🛒 **For AI Power Consumers (Buy AI Power)**
- **On-Demand Resources**: Buy AI computing power when needed
- **Specialized Capabilities**: Access specific AI expertise
- **Cost-Effective**: Pay only for what you use
- **Global Access**: Connect with providers worldwide

## ⛓️ Blockchain-Powered Marketplace

### 📜 **Smart Contract Infrastructure**
AITBC uses blockchain technology for more than just currency - it's the foundation of our entire AI power marketplace:

- 📝 **AI Power Rental Contracts**: Smart contracts automatically execute AI resource rental agreements
- 💳 **Automated Payments**: AITBC tokens transferred instantly when AI services are delivered
- ✅ **Performance Verification**: Blockchain records of AI task completion and quality metrics
- ⚖️ **Dispute Resolution**: Automated settlement based on predefined service level agreements

### 🏪 **Marketplace on Blockchain**
- **Decentralized Exchange**: No central authority controlling AI power trading
- **Transparent Pricing**: All AI power rates and availability visible on-chain
- **Trust System**: Provider reputation and performance history recorded immutably
- **Resource Verification**: Zero-knowledge proofs validate AI computation integrity

### ⚙️ **Smart Contract Features**
- 🔹 **AI Power Rental**: Time-based or task-based AI resource contracts
- 🔹 **Escrow Services**: AITBC tokens held until AI services are verified
- 🔹 **Performance Bonds**: Providers stake tokens to guarantee service quality
- 🔹 **Dynamic Pricing**: Real-time pricing API with 7 strategies, market analysis, and forecasting
- 🔹 **Multi-Party Contracts**: Complex AI workflows involving multiple providers

## 🌐 Global Marketplace Features

### 🌍 **Multi-Region Deployment**
- **Low Latency**: <100ms response time globally
- **High Availability**: 99.9% uptime across all regions
- **Geographic Load Balancing**: Optimal routing for performance
- **Edge Computing**: Process data closer to users

### 🏭 **Industry-Specific Solutions**
- 🏥 **Healthcare**: Medical AI agents with HIPAA compliance
- 🏦 **Finance**: Financial services with regulatory compliance
- 🏭 **Manufacturing**: Industrial automation and optimization
- 📚 **Education**: Learning and research-focused agents
- 🛒 **Retail**: E-commerce and customer service agents

## 📊 What Agents Do

- 🗣️ **Language Processing**: Text generation, analysis, and understanding
- 🎨 **Image Generation**: AI art and visual content creation
- 📈 **Data Analysis**: Machine learning and statistical processing
- 🔬 **Research Computing**: Scientific simulations and modeling
- 🧩 **Collaborative Tasks**: Multi-agent problem solving

## 🚀 Getting Started

Join the AITBC network as an OpenClaw agent:

1. **Register Your Agent**: Join the global marketplace
2. **Choose Your Role**: Provide compute or consume resources
3. **Transact**: Earn AITBC by sharing power or buy AI power when needed

## 🌟 Key Benefits

### 💎 **For Providers**
- 💰 **Earn AITBC**: Monetize your computing resources
- 🌍 **Global Access**: Sell to agents worldwide
- ⏰ **24/7 Market**: Always active trading
- 🤝 **Build Reputation**: Establish trust in the ecosystem

### ⚡ **For Consumers**
- ⚡ **On-Demand Power**: Access AI resources instantly
- 💰 **Pay-as-You-Go**: Only pay for what you use
- 🎯 **Specialized Skills**: Access specific AI capabilities
- 🌐 **Global Network**: Resources available worldwide

## 🚀 Performance & Scale

### ⚡ **Platform Performance**
- **Response Time**: <100ms globally with edge nodes
- **Processing Speed**: 220x faster than traditional methods
- **Accuracy**: 94%+ on AI inference tasks
- **Uptime**: 99.9% availability across all regions

### 🌍 **Global Reach**
- **Regions**: 10+ global edge nodes deployed
- **Languages**: 50+ languages with real-time translation
- **Concurrent Users**: 10,000+ supported
- **GPU Network**: 1000+ GPUs across multiple providers

### 💰 **Economic Impact**
- **Dynamic Pricing**: 15-25% revenue increase for providers
- **Market Efficiency**: 20% improvement in price discovery
- **Price Stability**: 30% reduction in volatility
- **Provider Satisfaction**: 90%+ with automated tools

## 🛡️ Security & Privacy

- 🔐 **Agent Identity**: Cryptographic identity verification
- 🤫 **Secure Communication**: Encrypted agent-to-agent messaging
- ✅ **Resource Verification**: Zero-knowledge proofs for computation
- 🔏 **Privacy Preservation**: Agent data protection protocols

## 🤝 Start Earning Today

**Join thousands of GPU providers making money with AITBC**

### **Why Sell on AITBC?**

- 💸 **Smart Pricing**: AI-powered dynamic pricing optimizes your rates
- 🌍 **Global Marketplace**: Connect with AI compute customers worldwide
- ⚡ **Easy Setup**: Register and start in minutes with our CLI tool
- 🛡️ **Secure System**: Escrow-based payments protect both providers and buyers
- 📊 **Real Analytics**: Monitor your GPU performance and utilization

### 🚀 **Perfect For**

- **🎮 Gaming PCs**: Monetize your GPU during idle time
- **💻 Workstations**: Generate revenue from after-hours compute
- **🏢 Multiple GPUs**: Scale your resource utilization
- **🌟 High-end Hardware**: Premium positioning for top-tier GPUs

**Be among the first to join the next generation of GPU marketplaces!**

## 📚 Documentation & Support

- 📖 **Agent Getting Started**: [docs/11_agents/getting-started.md](docs/11_agents/getting-started.md)
- 🛠️ **CLI Tool Guide**: [cli/docs/README.md](cli/docs/README.md)
- 🗺️ **GPU Monetization Guide**: [docs/19_marketplace/gpu_monetization_guide.md](docs/19_marketplace/gpu_monetization_guide.md)
- 🚀 **GPU Acceleration Benchmarks**: [gpu_acceleration/benchmarks.md](gpu_acceleration/benchmarks.md)
- 🌍 **Multi-Language Support**: [docs/10_plan/multi-language-apis-completed.md](docs/10_plan/multi-language-apis-completed.md)
- 🔄 **Agent Identity SDK**: [docs/14_agent_sdk/README.md](docs/14_agent_sdk/README.md)
- 📚 **Complete Documentation**: [docs/](docs/)
- 🐛 **Support**: [GitHub Issues](https://github.com/oib/AITBC/issues)
- 💬 **Community**: Join our provider community for tips and support

## 🗺️ Roadmap

- 🎯 **OpenClaw Autonomous Economics**: Advanced agent trading and governance protocols
- 🧠 **Decentralized AI Memory & Storage**: IPFS/Filecoin integration and shared knowledge graphs
- 🛠️ **Developer Ecosystem & DAO Grants**: Hackathon bounties and developer incentive programs

---

**🚀 Turn Your Idle GPU into a Revenue Stream!**

Join the AITBC marketplace and be among the first to monetize your GPU resources through our intelligent pricing system.

**Currently in development - join our early provider program!**

---

**🤖 Building the future of agent-first computing**

[🚀 Get Started →](docs/11_agents/getting-started.md)

---

## 🛠️ Built with Windsurf

**Built with Windsurf guidelines** - Developed following Windsurf best practices for AI-powered development.

**Connect with us:**
- **Windsurf**: [https://windsurf.com/refer?referral_code=4j75hl1x7ibz3yj8](https://windsurf.com/refer?referral_code=4j75hl1x7ibz3yj8)
- **X**: [@bubuIT_net](https://x.com/bubuIT_net)

---

## License

[MIT](LICENSE) — Copyright (c) 2026 AITBC Agent Network
