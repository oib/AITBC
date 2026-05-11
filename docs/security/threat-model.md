# AITBC Threat Model

This document describes the threat model for the AITBC platform, identifying potential attackers, attack vectors, and security assumptions.

## System Overview

The AITBC platform consists of:
- Blockchain node (PoA consensus)
- Smart contracts (token, staking, governance)
- ZK proof circuits (Circom)
- Coordinator API (Python/FastAPI)
- Wallet daemon
- Agent services
- Marketplace service

## Assumptions

### Trust Assumptions
- Blockchain nodes are operated by trusted entities initially
- Smart contract code is immutable after deployment
- ZK proving system is cryptographically sound
- Private keys are properly secured by users

### Security Assumptions
- TLS is used for all network communication
- Authentication tokens are properly validated
- Input validation is performed on all endpoints
- Secrets are stored securely (environment variables, secret managers)

## Attackers

### External Attackers
- **Malicious Users:** Attempt to exploit vulnerabilities for financial gain
- **Network Attackers:** Intercept or manipulate network traffic
- **Smart Contract Attackers:** Exploit contract logic or reentrancy

### Internal Threats
- **Compromised Node Operators:** Malicious behavior by node operators
- **Insider Threats:** Unauthorized access by team members
- **Supply Chain Attacks:** Compromised dependencies or build processes

## Attack Vectors

### 1. Smart Contract Vulnerabilities

#### Reentrancy
- **Description:** Attacker calls back into contract before state update
- **Impact:** Drain funds from contract
- **Mitigation:** Use checks-effects-interactions pattern, reentrancy guards

#### Arithmetic Overflow/Underflow
- **Description:** Integer arithmetic exceeds bounds
- **Impact:** Incorrect calculations, potential fund loss
- **Mitigation:** Solidity 0.8+ has built-in overflow protection

#### Access Control
- **Description:** Unauthorized function execution
- **Impact:** Privilege escalation, fund theft
- **Mitigation:** Role-based access control, proper modifier usage

#### Front-running
- **Description:** Attacker sees transaction and submits competing transaction
- **Impact:** MEV extraction, transaction manipulation
- **Mitigation:** Commit-reveal schemes, batch auctions

### 2. ZK Proof Vulnerabilities

#### Circuit Vulnerabilities
- **Description:** Flaws in Circom circuit constraints
- **Impact:** False proofs accepted, privacy broken
- **Mitigation:** Formal verification, peer review, test vectors

#### Side-Channel Attacks
- **Description:** Information leaked through timing or other side channels
- **Impact:** Private information disclosure
- **Mitigation:** Constant-time operations, proper randomness

#### Trusted Setup Compromise
- **Description:** Toxic waste leaked from trusted setup
- **Impact:** False proofs can be generated
- **Mitigation:** Multi-party computation, secure destruction of waste

### 3. API Security Vulnerabilities

#### Injection Attacks
- **Description:** SQL injection, command injection
- **Impact:** Data breach, system compromise
- **Mitigation:** Parameterized queries, input validation

#### Authentication Bypass
- **Description:** Weak or missing authentication
- **Impact:** Unauthorized access
- **Mitigation:** Strong authentication, proper token validation

#### Rate Limiting Bypass
- **Description:** Attacker overwhelms API with requests
- **Impact:** DoS, resource exhaustion
- **Mitigation:** Rate limiting, circuit breakers

### 4. Network Security

#### Man-in-the-Middle
- **Description:** Attacker intercepts and modifies traffic
- **Impact:** Data manipulation, credential theft
- **Mitigation:** TLS, certificate pinning

#### DDoS Attacks
- **Description:** Overwhelm services with traffic
- **Impact:** Service unavailability
- **Mitigation:** Rate limiting, CDN, load balancing

### 5. Economic Attack Vectors

#### Sybil Attacks
- **Description:** Attacker creates multiple fake identities
- **Impact:** Manipulate consensus, rewards
- **Mitigation:** Identity verification, staking requirements

#### Pump and Dump
- **Description:** Manipulate token price
- **Impact:** Financial loss for users
- **Mitigation:** Liquidity locks, vesting periods

#### Governance Attacks
- **Description:** Manipulate governance decisions
- **Impact:** Protocol changes for malicious purposes
- **Mitigation:** Time locks, quorum requirements, delegation limits

## Security Controls

### Preventive Controls
- Code review and testing
- Static analysis (Bandit, Slither)
- Formal verification for critical components
- Access control and authentication
- Input validation and sanitization

### Detective Controls
- Logging and monitoring
- Anomaly detection
- Security scanning in CI/CD
- Audit trails

### Responsive Controls
- Incident response plan
- Emergency pause mechanisms
- Circuit breakers
- Hotfix deployment process

## Risk Assessment

| Component | Risk Level | Primary Threats |
|-----------|------------|-----------------|
| Smart Contracts | High | Reentrancy, access control, economic attacks |
| ZK Circuits | High | Circuit vulnerabilities, trusted setup |
| Coordinator API | Medium | Injection, auth bypass, DoS |
| Blockchain Node | Medium | Network attacks, consensus manipulation |
| Wallet Daemon | High | Key theft, phishing |
| Marketplace | Medium | Oracle manipulation, front-running |

## Ongoing Monitoring

- Security scanning in CI/CD pipeline
- Dependency vulnerability scanning
- Smart contract monitoring (events, balances)
- Network traffic analysis
- Anomaly detection on API endpoints

## Related Documents

- [Security Architecture](2_security-architecture.md)
- [Security Best Practices](best-practices.md)
- [Audit Findings](audit-findings.md)
- [Economic Analysis](economic-analysis.md)
