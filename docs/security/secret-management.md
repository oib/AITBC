# Secret Management

This guide covers environment variables, HashiCorp Vault, and AWS Secrets Manager.

## Environment Variables

```bash
# Never commit secrets to git
echo ".env" >> .gitignore

# Use .env files
echo "DATABASE_PASSWORD=secure-password" >> .env
```

## HashiCorp Vault

```bash
# Install Vault
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

# Store secrets
vault kv put secret/aitbc/database password="secure-password"

# Retrieve secrets
vault kv get -field=password secret/aitbc/database
```

## AWS Secrets Manager

```python
import boto3

def get_secret(secret_name):
    """Retrieve secret from AWS Secrets Manager"""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']
```

## See Also

- [API Key Management](api-key-management.md) - Key generation and rotation
- [Database Security](database-security.md) - Database credentials
- [Access Control](access-control.md) - Permissions
