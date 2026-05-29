# Single-Server Production Deployment

This guide covers deploying AITBC on a single server for production use.

## Installation Steps

### 1. Prepare Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Create user
sudo useradd -m -s /bin/bash aitbc
sudo usermod -aG docker aitbc
```

### 2. Install Dependencies

```bash
# Install system dependencies
sudo apt install -y \
    build-essential \
    python3-dev \
    python3-venv \
    git \
    curl \
    nginx \
    postgresql \
    redis-server \
    docker.io \
    docker-compose
```

### 3. Deploy Application

```bash
# Clone repository
sudo -u aitbc git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# Setup virtual environment
sudo -u aitbc python3 -m venv /opt/aitbc/venv
sudo -u aitbc /opt/aitbc/venv/bin/pip install -r requirements.txt

# Setup database
sudo -u postgres psql -c "CREATE DATABASE aitbc;"
sudo -u postgres psql -c "CREATE USER aitbc WITH PASSWORD 'secure-password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aitbc TO aitbc;"
```

### 4. Configure Systemd Services

```bash
# Setup services
sudo ./scripts/setup.sh

# Enable services
sudo systemctl enable aitbc-blockchain
sudo systemctl enable aitbc-coordinator-api
sudo systemctl enable aitbc-marketplace

# Start services
sudo systemctl start aitbc-blockchain
sudo systemctl start aitbc-coordinator-api
sudo systemctl start aitbc-marketplace
```

### 5. Configure Nginx

```nginx
# /etc/nginx/sites-available/aitbc
upstream coordinator {
    server 127.0.0.1:8011;
}

upstream blockchain {
    server 127.0.0.1:8006;
}

upstream marketplace {
    server 127.0.0.1:8102;
}

server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://coordinator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /blockchain/ {
        proxy_pass http://blockchain;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /marketplace/ {
        proxy_pass http://marketplace;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## See Also

- [Prerequisites](prerequisites.md) - System requirements
- [SSL/TLS Setup](ssl-tls-setup.md) - SSL configuration
- [Configuration](configuration.md) - Environment configuration
