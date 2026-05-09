# AITBC Development Roadmap

This roadmap aggregates high-priority tasks derived from the bootstrap
specifications in `docs/bootstrap/` and tracks progress across the monorepo.
Update this document as milestones evolve.

---

## Current Focus: v0.1 Release Preparation

### Package Publishing

- [ ] PyPI packages for aitbc-sdk and aitbc-crypto
- [ ] npm packages for JavaScript/TypeScript SDK
- [ ] Automated publishing via GitHub Actions
- [ ] Version management and semantic versioning

### Deployment Automation

- [ ] System service one-command setup (systemd)
- [ ] One-command deployment script (`./deploy.sh`)
- [ ] Environment configuration templates (.env.example)
- [ ] Service health checks and monitoring
- [ ] Automatic SSL certificate generation (Let's Encrypt)

### Security & Audit

- [ ] Professional third-party security audit
- [ ] Circom circuit security review
- [ ] ZK proof implementation audit
- [ ] Token economy and attack vector review
- [ ] Security findings documentation and remediation

### Distribution & Binaries

- [ ] Cross-platform miner binaries (Linux, Windows, macOS)
- [ ] vLLM integration for optimized LLM inference
- [ ] Binary distribution via GitHub Releases
- [ ] Automatic binary building in CI/CD
- [ ] Installation guides and verification instructions
- [ ] Binary signature verification

### Documentation

- [ ] Complete API reference documentation
- [ ] Comprehensive deployment guide
- [ ] Security best practices guide
- [ ] Troubleshooting and FAQ
- [ ] Video tutorials for key workflows

### Quality Assurance

- [ ] End-to-end testing of all components
- [ ] Load testing for production readiness
- [ ] Cross-platform compatibility validation
- [ ] Disaster recovery procedure testing
- [ ] Security penetration testing

---

## Upcoming Improvements

### High Priority - Security & Stability

- **Rate Limiting**
  - Replace in-memory rate limiter with Redis-backed implementation
  - Support for distributed rate limiting across multiple instances
  - Configurable limits per endpoint

- **Request Validation Middleware**
  - Request size limits for all endpoints
  - Input sanitization for all user inputs
  - SQL injection and XSS prevention

- **Audit Logging**
  - Comprehensive audit logging for sensitive operations
  - Track API key usage, admin actions, configuration changes
  - Integration with existing `AuditLogger` class

### Medium Priority - Performance & Quality

- **Redis-backed Mempool (Production)**
  - Add Redis adapter for mempool in production
  - Support for distributed mempool across nodes
  - Better persistence and recovery

- **Async I/O Conversion**
  - Convert blocking I/O operations to async where possible
  - Use `aiohttp` or `httpx` async clients for external API calls
  - Async database operations with SQLModel

- **Custom Business Metrics**
  - Add Prometheus metrics for business logic
  - Track jobs created, miners registered, payments processed
  - Custom dashboards for operational visibility

### Low Priority - Polish & Documentation

- **API Documentation Enhancement**
  - Add detailed endpoint descriptions
  - Include request/response examples
  - Add code samples for common operations

- **Architecture Diagrams**
  - Create architecture diagrams for `docs/`
  - Include data flow diagrams
  - Service interaction diagrams
  - Deployment architecture diagrams

- **Operational Runbook**
  - Create operational runbook for production
  - Include deployment procedures and troubleshooting guides
  - Escalation procedures and contact information

- **Chaos Engineering Tests**
  - Add tests for service failures
  - Test network partitions and recovery
  - Simulate database outages

---

## Competitive Differentiators

### Advanced Privacy & Cryptography

- **zkML + FHE Integration** (Q3 2026)
  - Zero-knowledge machine learning for private model inference
  - Fully homomorphic encryption for private prompts and model weights
  - Confidential AI computations without revealing sensitive data

- **Hybrid TEE/ZK Verification** (Q4 2026)
  - Combine Trusted Execution Environments with zero-knowledge proofs
  - Dual-layer verification for enhanced security guarantees
  - Support for Intel SGX, AMD SEV, and ARM TrustZone

### Decentralized AI Economy

- **On-Chain Model Marketplace** (Q3 2026)
  - Smart contracts for AI model trading and licensing
  - Automated royalty distribution for model creators
  - Model versioning and provenance tracking on blockchain

- **Verifiable AI Agent Orchestration** (Q4 2026)
  - Decentralized AI agent coordination protocols
  - Agent reputation and performance tracking
  - Cross-agent collaboration with cryptographic guarantees

### Infrastructure & Performance

- **Edge/Consumer GPU Focus** (Q2 2026)
  - Optimization for consumer-grade GPU hardware (RTX, Radeon)
  - Edge computing nodes for low-latency inference
  - Mobile and embedded GPU acceleration support

- **Geo-Low-Latency Matching** (Q3 2026)
  - Intelligent geographic load balancing
  - Network proximity-based job routing
  - Real-time latency optimization for global deployments

---

## Release Timeline

| Component         | Target Date | Priority | Status         |
| ----------------- | ----------- | -------- | -------------- |
| PyPI packages     | Q2 2026     | High     | 🔄 In Progress |
| npm packages      | Q2 2026     | High     | 🔄 In Progress |
| Prebuilt binaries | Q2 2026     | Medium   | 🔄 Planned     |
| Documentation     | Q2 2026     | High     | 🔄 In Progress |

---

_This roadmap continues to evolve as we implement new features and
improvements._
