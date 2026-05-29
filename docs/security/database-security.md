# Database Security

This guide covers PostgreSQL security, connection security, and backup encryption.

## PostgreSQL Security

```sql
-- Create dedicated user
CREATE USER aitbc WITH PASSWORD 'secure-password';

-- Grant minimum privileges
GRANT CONNECT ON DATABASE aitbc TO aitbc;
GRANT USAGE ON SCHEMA public TO aitbc;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aitbc;

-- Enable SSL
ALTER SYSTEM SET ssl = 'on';
ALTER SYSTEM SET ssl_cert_file = '/etc/ssl/certs/postgresql.crt';
ALTER SYSTEM SET ssl_key_file = '/etc/ssl/private/postgresql.key';
```

## Connection Security

```python
# Use SSL for database connections
DATABASE_URL = "postgresql://user:pass@localhost:5432/aitbc?sslmode=require"

# Connection pooling with SSL
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    ssl={'sslmode': 'require'}
)
```

## Backup Encryption

```bash
# Encrypt database backups
pg_dump aitbc | gpg --encrypt --recipient admin@aitbc.dev > backup.sql.gpg

# Decrypt backup
gpg --decrypt backup.sql.gpg > backup.sql
```

## See Also

- [Secret Management](secret-management.md) - Credential storage
- [Network Security](network-security.md) - Network segmentation
- [Access Control](access-control.md) - User permissions
