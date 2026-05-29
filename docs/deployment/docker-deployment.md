# Docker Containerized Deployment

This guide covers deploying AITBC using Docker and Docker Compose.

## Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  blockchain:
    build: ./apps/blockchain_node
    ports:
      - "8006:8006"
    volumes:
      - blockchain-data:/data
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/aitbc

  coordinator:
    build: ./apps/coordinator-api
    ports:
      - "8011:8011"
    depends_on:
      - blockchain
      - postgres
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/aitbc

  marketplace:
    build: ./apps/marketplace_service
    ports:
      - "8102:8102"
    depends_on:
      - postgres
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/aitbc

  postgres:
    image: postgres:15
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=aitbc
      - POSTGRES_USER=aitbc
      - POSTGRES_PASSWORD=secure-password

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  blockchain-data:
  postgres-data:
```

## Build and Run

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

## See Also

- [Prerequisites](prerequisites.md) - System requirements
- [Cloud Deployment](cloud-deployment.md) - Cloud-specific deployment
- [Configuration](configuration.md) - Environment configuration
