# AITBC Security and Performance Features Guide

## Table of Contents
- [Enhanced Secret Management](#enhanced-secret-management)
- [Blockchain-Specific Validation](#blockchain-specific-validation)
- [Performance Caching Strategies](#performance-caching-strategies)
- [Database Optimization](#database-optimization)
- [Dependency Security Automation](#dependency-security-automation)
- [Security Best Practices](#security-best-practices)

---

## Enhanced Secret Management

### Overview
The enhanced `SecretManager` provides enterprise-grade secret management with automatic expiration, rotation, and encryption key rotation capabilities.

### Features
- **Secret Expiration**: Automatic TTL-based expiration
- **Secret Rotation**: Version tracking for secret updates
- **Encryption Key Rotation**: Master key rotation with re-encryption
- **Metadata Tracking**: Creation, rotation, and expiration timestamps
- **Secure Export**: Metadata export with optional value inclusion

### Basic Usage

```python
from aitbc.crypto.security import SecretManager

# Initialize with default TTL (24 hours)
manager = SecretManager(default_ttl_hours=24)

# Store a secret with custom TTL
manager.set_secret("api_key", "secret_value", ttl_hours=48)

# Retrieve a secret
secret = manager.get_secret("api_key")
if secret:
    print(f"Secret retrieved: {secret}")

# Rotate a secret with version tracking
manager.rotate_secret("api_key", "new_value", ttl_hours=48)

# Get secret metadata
metadata = manager.get_secret_metadata("api_key")
print(f"Version: {metadata['version']}")
print(f"Created: {metadata['created_at']}")
print(f"Rotated: {metadata['rotated_at']}")

# Clean up expired secrets
cleaned = manager.cleanup_expired_secrets()
print(f"Cleaned {cleaned} expired secrets")

# Export metadata (safe for audit)
export = manager.export_secrets(include_values=False)
print(f"Exported {len(export)} secret entries")
```

### Advanced Usage

#### Encryption Key Rotation
```python
from cryptography.fernet import Fernet

# Initialize with current encryption key
manager = SecretManager(encryption_key=current_key)

# Add secrets
manager.set_secret("key1", "value1")
manager.set_secret("key2", "value2")

# Rotate to new encryption key
new_key = Fernet.generate_key().decode('utf-8')
success = manager.rotate_encryption_key(new_key)

if success:
    print("Encryption key rotated successfully")
    # All secrets are re-encrypted with new key
```

#### Secret Expiration Management
```python
# Set short-lived secrets (e.g., session tokens)
manager.set_secret("session_token", "token_value", ttl_hours=1)

# Set long-lived secrets (e.g., API keys)
manager.set_secret("api_key", "key_value", ttl_hours=720)  # 30 days

# Check if secret is expired
metadata = manager.get_secret_metadata("api_key")
if metadata['is_expired']:
    print("Secret has expired, needs rotation")

# List only non-expired secrets
active_keys = manager.list_secrets(include_expired=False)
print(f"Active secrets: {len(active_keys)}")
```

### Configuration Options

```python
manager = SecretManager(
    encryption_key=None,  # Auto-generate if None
    default_ttl_hours=24   # Default time-to-live in hours
)
```

### Security Considerations
- Always use strong encryption keys (Fernet.generate_key())
- Rotate secrets regularly (recommended: monthly for API keys, quarterly for encryption keys)
- Never log or expose secret values
- Use environment variables for encryption keys in production
- Implement proper access controls for secret management

---

## Blockchain-Specific Validation

### Overview
Enhanced `SecurityValidator` provides blockchain-specific input validation to prevent common blockchain security issues.

### Features
- **Private key validation**: Format and length checking
- **Chain ID validation**: Positive integer validation
- **Contract address validation**: Ethereum address format checking
- **Transaction data validation**: Hex string validation
- **Gas parameter validation**: Reasonable bounds checking

### Basic Usage

```python
from aitbc.security_hardening import SecurityValidator

# Validate Ethereum private key
private_key = "0x" + "a" * 64
if SecurityValidator.validate_ethereum_private_key(private_key):
    print("Valid private key format")

# Validate chain ID
chain_id = 1
if SecurityValidator.validate_chain_id(chain_id):
    print("Valid chain ID")

# Validate contract address
contract_address = "0x" + "b" * 40
if SecurityValidator.validate_contract_address(contract_address):
    print("Valid contract address")

# Validate transaction data
tx_data = "0xaabbcc"
if SecurityValidator.validate_transaction_data(tx_data):
    print("Valid transaction data")

# Validate gas parameters
gas_price = 20000000000  # 20 gwei
gas_limit = 21000
if SecurityValidator.validate_gas_price(gas_price):
    if SecurityValidator.validate_gas_limit(gas_limit):
        print("Valid gas parameters")
```

### Validation Functions Reference

| Function | Input | Returns | Purpose |
|----------|-------|---------|---------|
| `validate_ethereum_private_key` | str | bool | Validates Ethereum private key format |
| `validate_chain_id` | str/int | bool | Validates blockchain chain ID |
| `validate_contract_address` | str | bool | Validates smart contract address |
| `validate_block_number` | str/int | bool | Validates block number |
| `validate_gas_price` | str/int | bool | Validates gas price (wei) |
| `validate_gas_limit` | str/int | bool | Validates gas limit (reasonable bounds) |
| `validate_transaction_data` | str | bool | Validates transaction data hex string |
| `validate_amount` | str/int/float | bool | Validates transaction amount (positive) |

### Integration Example

```python
from aitbc.security_hardening import SecurityValidator
from aitbc.exceptions import ValidationError

def validate_transaction_params(tx_data: dict) -> bool:
    """Validate all transaction parameters"""
    errors = []

    if not SecurityValidator.validate_chain_id(tx_data.get('chain_id', 0)):
        errors.append("Invalid chain ID")

    if not SecurityValidator.validate_contract_address(tx_data.get('to_address', '')):
        errors.append("Invalid contract address")

    if not SecurityValidator.validate_gas_price(tx_data.get('gas_price', 0)):
        errors.append("Invalid gas price")

    if not SecurityValidator.validate_gas_limit(tx_data.get('gas_limit', 0)):
        errors.append("Invalid gas limit")

    if not SecurityValidator.validate_amount(tx_data.get('amount', 0)):
        errors.append("Invalid amount")

    if errors:
        raise ValidationError(f"Transaction validation failed: {', '.join(errors)}")

    return True
```

---

## Performance Caching Strategies

### Overview
Enhanced caching system with blockchain-specific optimizations, intelligent invalidation, and performance monitoring.

### Features
- **Blockchain-specific caching**: Different TTL for different data types
- **Automatic cache invalidation**: Event-driven cache consistency
- **Performance monitoring**: Hit/miss rate tracking, operation timing
- **Redis integration**: Distributed caching support
- **Cache decorators**: Easy function-level caching

### Blockchain Cache Usage

```python
from aitbc.caching import BlockchainCache
from aitbc.redis_cache import get_cache

# Initialize blockchain cache
redis_cache = get_cache(redis_url="redis://localhost:6379/0")
blockchain_cache = BlockchainCache(redis_cache=redis_cache)

# Cache account balance (short TTL: 30 seconds)
blockchain_cache.set_account_balance("0x" + "a" * 40, 1, "1000000000000000000")
balance = blockchain_cache.get_account_balance("0x" + "a" * 40, 1)

# Cache block data (long TTL: 1 hour)
blockchain_cache.set_block(12345, 1, block_data)
block = blockchain_cache.get_block(12345, 1)

# Cache transaction (very long TTL: 24 hours)
blockchain_cache.set_transaction("0x" + "a" * 64, 1, tx_data)
tx = blockchain_cache.get_transaction("0x" + "a" * 64, 1)

# Invalidate account balance (e.g., after transaction)
blockchain_cache.invalidate_account("0x" + "a" * 40, 1)
```

### Cache Invalidation

```python
from aitbc.caching import CacheInvalidator

# Initialize invalidator
invalidator = CacheInvalidator(blockchain_cache)

# Handle blockchain events
invalidator.handle_event("new_block", {
    "chain_id": 1,
    "block_number": 12345
})

invalidator.handle_event("new_transaction", {
    "chain_id": 1,
    "from_address": "0x" + "a" * 40,
    "to_address": "0x" + "b" * 40,
    "contract_address": "0x" + "c" * 40
})
```

### Cache Decorators

```python
from aitbc.caching import cached_blockchain

@cached_blockchain(operation="account_balance", ttl=30)
def get_account_balance(address: str, chain_id: int) -> str:
    # Expensive blockchain query
    return blockchain_query(address, chain_id)

# First call: executes function and caches result
balance1 = get_account_balance("0x" + "a" * 40, 1)

# Second call: returns cached result
balance2 = get_account_balance("0x" + "a" * 40, 1)
```

### Performance Monitoring

```python
from aitbc.caching import get_cache_metrics

# Get global cache metrics
metrics = get_cache_metrics()

# Record cache operations
metrics.record_hit("account_balance", 1.5)
metrics.record_miss("block_query", 2.0)

# Get statistics
stats = metrics.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Average duration: {stats['operation_stats']['account_balance']['avg_duration_ms']:.2f}ms")
```

### Cache TTL Defaults

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Account Balance | 30s | Changes frequently |
| Block Data | 1h | Stable after confirmation |
| Transaction | 24h | Immutable |
| Contract State | 1m | Changes frequently |
| Chain State | 10s | Changes very frequently |
| Market Data | 5m | Moderate change rate |

---

## Database Optimization

### Overview
Enhanced database utilities with query monitoring, read replica support, and performance tracking.

### Features
- **Query monitoring**: Performance tracking and slow query detection
- **Read replica management**: Intelligent read/write routing for PostgreSQL
- **Connection pooling**: Optimized connection management
- **Performance metrics**: Query statistics and analysis

### Query Monitoring

```python
from aitbc.database import DatabaseConnection, QueryMonitor
from pathlib import Path

# Initialize with monitoring enabled
db = DatabaseConnection(Path("aitbc.db"), enable_monitoring=True)
db.connect()

# Execute queries (automatically monitored)
db.execute("CREATE TABLE users (id INTEGER, name TEXT)")
db.execute("INSERT INTO users VALUES (1, 'Alice')")

# Get monitoring statistics
stats = db.get_monitoring_stats()
print(f"Total queries: {stats['total_queries']}")
print(f"Average time: {stats['avg_execution_time_ms']:.2f}ms")
print(f"Error rate: {stats['error_rate']:.2%}")

# Get slow queries
slow_queries = db.get_slow_queries(limit=10)
for query in slow_queries:
    print(f"Slow: {query.query} ({query.execution_time_ms:.2f}ms)")

db.close()
```

### Read Replica Management (PostgreSQL)

```python
from aitbc.database import ReadReplicaManager

# Initialize with primary and replicas
manager = ReadReplicaManager(
    primary_url="postgresql://user:pass@primary-host/aitbc",
    replica_urls=[
        "postgresql://user:pass@replica1-host/aitbc",
        "postgresql://user:pass@replica2-host/aitbc"
    ],
    read_weight=70  # 70% of reads to replicas
)

# Get read session (uses replica)
read_session = manager.get_session(read_only=True)
users = read_session.execute("SELECT * FROM users").fetchall()

# Get write session (always uses primary)
write_session = manager.get_session(read_only=False)
write_session.execute("INSERT INTO users VALUES (1, 'Bob')")
write_session.commit()

# Get performance metrics
metrics = manager.get_metrics()
print(f"Replica count: {metrics['replica_count']}")
print(f"Read weight: {metrics['read_weight']}")

manager.close()
```

### Connection Pooling Configuration

```python
from aitbc.database import create_pooled_engine

# SQLite with connection pooling
engine = create_pooled_engine(
    database_url="sqlite:///aitbc.db",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True
)

# PostgreSQL with connection pooling
engine = create_pooled_engine(
    database_url="postgresql://user:pass@localhost/aitbc",
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True
)
```

### Query Monitor Configuration

```python
from aitbc.database import QueryMonitor

# Custom slow query threshold
monitor = QueryMonitor(
    slow_query_threshold_ms=500.0,  # 500ms threshold
    enable_logging=True
)

# Record query manually
monitor.record_query(
    query="SELECT * FROM large_table",
    execution_time_ms=750.0,
    success=True,
    row_count=1000
)

# Get statistics
stats = monitor.get_stats()
print(f"Slow queries: {stats['slow_query_count']}")
```

---

## Dependency Security Automation

### Overview
Automated dependency security scanning using safety, pip-audit, and bandit with CI/CD integration.

### Local Security Scanning

```bash
# Run comprehensive security scan
./scripts/security/dependency-scan.sh

# Or run individual tools
safety check --file requirements.txt
pip-audit -r requirements.txt
bandit -r aitbc/
```

### CI/CD Integration

The security scanning is automatically integrated into:
- **GitHub Actions**: `.github/workflows/dependency-security.yml`
- **Gitea Actions**: `.gitea/workflows/security-scanning.yml`

Triggers:
- On push to main/develop branches
- On pull requests
- Daily scheduled scans (GitHub: 2 AM UTC, Gitea: Weekly)
- Manual workflow dispatch

### Security Report Analysis

```python
import json

# Parse safety report
with open('safety-report.json') as f:
    safety_report = json.load(f)
    for vuln in safety_report:
        print(f"Package: {vuln['package_name']}")
        print(f"Severity: {vuln['severity']}")
        print(f"Fix: {vuln['advisory']}")

# Parse pip-audit report
with open('pip-audit-report.json') as f:
    audit_report = json.load(f)
    for dep in audit_report['dependencies']:
        if dep['vulnerabilities']:
            print(f"Vulnerable: {dep['name']}")
```

### Dependency Update Process

```bash
# Update specific package
pip install --upgrade package_name

# Update all dependencies
pip install --upgrade -r requirements.txt

# Freeze updated requirements
pip freeze > requirements.txt

# Run security scan
./scripts/security/dependency-scan.sh
```

### Security Policy

See `.github/SECURITY.md` for comprehensive security policies including:
- Vulnerability response procedures
- Severity-based timelines
- Security best practices
- Emergency contacts

---

## Security Best Practices

### 1. Secret Management
```python
# ✅ Good: Use environment variables for encryption keys
import os
encryption_key = os.environ.get('ENCRYPTION_KEY')

# ❌ Bad: Hardcode encryption keys
encryption_key = "hardcoded_key_here"
```

### 2. Input Validation
```python
# ✅ Good: Validate all blockchain inputs
from aitbc.security_hardening import SecurityValidator

def process_transaction(tx_data: dict):
    if not SecurityValidator.validate_chain_id(tx_data['chain_id']):
        raise ValidationError("Invalid chain ID")
    # ... process transaction

# ❌ Bad: No validation
def process_transaction(tx_data: dict):
    # ... process transaction without validation
```

### 3. Error Handling
```python
# ✅ Good: Proper exception chaining
try:
    result = risky_operation()
except Exception as e:
    raise DatabaseError("Operation failed") from e

# ❌ Bad: Lose original exception
try:
    result = risky_operation()
except Exception:
    raise DatabaseError("Operation failed")
```

### 4. Caching Strategy
```python
# ✅ Good: Cache with appropriate TTL and invalidation
blockchain_cache.set_account_balance(address, chain_id, balance)
# Invalidate after transaction
blockchain_cache.invalidate_account(address, chain_id)

# ❌ Bad: Cache without invalidation
cache.set("balance", balance, ttl=86400)  # Too long, stale data
```

### 5. Database Security
```python
# ✅ Good: Use parameterized queries
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))

# ❌ Bad: String concatenation (SQL injection risk)
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
```

### 6. Dependency Management
```python
# ✅ Good: Regular security scans
./scripts/security/dependency-scan.sh

# ✅ Good: Pin versions in requirements.txt
requests==2.31.0
cryptography==41.0.7

# ❌ Bad: Unpinned versions
requests>=2.28.0
cryptography
```

### 7. Monitoring
```python
# ✅ Good: Enable monitoring in production
db = DatabaseConnection(db_path, enable_monitoring=True)

# ✅ Good: Regular metrics review
stats = db.get_monitoring_stats()
if stats['error_rate'] > 0.05:  # 5% error rate threshold
    alert_team("High database error rate")

# ❌ Bad: No monitoring
db = DatabaseConnection(db_path, enable_monitoring=False)
```

### 8. Cache Monitoring
```python
# ✅ Good: Monitor cache performance
metrics = get_cache_metrics()
stats = metrics.get_stats()
if stats['hit_rate'] < 0.7:  # 70% hit rate threshold
    optimize_cache_strategy()

# ❌ Bad: No cache monitoring
# Just caching without performance analysis
```

---

## Quick Reference

### Security Features
- **SecretManager**: Enhanced secret management with rotation
- **SecurityValidator**: Blockchain-specific validation
- **DependencySecurity**: Automated vulnerability scanning

### Performance Features
- **BlockchainCache**: Specialized blockchain caching
- **CacheInvalidator**: Event-driven cache invalidation
- **QueryMonitor**: Database query performance tracking
- **ReadReplicaManager**: PostgreSQL read replica routing

### Configuration Files
- `.github/SECURITY.md` - Security policy and procedures
- `.github/workflows/dependency-security.yml` - GitHub security automation
- `.gitea/workflows/security-scanning.yml` - Gitea security automation
- `scripts/security/dependency-scan.sh` - Local security scanning script

### Testing
- `tests/test_security_enhancements.py` - Security feature tests
- `tests/test_performance_caching.py` - Caching feature tests
- `tests/test_database_optimization.py` - Database optimization tests
- `tests/test_dependency_security.py` - Dependency security tests

---

## Support

For security issues or questions about these features:
- **Security Policy**: See `.github/SECURITY.md`
- **Security Issues**: security@aitbc.io
- **Documentation**: See inline docstrings and type hints
- **Examples**: See test files for usage examples

---

**Last Updated**: 2025-01-04
**Version**: 2.0
**Maintained By**: AITBC Development Team
