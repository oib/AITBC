# Security

## Overview

This document covers security considerations for the Governance Service, including authentication, authorization, data protection, and best practices.

## Authentication

### Service-to-Service Authentication

API endpoints require API key authentication for service-to-service communication.

**Implementation:**
```python
# In main.py
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key

@app.get("/v1/governance/proposals", dependencies=[Depends(verify_api_key)])
async def get_proposals():
    ...
```

**Configuration:**
```bash
export API_KEY=your_secure_api_key
```

### Wallet-Based Authentication

CLI commands use wallet-based authentication for blockchain operations.

**Implementation:**
```python
# Wallet signing
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

def sign_message(private_key, message):
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return signature
```

## Authorization

### Role-Based Access Control

User roles determine access levels:

| Role | Permissions |
|------|-------------|
| admin | Full access to all operations |
| voter | Can vote on proposals |
| proposer | Can create proposals |
| viewer | Read-only access |

**Implementation:**
```python
# In governance_service.py
async def check_permission(user_id: str, required_role: str):
    profile = await self.get_profile_by_user_id(user_id)
    if not profile or profile.role != required_role:
        raise PermissionError("Insufficient permissions")
```

### Token-Based Authorization

Voting power is determined by token holdings and staking:

```python
# Voting power calculation
voting_power = token_balance + (staked_tokens * 2)
```

## Data Protection

### Encryption at Rest

**PostgreSQL:**
```sql
-- Enable encryption
ALTER DATABASE aitbc_governance WITH ENCRYPTION = true;
```

**SQLite:**
- Use full-disk encryption (LUKS, BitLocker)
- Encrypt database file with tools like sqlcipher

### Encryption in Transit

**TLS/SSL Configuration:**
```nginx
# Nginx configuration
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/governance.crt;
    ssl_certificate_key /etc/ssl/private/governance.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
}
```

### Sensitive Data Handling

**Environment Variables:**
- Never commit secrets to version control
- Use `.env` files (add to .gitignore)
- Use secret management systems (HashiCorp Vault, AWS Secrets Manager)

**Example .env file:**
```bash
DB_PASS=your_secure_password
API_KEY=your_secure_api_key
PRIVATE_KEY=0x...
```

## Smart Contract Security

### Reentrancy Protection

The contracts use Solidity 0.8+ which has built-in overflow protection and follow the checks-effects-interactions pattern.

**Example:**
```solidity
function unstake(uint256 amount) external {
    require(stakedTokens[msg.sender] >= amount, "Insufficient staked tokens");
    require(block.timestamp >= stakeLockEnd[msg.sender], "Stake still locked");
    
    // Checks
    // Effects
    stakedTokens[msg.sender] -= amount;
    
    // Interactions
    _transfer(address(this), msg.sender, amount);
}
```

### Access Control

**AITBCGovernanceToken.sol:**
- Only owner can mint tokens (initial deployment)
- Anyone can stake/unstake their own tokens

**AITBCVoting.sol:**
- Anyone can create proposals
- Token holders can vote
- Anyone can execute passed proposals

### Time Manipulation Protection

**Execution Delay:**
- 1-day delay after voting ends before execution
- Prevents front-running and manipulation

**Lock Periods:**
- Minimum 30-day lock period for staking
- Prevents short-term manipulation

## Input Validation

### API Input Validation

**Pydantic Models:**
```python
from pydantic import BaseModel, Field, validator

class StakeRequest(BaseModel):
    staker_address: str = Field(..., regex=r"^0x[a-fA-F0-9]{40}$")
    amount: int = Field(..., gt=0)
    lock_period_days: int = Field(..., ge=30)
    
    @validator('amount')
    def validate_amount(cls, v):
        if v > 1_000_000_000 * 10**18:
            raise ValueError("Amount exceeds total supply")
        return v
```

### SQL Injection Prevention

**SQLModel automatically prevents SQL injection:**
```python
# Safe - parameterized query
stmt = select(Proposal).where(Proposal.proposal_id == proposal_id)

# Never do this - vulnerable to SQL injection
# stmt = f"SELECT * FROM proposals WHERE proposal_id = '{proposal_id}'"
```

### Smart Contract Input Validation

```solidity
function createProposal(
    string memory proposalType,
    string memory title,
    string memory description,
    bytes memory value,
    uint256 votingPeriod
) external returns (bytes32) {
    require(votingPeriod >= MIN_VOTING_PERIOD, "Voting period too short");
    require(votingPeriod <= MAX_VOTING_PERIOD, "Voting period too long");
    // ...
}
```

## Rate Limiting

### API Rate Limiting

**Implementation:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/v1/governance/proposals")
@limiter.limit("100/minute")
async def get_proposals():
    ...
```

**Limits:**
- 100 requests per minute per IP
- 1000 requests per hour per IP

### Smart Contract Gas Limits

**Gas optimization:**
- Packed structs
- View functions for read operations
- Event indexing for efficient filtering

## Audit Logging

### Service Logs

**Systemd journal:**
```bash
sudo journalctl -u aitbc-governance -f
```

**Application logs:**
```python
logger.info(f"Proposal {proposal_id} created by {proposer_id}")
logger.warning(f"Failed to execute proposal {proposal_id}: {error}")
logger.error(f"Database connection failed: {error}")
```

### Audit Trail

**Proposal execution log:**
```python
execution_log = ProposalExecutionLog(
    proposal_id=proposal_id,
    execution_step="start",
    status="pending",
    result={}
)
```

**Database audit:**
- All proposal executions logged
- Vote records with timestamps
- Staking and delegation history

## Security Best Practices

### Development

1. **Never commit secrets** to version control
2. **Use different credentials** for development/staging/production
3. **Enable security headers** in production
4. **Regular security audits** of code and dependencies
5. **Keep dependencies updated**

### Production

1. **Use HTTPS/TLS** for all communications
2. **Enable firewall rules** to restrict access
3. **Use secret management** for sensitive data
4. **Regular backups** with encryption
5. **Monitor for suspicious activity**
6. **Implement intrusion detection**

### Smart Contracts

1. **Audit contracts** before deployment
2. **Use testnet first** before mainnet deployment
3. **Implement upgrade patterns** for future changes
4. **Monitor contract activity** on-chain
5. **Have emergency procedures** for critical bugs

## Vulnerability Management

### Dependency Scanning

```bash
# Python dependencies
pip-audit

# Smart contract dependencies
forge install OpenZeppelin/openzeppelin-contracts --no-commit
```

### Security Updates

**Regular updates:**
- Python packages: `pip install --upgrade <package>`
- System packages: `apt update && apt upgrade`
- Smart contracts: Re-deploy with fixes

### Incident Response

**Steps:**
1. Identify the vulnerability
2. Assess impact
3. Patch the vulnerability
4. Deploy fix
5. Monitor for exploitation
6. Document the incident

## Compliance

### Data Privacy

- GDPR compliance for user data
- Data retention policies
- Right to be forgotten

### Financial Regulations

- KYC/AML requirements for token operations
- Transaction monitoring
- Suspicious activity reporting

## References

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- Solidity Security: https://docs.soliditylang.org/security/
- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
