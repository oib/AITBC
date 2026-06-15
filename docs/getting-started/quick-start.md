# AITBC Quick Start Guide - New Security & Performance Features

This guide helps you quickly get started with the new security and performance features in AITBC.

## 🚀 5-Minute Quick Start

### 1. Secret Management

```python
from aitbc.crypto.security import SecretManager

# Initialize
manager = SecretManager(default_ttl_hours=24)

# Store and retrieve
manager.set_secret("api_key", "your_secret_here")
secret = manager.get_secret("api_key")

# Rotate secrets
manager.rotate_secret("api_key", "new_secret_value")
```

### 2. Blockchain Validation

```python
from aitbc.security_hardening import SecurityValidator

# Validate inputs
if SecurityValidator.validate_ethereum_private_key("0x" + "a" * 64):
    print("Valid private key")

if SecurityValidator.validate_chain_id(1):
    print("Valid chain ID")
```

### 3. Performance Caching

```python
from aitbc.caching import BlockchainCache, cached_blockchain

# Method 1: Direct cache usage
cache = BlockchainCache()
cache.set_account_balance("0x" + "a" * 40, 1, "1000000000000000000")
balance = cache.get_account_balance("0x" + "a" * 40, 1)

# Method 2: Decorator
@cached_blockchain(operation="account_balance", ttl=30)
def get_balance(address: str, chain_id: int) -> str:
    return blockchain_query(address, chain_id)
```

### 4. Database Monitoring

```python
from aitbc.database import DatabaseConnection
from pathlib import Path

# Enable monitoring
db = DatabaseConnection(Path("aitbc.db"), enable_monitoring=True)
db.connect()

# Execute queries (automatically monitored)
db.execute("CREATE TABLE test (id INTEGER)")

# Check performance
stats = db.get_monitoring_stats()
print(f"Queries: {stats['total_queries']}, Avg time: {stats['avg_execution_time_ms']:.2f}ms")
```

### 5. Security Scanning

```bash
# Run local security scan
./scripts/security/dependency-scan.sh

# Or individual tools
safety check --file requirements.txt
pip-audit -r requirements.txt
```

## 📋 Feature Checklist

Use this checklist to ensure you're using the new features effectively:

### Security Features
- [ ] Using enhanced `SecretManager` for sensitive data
- [ ] Validating blockchain inputs with `SecurityValidator`
- [ ] Running local security scans before commits
- [ ] Reviewing CI/CD security reports
- [ ] Following security best practices

### Performance Features
- [ ] Using `BlockchainCache` for blockchain data
- [ ] Implementing cache invalidation for state changes
- [ ] Enabling database query monitoring
- [ ] Configuring appropriate cache TTL values
- [ ] Monitoring cache hit rates

## 🎯 Common Use Cases

### Use Case 1: Secure API Key Storage

```python
from aitbc.crypto.security import SecretManager

# Initialize with environment variable
import os
manager = SecretManager(
    encryption_key=os.environ['ENCRYPTION_KEY'],
    default_ttl_hours=720  # 30 days
)

# Store API key
manager.set_secret("exchange_api_key", os.environ['EXCHANGE_API_KEY'])

# Use in application
api_key = manager.get_secret("exchange_api_key")
if not api_key:
    raise ValueError("API key expired or not found")
```

### Use Case 2: Blockchain Transaction Validation

```python
from aitbc.security_hardening import SecurityValidator
from aitbc.exceptions import ValidationError

def validate_transaction(tx: dict) -> bool:
    """Validate all transaction parameters"""
    validations = [
        ('chain_id', SecurityValidator.validate_chain_id),
        ('to_address', SecurityValidator.validate_contract_address),
        ('gas_price', SecurityValidator.validate_gas_price),
        ('gas_limit', SecurityValidator.validate_gas_limit),
        ('amount', SecurityValidator.validate_amount),
    ]

    for field, validator in validations:
        if not validator(tx.get(field, 0)):
            raise ValidationError(f"Invalid {field}")

    return True
```

### Use Case 3: High-Performance Blockchain Queries

```python
from aitbc.caching import BlockchainCache, CacheInvalidator

# Setup
cache = BlockchainCache()
invalidator = CacheInvalidator(cache)

# Query with caching
def get_account_balance(address: str, chain_id: int) -> str:
    # Try cache first
    balance = cache.get_account_balance(address, chain_id)
    if balance:
        return balance

    # Query blockchain
    balance = blockchain_rpc.get_balance(address, chain_id)

    # Cache result
    cache.set_account_balance(address, chain_id, balance)
    return balance

# Invalidate on transaction
def on_transaction(tx):
    invalidator.handle_event("new_transaction", {
        'chain_id': tx.chain_id,
        'from_address': tx.from_address,
        'to_address': tx.to_address
    })
```

### Use Case 4: Database Performance Optimization

```python
from aitbc.database import DatabaseConnection, QueryMonitor
from pathlib import Path

# Setup with monitoring
db = DatabaseConnection(Path("aitbc.db"), enable_monitoring=True)
db.connect()

# Monitor slow queries
def check_performance():
    stats = db.get_monitoring_stats()
    slow_queries = db.get_slow_queries(limit=5)

    if stats['avg_execution_time_ms'] > 100:
        print("⚠️  High average query time")

    for query in slow_queries:
        print(f"⚠️  Slow query: {query.query[:50]}... ({query.execution_time_ms:.2f}ms)")

# Run periodically
check_performance()
db.close()
```

## 🔧 Configuration Examples

### Production Configuration

```python
# config.py
import os
from aitbc.crypto.security import SecretManager
from aitbc.caching import BlockchainCache
from aitbc.redis_cache import get_cache
from aitbc.database import ReadReplicaManager

# Secret Manager
SECRET_MANAGER = SecretManager(
    encryption_key=os.environ['ENCRYPTION_KEY'],
    default_ttl_hours=24
)

# Blockchain Cache
REDIS_CACHE = get_cache(
    redis_url=os.environ['REDIS_URL'],
    max_connections=20,
    default_ttl=3600
)
BLOCKCHAIN_CACHE = BlockchainCache(redis_cache=REDIS_CACHE)

# Database (PostgreSQL with read replicas)
DB_MANAGER = ReadReplicaManager(
    primary_url=os.environ['DATABASE_PRIMARY_URL'],
    replica_urls=[
        os.environ['DATABASE_REPLICA1_URL'],
        os.environ['DATABASE_REPLICA2_URL']
    ],
    read_weight=80
)
```

### Development Configuration

```python
# dev_config.py
from aitbc.crypto.security import SecretManager
from aitbc.caching import BlockchainCache
from aitbc.database import DatabaseConnection
from pathlib import Path

# Secret Manager (auto-generated key)
SECRET_MANAGER = SecretManager(default_ttl_hours=1)

# Blockchain Cache (no Redis, in-memory only)
BLOCKCHAIN_CACHE = BlockchainCache(redis_cache=None)

# Database (SQLite with monitoring)
DB = DatabaseConnection(Path("dev_aitbc.db"), enable_monitoring=True)
```

## 📊 Monitoring Dashboard

### Key Metrics to Track

```python
from aitbc.caching import get_cache_metrics
from aitbc.database import DatabaseConnection

def get_performance_metrics():
    """Get all performance metrics"""
    metrics = {
        'cache': get_cache_metrics().get_stats(),
        'database': DatabaseConnection.get_monitoring_stats()
    }
    return metrics

def health_check():
    """Quick health check"""
    metrics = get_performance_metrics()

    health = {
        'cache_hit_rate': metrics['cache']['hit_rate'] > 0.7,
        'db_error_rate': metrics['database']['error_rate'] < 0.05,
        'avg_query_time': metrics['database']['avg_execution_time_ms'] < 100
    }

    return all(health.values()), health
```

## 🐛 Troubleshooting

### Common Issues

**Issue**: Secret retrieval returns None
```python
# Solution: Check if secret expired
metadata = manager.get_secret_metadata("api_key")
if metadata['is_expired']:
    manager.rotate_secret("api_key", "new_value")
```

**Issue**: Cache hit rate is low
```python
# Solution: Check TTL values and invalidation
stats = cache.get_cache_stats()
print(f"TTL settings: {stats['default_ttl']}")
# Adjust TTL based on data volatility
```

**Issue**: Database queries are slow
```python
# Solution: Check slow queries and optimize
slow_queries = db.get_slow_queries(limit=10)
for query in slow_queries:
    print(f"Optimize: {query.query}")
    # Add indexes or rewrite queries
```

**Issue**: Security scan finds vulnerabilities
```python
# Solution: Update dependencies
pip install --upgrade vulnerable_package
pip freeze > requirements.txt
./scripts/security/dependency-scan.sh
```

## 📚 Next Steps

1. **Read the full guide**: `docs/SECURITY_AND_PERFORMANCE.md`
2. **Review security policy**: `.github/SECURITY.md`
3. **Check test files**: See `tests/test_*.py` for examples
4. **Run security scan**: `./scripts/security/dependency-scan.sh`
5. **Enable monitoring**: Set up monitoring in your application

## 🆘 Getting Help

- **Documentation**: See inline docstrings and type hints
- **Examples**: Check test files for comprehensive examples
- **Security Issues**: security@aitbc.io
- **General Issues**: Create GitHub issue

---

**Version**: 1.0
**Last Updated**: 2025-01-04
