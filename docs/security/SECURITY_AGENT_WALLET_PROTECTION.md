# AITBC Agent Wallet Security Model

## 🛡️ Overview

The AITBC autonomous agent wallet security model addresses the critical vulnerability where **compromised agents = drained wallets**. This document outlines the implemented guardian contract system that provides spending limits, time locks, and emergency controls for autonomous agent wallets.

## ⚠️ Security Problem Statement

### Current Vulnerability
- **Direct signing authority**: Agents have unlimited spending capability
- **Single point of failure**: Compromised agent = complete wallet drain
- **No spending controls**: No limits on transaction amounts or frequency
- **No emergency response**: No mechanism to halt suspicious activity

### Attack Scenarios
1. **Agent compromise**: Malicious code gains control of agent signing keys
2. **Logic exploitation**: Bugs in agent logic trigger excessive spending
3. **External manipulation**: Attackers influence agent decision-making
4. **Key leakage**: Private keys exposed through vulnerabilities

## 🔐 Security Solution: Guardian Contract System

### Core Components

#### 1. Guardian Contract
A smart contract that wraps agent wallets with security controls:
- **Spending limits**: Per-transaction, hourly, daily, weekly caps
- **Time locks**: Delayed execution for large transactions
- **Emergency controls**: Guardian-initiated pause/unpause
- **Multi-signature recovery**: Requires multiple guardian approvals

#### 2. Security Profiles
Pre-configured security levels for different agent types:
- **Conservative**: Low limits, high security (default)
- **Aggressive**: Higher limits, moderate security
- **High Security**: Very low limits, maximum protection

#### 3. Guardian Network
Trusted addresses that can intervene in emergencies:
- **Multi-sig approval**: Multiple guardians required for critical actions
- **Recovery mechanism**: Restore access after compromise
- **Override controls**: Emergency pause and limit adjustments

## 📊 Security Configurations

### Conservative Configuration (Default)
```python
{
    "per_transaction": 100,    # $100 per transaction
    "per_hour": 500,          # $500 per hour
    "per_day": 2000,          # $2,000 per day
    "per_week": 10000,        # $10,000 per week
    "time_lock_threshold": 1000,  # Time lock over $1,000
    "time_lock_delay": 24     # 24 hour delay
}
```

### Aggressive Configuration
```python
{
    "per_transaction": 1000,   # $1,000 per transaction
    "per_hour": 5000,         # $5,000 per hour
    "per_day": 20000,         # $20,000 per day
    "per_week": 100000,       # $100,000 per week
    "time_lock_threshold": 10000,  # Time lock over $10,000
    "time_lock_delay": 12     # 12 hour delay
}
```

### High Security Configuration
```python
{
    "per_transaction": 50,     # $50 per transaction
    "per_hour": 200,          # $200 per hour
    "per_day": 1000,          # $1,000 per day
    "per_week": 5000,         # $5,000 per week
    "time_lock_threshold": 500,   # Time lock over $500
    "time_lock_delay": 48     # 48 hour delay
}
```

## 🚀 Implementation Guide

### 1. Register Agent for Protection

```python
from aitbc_chain.contracts.agent_wallet_security import register_agent_for_protection

# Register with conservative security (default)
result = register_agent_for_protection(
    agent_address="0x1234...abcd",
    security_level="conservative",
    guardians=["0xguard1...", "0xguard2...", "0xguard3..."]
)

if result["status"] == "registered":
    print(f"Agent protected with limits: {result['limits']}")
```

### 2. Protect Transactions

```python
from aitbc_chain.contracts.agent_wallet_security import protect_agent_transaction

# Protect a transaction
result = protect_agent_transaction(
    agent_address="0x1234...abcd",
    to_address="0x5678...efgh",
    amount=500  # $500
)

if result["status"] == "approved":
    operation_id = result["operation_id"]
    # Execute with agent signature
    # execute_protected_transaction(agent_address, operation_id, signature)
elif result["status"] == "time_locked":
    print(f"Transaction locked for {result['delay_hours']} hours")
```

### 3. Emergency Response

```python
# Emergency pause by guardian
agent_wallet_security.emergency_pause_agent(
    agent_address="0x1234...abcd",
    guardian_address="0xguard1..."
)

# Unpause with multiple guardian signatures
agent_wallet_security.emergency_unpause(
    agent_address="0x1234...abcd",
    guardian_signatures=["sig1", "sig2", "sig3"]
)
```

## 🔍 Security Monitoring

### Real-time Monitoring
```python
# Get agent security status
status = get_agent_security_summary("0x1234...abcd")

# Check spending limits
spent_today = status["spending_status"]["spent"]["current_day"]
limit_today = status["spending_status"]["remaining"]["current_day"]

# Detect suspicious activity
suspicious = detect_suspicious_activity("0x1234...abcd", hours=24)
if suspicious["suspicious_activity"]:
    print(f"Suspicious patterns: {suspicious['suspicious_patterns']}")
```

### Security Reporting
```python
# Generate comprehensive security report
report = generate_security_report()

print(f"Protected agents: {report['summary']['total_protected_agents']}")
print(f"Active protection: {report['summary']['protection_coverage']}")
print(f"Emergency mode agents: {report['summary']['emergency_mode_agents']}")
```

## 🛠️ Integration with Agent Logic

### Modified Agent Transaction Flow
```python
class SecureAITBCAgent:
    def __init__(self, wallet_address: str, security_level: str = "conservative"):
        self.wallet_address = wallet_address
        self.security_level = security_level
        
        # Register for protection
        register_agent_for_protection(wallet_address, security_level)
    
    def send_transaction(self, to_address: str, amount: int, data: str = ""):
        # Protect transaction first
        result = protect_agent_transaction(self.wallet_address, to_address, amount, data)
        
        if result["status"] == "approved":
            # Execute immediately
            return self._execute_transaction(result["operation_id"])
        elif result["status"] == "time_locked":
            # Queue for later execution
            return self._queue_time_locked_transaction(result)
        else:
            # Transaction rejected
            raise Exception(f"Transaction rejected: {result['reason']}")
```

## 📋 Security Best Practices

### 1. Guardian Selection
- **Multi-sig guardians**: Use 3-5 trusted addresses
- **Geographic distribution**: Guardians in different jurisdictions
- **Key security**: Hardware wallets for guardian keys
- **Regular rotation**: Update guardians periodically

### 2. Security Level Selection
- **Conservative**: Default for most agents
- **Aggressive**: High-volume trading agents
- **High Security**: Critical infrastructure agents

### 3. Monitoring and Alerts
- **Real-time alerts**: Suspicious activity notifications
- **Daily reports**: Spending limit utilization
- **Emergency procedures**: Clear response protocols

### 4. Recovery Planning
- **Backup guardians**: Secondary approval network
- **Recovery procedures**: Steps for key compromise
- **Documentation**: Clear security policies

## 🔧 Technical Architecture

### Contract Structure
```
GuardianContract
├── SpendingLimit (per_transaction, per_hour, per_day, per_week)
├── TimeLockConfig (threshold, delay_hours, max_delay_hours)
├── GuardianConfig (limits, time_lock, guardians, pause_enabled)
└── State Management (spending_history, pending_operations, nonce)
```

### Security Flow
1. **Transaction Initiation** → Check limits
2. **Limit Validation** → Approve/Reject/Time-lock
3. **Time Lock** → Queue for delayed execution
4. **Guardian Intervention** → Emergency pause/unpause
5. **Execution** → Record and update limits

### Data Structures
```python
# Operation tracking
{
    "operation_id": "0x...",
    "type": "transaction",
    "to": "0x...",
    "amount": 1000,
    "timestamp": "2026-03-03T08:45:00Z",
    "status": "completed|pending|time_locked",
    "unlock_time": "2026-03-04T08:45:00Z"  # if time_locked
}

# Spending history
{
    "operation_id": "0x...",
    "amount": 500,
    "timestamp": "2026-03-03T07:30:00Z",
    "executed_at": "2026-03-03T07:31:00Z",
    "status": "completed"
}
```

## 🚨 Emergency Procedures

### 1. Immediate Response
1. **Identify compromise**: Detect suspicious activity
2. **Emergency pause**: Guardian initiates pause
3. **Assess damage**: Review transaction history
4. **Secure keys**: Rotate compromised keys

### 2. Recovery Process
1. **Multi-sig approval**: Gather guardian signatures
2. **Limit adjustment**: Reduce spending limits
3. **System update**: Patch vulnerability
4. **Resume operations**: Careful monitoring

### 3. Post-Incident
1. **Security audit**: Review all security controls
2. **Update guardians**: Rotate guardian addresses
3. **Improve monitoring**: Enhance detection capabilities
4. **Documentation**: Update security procedures

## 📈 Security Metrics

### Key Performance Indicators
- **Protection coverage**: % of agents under protection
- **Limit utilization**: Average spending vs. limits
- **Response time**: Emergency pause latency
- **False positives**: Legitimate transactions blocked

### Monitoring Dashboard
```python
# Real-time security metrics
metrics = {
    "total_agents": 150,
    "protected_agents": 148,
    "active_protection": "98.7%",
    "emergency_mode": 2,
    "daily_spending": "$45,000",
    "limit_utilization": "67%",
    "suspicious_alerts": 3
}
```

## 🔮 Future Enhancements

### Planned Features
1. **Dynamic limits**: AI-driven limit adjustment
2. **Behavioral analysis**: Machine learning anomaly detection
3. **Cross-chain protection**: Multi-blockchain security
4. **DeFi integration**: Protocol-specific protections

### Research Areas
1. **Zero-knowledge proofs**: Privacy-preserving security
2. **Threshold signatures**: Advanced multi-sig schemes
3. **Quantum resistance**: Post-quantum security
4. **Formal verification**: Mathematical security proofs

## 📚 References

### Related Documentation
- [AITBC Security Architecture](SECURITY_OVERVIEW.md)
- [Smart Contract Security](README.md)
- [Agent Development Guide](../11_agents/README.md)

### External Resources
- [Ethereum Smart Contract Security](https://consensys.github.io/smart-contract-best-practices/)
- [Multi-signature Wallet Standards](https://github.com/ethereum/EIPs/blob/master/EIPS/eip-2645.md)
- [Time-lock Contracts](https://github.com/ethereum/EIPs/blob/master/EIPS/eip-650.md)

---

**Security Status**: ✅ IMPLEMENTED  
**Last Updated**: March 3, 2026  
**Next Review**: March 17, 2026  

*This security model significantly reduces the attack surface for autonomous agent wallets while maintaining operational flexibility for legitimate activities.*
