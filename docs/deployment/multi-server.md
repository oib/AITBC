# Multi-Server Deployment

This guide covers deploying AITBC across multiple servers for high availability and scalability.

## Architecture

```
                    Load Balancer
                         |
        +----------------+----------------+
        |                |                |
   Blockchain Node   Coordinator API   Marketplace
        |                |                |
        +----------------+----------------+
                         |
                   PostgreSQL Cluster
                         |
                   Redis Cluster
```

## Node Types

1. **Blockchain Node**
   - Runs blockchain consensus
   - Maintains ledger
   - Requires public IP

2. **Coordinator API**
   - Job submission and management
   - Payment processing
   - API gateway

3. **Marketplace Service**
   - GPU offer management
   - Matching engine
   - Price discovery

4. **Database Node**
   - PostgreSQL cluster
   - Redis cache
   - Data persistence

## Setup Steps

### 1. Configure Network

```bash
# On each node, configure network
sudo apt install -y etcd
sudo systemctl enable etcd
sudo systemctl start etcd
```

### 2. Deploy Blockchain Node

```bash
# On blockchain node
sudo apt install -y nvidia-cuda-toolkit
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
./scripts/setup/blockchain.sh
```

### 3. Deploy Coordinator API

```bash
# On coordinator node
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
./scripts/setup/coordinator.sh
```

### 4. Deploy Marketplace Service

```bash
# On marketplace node
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc
./scripts/setup/marketplace.sh
```

### 5. Configure Database Cluster

```bash
# On database node
sudo apt install -y postgresql redis-server
sudo -u postgres psql -c "CREATE DATABASE aitbc;"
```

## See Also

- [Prerequisites](prerequisites.md) - System requirements
- [Cloud Deployment](cloud-deployment.md) - Cloud-specific deployment
- [Configuration](configuration.md) - Environment configuration
