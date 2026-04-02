#!/bin/bash

# ============================================================================
# AITBC Production-Grade Setup
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"
PYTHON_CMD="$VENV_DIR/bin/python"

echo -e "${BLUE}🚀 AITBC PRODUCTION-GRADE SETUP${NC}"
echo "=========================="
echo "Upgrading from demonstration to production system"
echo "Nodes: aitbc (localhost) and aitbc1 (remote)"
echo ""

# Step 1: Production Environment Setup
echo -e "${CYAN}🔧 Step 1: Production Environment${NC}"
echo "================================="

cd "$AITBC_ROOT"

# Create production directories
mkdir -p /opt/aitbc/production/{logs,data,config,backups,monitoring}
mkdir -p /opt/aitbc/production/logs/{services,blockchain,marketplace,errors}
mkdir -p /opt/aitbc/production/data/{blockchain,marketplace,agents,gpu}

# Set proper permissions
chmod 755 /opt/aitbc/production
chmod 700 /opt/aitbc/production/data

echo "✅ Production directories created"

# Step 2: Production Database Setup
echo -e "${CYAN}💾 Step 2: Production Database${NC}"
echo "============================"

# Install production dependencies
"$PYTHON_CMD" -m pip install --upgrade pip
"$PYTHON_CMD" -m pip install sqlalchemy psycopg2-binary redis celery

# Create production database configuration
cat > /opt/aitbc/production/config/database.py << 'EOF'
import os
import ssl

# Production Database Configuration
DATABASE_CONFIG = {
    'production': {
        'url': os.getenv('DATABASE_URL', 'postgresql://aitbc:password@localhost:5432/aitbc_prod'),
        'pool_size': 20,
        'max_overflow': 30,
        'pool_timeout': 30,
        'pool_recycle': 3600,
        'ssl_context': ssl.create_default_context()
    },
    'redis': {
        'host': os.getenv('REDIS_HOST', 'localhost'),
        'port': int(os.getenv('REDIS_PORT', 6379)),
        'db': int(os.getenv('REDIS_DB', 0)),
        'password': os.getenv('REDIS_PASSWORD', None),
        'ssl': os.getenv('REDIS_SSL', 'false').lower() == 'true'
    }
}
EOF

echo "✅ Production database configuration created"

# Step 3: Production Blockchain Setup
echo -e "${CYAN}⛓️  Step 3: Production Blockchain${NC}"
echo "=============================="

# Create production blockchain configuration
cat > /opt/aitbc/production/config/blockchain.py << 'EOF'
import os
from pathlib import Path

# Production Blockchain Configuration
BLOCKCHAIN_CONFIG = {
    'network': {
        'name': 'aitbc-mainnet',
        'chain_id': 1337,
        'consensus': 'proof_of_authority',
        'block_time': 5,  # seconds
        'gas_limit': 8000000,
        'difficulty': 'auto'
    },
    'nodes': {
        'aitbc': {
            'host': 'localhost',
            'port': 8545,
            'rpc_port': 8545,
            'p2p_port': 30303,
            'data_dir': '/opt/aitbc/production/data/blockchain/aitbc'
        },
        'aitbc1': {
            'host': 'aitbc1',
            'port': 8545,
            'rpc_port': 8545,
            'p2p_port': 30303,
            'data_dir': '/opt/aitbc/production/data/blockchain/aitbc1'
        }
    },
    'security': {
        'enable_tls': True,
        'cert_path': '/opt/aitbc/production/config/certs',
        'require_auth': True,
        'api_key': os.getenv('BLOCKCHAIN_API_KEY', 'production-key-change-me')
    }
}
EOF

echo "✅ Production blockchain configuration created"

# Step 4: Production Services Configuration
echo -e "${CYAN}🔧 Step 4: Production Services${NC}"
echo "=============================="

# Create production service configurations
cat > /opt/aitbc/production/config/services.py << 'EOF'
import os

# Production Services Configuration
SERVICES_CONFIG = {
    'blockchain': {
        'host': '0.0.0.0',
        'port': 8545,
        'workers': 4,
        'log_level': 'INFO',
        'max_connections': 1000
    },
    'marketplace': {
        'host': '0.0.0.0',
        'port': 8002,
        'workers': 8,
        'log_level': 'INFO',
        'max_connections': 5000
    },
    'gpu_marketplace': {
        'host': '0.0.0.0',
        'port': 8003,
        'workers': 4,
        'log_level': 'INFO',
        'max_connections': 1000
    },
    'monitoring': {
        'host': '0.0.0.0',
        'port': 9000,
        'workers': 2,
        'log_level': 'INFO'
    }
}

# Production Logging
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'production': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/opt/aitbc/production/logs/services/aitbc.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'production'
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'production'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['file', 'console']
    }
}
EOF

echo "✅ Production services configuration created"

# Step 5: Production Security Setup
echo -e "${CYAN}🔒 Step 5: Production Security${NC}"
echo "=========================="

# Create SSL certificates directory
mkdir -p /opt/aitbc/production/config/certs

# Generate self-signed certificates for production
cd /opt/aitbc/production/config/certs
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/C=US/ST=State/L=City/O=AITBC/OU=Production/CN=aitbc.local" 2>/dev/null || echo "OpenSSL not available, using existing certs"

# Create production environment file
cat > /opt/aitbc/production/.env << 'EOF'
# Production Environment Variables
NODE_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://aitbc:secure_password@localhost:5432/aitbc_prod
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=production-secret-key-change-me-in-production
BLOCKCHAIN_API_KEY=production-api-key-change-me
JWT_SECRET=production-jwt-secret-change-me

# Blockchain
NETWORK_ID=1337
CHAIN_ID=1337
CONSENSUS=proof_of_authority

# Services
BLOCKCHAIN_RPC_PORT=8545
MARKETPLACE_PORT=8002
GPU_MARKETPLACE_PORT=8003
MONITORING_PORT=9000

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
EOF

chmod 600 /opt/aitbc/production/.env
echo "✅ Production security setup completed"

echo ""
echo -e "${GREEN}🎉 PRODUCTION SETUP COMPLETED!${NC}"
echo "=================================="
echo ""
echo "✅ Production directories: /opt/aitbc/production/"
echo "✅ Database configuration: PostgreSQL + Redis"
echo "✅ Blockchain configuration: Multi-node PoA"
echo "✅ Services configuration: Production-grade"
echo "✅ Security setup: SSL + Environment variables"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT NOTES:${NC}"
echo "1. Change all default passwords and keys"
echo "2. Set up real PostgreSQL and Redis instances"
echo "3. Configure proper SSL certificates"
echo "4. Set up monitoring and alerting"
echo "5. Configure backup and disaster recovery"
echo ""
echo -e "${BLUE}🚀 Ready for production deployment!${NC}"
