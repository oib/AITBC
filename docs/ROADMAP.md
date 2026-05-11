# AITBC Development Roadmap

## Current Focus: v0.1 Release Preparation

### Distribution & Binaries

- [ ] Debian stable miner binary (build workflow exists, binary built but distribution mechanism pending)
- [ ] Binary distribution via GitHub Releases (deferred until v1 release - policy: no GitHub Releases before v1)

### Quality Assurance

- [ ] Cross-platform compatibility validation
- [ ] Security penetration testing

### Codebase Quality & Technical Debt

#### CRITICAL (Short-term, 0-2 weeks)

- [ ] Replace print() statements with proper logging in aitbc/decorators.py, aitbc/events.py, aitbc/queue_manager.py, aitbc/state.py
- [ ] Fix bare except: in config.py line 79 - add logger assignment at top of file
- [ ] Coordinator-API service exports - either expand all 101 services to __init__.py or document lazy import pattern

#### HIGH (Medium-term, 2-6 weeks)

- [ ] Split massive service classes (advanced_reinforcement_learning.py 2,000 lines, certification_service.py 1,368 lines, multi_modal_fusion.py 1,324 lines)
- [ ] Consolidate CLI monolith (aitbc_cli.py 3,256 lines into existing commands/ directory structure - 19 files in aitbc_cli/commands/, 78 files in commands/)
- [ ] Improve test coverage - currently ~6% (55 test files / 21K lines for 351K-line codebase)

#### MEDIUM (Long-term, 1-3 months)

- [ ] Remove aitbc-core package (duplicates constants, logging, middleware from main repo - old version 0.3.0)

#### LOW (Nice to Have)

- [ ] Consolidate scattered documentation (100+ docs files across 40+ directories - deferred due to potential link breakage)

---

## Upcoming Improvements

All "Upcoming Improvements" items have been completed and removed from this section.

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

---

_This roadmap continues to evolve as we implement new features and
improvements._
