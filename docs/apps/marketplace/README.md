# Marketplace Applications

GPU marketplace and pool hub services.

> **⚠️ DEPRECATION NOTICE (v0.4.7)**: GPU-only marketplace with bids has been deprecated. The marketplace now focuses on hardware+software bundles with fixed pricing.

## Applications

- [Marketplace](marketplace.md) - GPU marketplace for compute resources
- [Pool Hub](pool-hub.md) - Pool hub for resource pooling

## Features

- GPU resource marketplace
- Hardware+software bundle offers with fixed pricing
- Pool management
- Multi-chain support
- **Agent-centric APIs** for autonomous resource discovery and transaction execution
- **Reputation & trust system** for agent decision-making
- **Dynamic pricing** based on market conditions
- **Software service registry** (Ollama, Whisper, FFmpeg)
- **Escrow-based payments** with on-chain verification

## Agent Integration

The marketplace is designed for agent-first architecture with comprehensive APIs for:

- **Resource Discovery**: Intelligent filtering and ranking of GPU resources
- **Transaction Execution**: Automated offer booking and escrow management
- **Reputation Tracking**: On-chain reputation scores for trust-based decisions
- **Dynamic Pricing**: Real-time market data and price optimization

See [Marketplace Backend Analysis](../../development/11_marketplace-backend-analysis.md) for detailed implementation flows and agent API usage examples.
