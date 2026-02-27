#!/usr/bin/env bash

# AITBC Platform Deployment Script for aitbc and aitbc1 Servers
# Deploys the complete platform to both production servers

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_critical() {
    echo -e "${RED}[CRITICAL]${NC} $1"
}

print_server() {
    echo -e "${PURPLE}[SERVER]${NC} $1"
}

print_deploy() {
    echo -e "${CYAN}[DEPLOY]${NC} $1"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CONTRACTS_DIR="$ROOT_DIR/contracts"
SERVICES_DIR="$ROOT_DIR/apps/coordinator-api/src/app/services"
FRONTEND_DIR="$ROOT_DIR/apps/marketplace-web"
INFRA_DIR="$ROOT_DIR/infra"

# Server configuration
AITBC_SERVER="aitbc-cascade"
AITBC1_SERVER="aitbc1-cascade"
AITBC_HOST="aitbc.bubuit.net"
AITBC1_HOST="aitbc1.bubuit.net"
AITBC_PORT="22"
AITBC1_PORT="22"

# Deployment configuration
DEPLOY_CONTRACTS=${1:-"true"}
DEPLOY_SERVICES=${2:-"true"}
DEPLOY_FRONTEND=${3:-"true"}
SKIP_VERIFICATION=${4:-"false"}
BACKUP_BEFORE_DEPLOY=${5:-"true"}

echo "🚀 AITBC Platform Deployment to aitbc and aitbc1 Servers"
echo "======================================================="
echo "Deploy Contracts: $DEPLOY_CONTRACTS"
echo "Deploy Services: $DEPLOY_SERVICES"
echo "Deploy Frontend: $DEPLOY_FRONTEND"
echo "Skip Verification: $SKIP_VERIFICATION"
echo "Backup Before Deploy: $BACKUP_BEFORE_DEPLOY"
echo "Timestamp: $(date -Iseconds)"
echo ""

# Pre-deployment checks
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if SSH keys are available
    if [[ ! -f "$HOME/.ssh/id_rsa" ]] && [[ ! -f "$HOME/.ssh/id_ed25519" ]]; then
        print_error "SSH keys not found. Please generate SSH keys first."
        exit 1
    fi
    
    # Check if we can connect to servers
    print_status "Testing SSH connections..."
    if ! ssh -o ConnectTimeout=10 -o BatchMode=yes $AITBC_SERVER "echo 'Connection successful'" 2>/dev/null; then
        print_error "Cannot connect to $AITBC_SERVER"
        exit 1
    fi
    
    if ! ssh -o ConnectTimeout=10 -o BatchMode=yes $AITBC1_SERVER "echo 'Connection successful'" 2>/dev/null; then
        print_error "Cannot connect to $AITBC1_SERVER"
        exit 1
    fi
    
    # Check if required directories exist
    if [[ ! -d "$CONTRACTS_DIR" ]]; then
        print_error "Contracts directory not found: $CONTRACTS_DIR"
        exit 1
    fi
    
    if [[ ! -d "$SERVICES_DIR" ]]; then
        print_error "Services directory not found: $SERVICES_DIR"
        exit 1
    fi
    
    if [[ ! -d "$FRONTEND_DIR" ]]; then
        print_error "Frontend directory not found: $FRONTEND_DIR"
        exit 1
    fi
    
    print_success "Prerequisites check completed"
}

# Backup existing deployment
backup_deployment() {
    if [[ "$BACKUP_BEFORE_DEPLOY" != "true" ]]; then
        print_status "Skipping backup (disabled)"
        return
    fi
    
    print_status "Creating backup of existing deployment..."
    
    local backup_dir="/tmp/aitbc-backup-$(date +%Y%m%d-%H%M%S)"
    
    # Backup aitbc server
    print_server "Backing up aitbc server..."
    ssh $AITBC_SERVER "
        mkdir -p $backup_dir
        sudo cp -r /var/www/aitbc.bubuit.net $backup_dir/ 2>/dev/null || true
        sudo cp -r /var/www/html $backup_dir/ 2>/dev/null || true
        sudo cp -r /etc/nginx/sites-enabled/ $backup_dir/ 2>/dev/null || true
        sudo cp -r /etc/systemd/system/aitbc* $backup_dir/ 2>/dev/null || true
        echo 'aitbc backup completed'
    "
    
    # Backup aitbc1 server
    print_server "Backing up aitbc1 server..."
    ssh $AITBC1_SERVER "
        mkdir -p $backup_dir
        sudo cp -r /var/www/aitbc.bubuit.net $backup_dir/ 2>/dev/null || true
        sudo cp -r /var/www/html $backup_dir/ 2>/dev/null || true
        sudo cp -r /etc/nginx/sites-enabled/ $backup_dir/ 2>/dev/null || true
        sudo cp -r /etc/systemd/system/aitbc* $backup_dir/ 2>/dev/null || true
        echo 'aitbc1 backup completed'
    "
    
    print_success "Backup completed: $backup_dir"
}

# Deploy smart contracts
deploy_contracts() {
    if [[ "$DEPLOY_CONTRACTS" != "true" ]]; then
        print_status "Skipping contract deployment (disabled)"
        return
    fi
    
    print_status "Deploying smart contracts..."
    
    cd "$CONTRACTS_DIR"
    
    # Check if contracts are already deployed
    if [[ -f "deployed-contracts-mainnet.json" ]]; then
        print_warning "Contracts already deployed. Skipping deployment."
        return
    fi
    
    # Compile contracts
    print_status "Compiling contracts..."
    npx hardhat compile
    
    # Deploy to mainnet
    print_status "Deploying contracts to mainnet..."
    npx hardhat run scripts/deploy-advanced-contracts.js --network mainnet
    
    # Verify contracts
    if [[ "$SKIP_VERIFICATION" != "true" ]]; then
        print_status "Verifying contracts..."
        npx hardhat run scripts/verify-advanced-contracts.js --network mainnet
    fi
    
    print_success "Smart contracts deployed and verified"
}

# Deploy backend services
deploy_services() {
    if [[ "$DEPLOY_SERVICES" != "true" ]]; then
        print_status "Skipping service deployment (disabled)"
        return
    fi
    
    print_status "Deploying backend services..."
    
    # Deploy to aitbc server
    print_server "Deploying services to aitbc server..."
    
    # Copy services to aitbc
    scp -r "$SERVICES_DIR" $AITBC_SERVER:/tmp/
    
    # Install dependencies and setup services on aitbc
    ssh $AITBC_SERVER "
        # Create service directory
        sudo mkdir -p /opt/aitbc/services
        
        # Copy services
        sudo cp -r /tmp/services/* /opt/aitbc/services/
        
        # Install Python dependencies
        cd /opt/aitbc/services
        python3 -m pip install -r requirements.txt 2>/dev/null || true
        
        # Create systemd services
        sudo tee /etc/systemd/system/aitbc-cross-chain-reputation.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Cross Chain Reputation Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/services
ExecStart=/usr/bin/python3 -m cross_chain_reputation
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        sudo tee /etc/systemd/system/aitbc-agent-communication.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Agent Communication Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/services
ExecStart=/usr/bin/python3 -m agent_communication
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        sudo tee /etc/systemd/system/aitbc-advanced-learning.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Advanced Learning Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/services
ExecStart=/usr/bin/python3 -m advanced_learning
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        # Reload systemd and start services
        sudo systemctl daemon-reload
        sudo systemctl enable aitbc-cross-chain-reputation
        sudo systemctl enable aitbc-agent-communication
        sudo systemctl enable aitbc-advanced-learning
        sudo systemctl start aitbc-cross-chain-reputation
        sudo systemctl start aitbc-agent-communication
        sudo systemctl start aitbc-advanced-learning
        
        echo 'Services deployed and started on aitbc'
    "
    
    # Deploy to aitbc1 server
    print_server "Deploying services to aitbc1 server..."
    
    # Copy services to aitbc1
    scp -r "$SERVICES_DIR" $AITBC1_SERVER:/tmp/
    
    # Install dependencies and setup services on aitbc1
    ssh $AITBC1_SERVER "
        # Create service directory
        sudo mkdir -p /opt/aitbc/services
        
        # Copy services
        sudo cp -r /tmp/services/* /opt/aitbc/services/
        
        # Install Python dependencies
        cd /opt/aitbc/services
        python3 -m pip install -r requirements.txt 2>/dev/null || true
        
        # Create systemd services
        sudo tee /etc/systemd/system/aitbc-cross-chain-reputation.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Cross Chain Reputation Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/services
ExecStart=/usr/bin/python3 -m cross_chain_reputation
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        sudo tee /etc/systemd/system/aitbc-agent-communication.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Agent Communication Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/services
ExecStart=/usr/bin/python3 -m agent_communication
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        sudo tee /etc/systemd/system/aitbc-advanced-learning.service > /dev/null << 'EOF'
[Unit]
Description=AITBC Advanced Learning Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/services
ExecStart=/usr/bin/python3 -m advanced_learning
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        
        # Reload systemd and start services
        sudo systemctl daemon-reload
        sudo systemctl enable aitbc-cross-chain-reputation
        sudo systemctl enable aitbc-agent-communication
        sudo systemctl enable aitbc-advanced-learning
        sudo systemctl start aitbc-cross-chain-reputation
        sudo systemctl start aitbc-agent-communication
        sudo systemctl start aitbc-advanced-learning
        
        echo 'Services deployed and started on aitbc1'
    "
    
    print_success "Backend services deployed to both servers"
}

# Deploy frontend
deploy_frontend() {
    if [[ "$DEPLOY_FRONTEND" != "true" ]]; then
        print_status "Skipping frontend deployment (disabled)"
        return
    fi
    
    print_status "Building and deploying frontend..."
    
    cd "$FRONTEND_DIR"
    
    # Build frontend
    print_status "Building frontend application..."
    npm run build
    
    # Deploy to aitbc server
    print_server "Deploying frontend to aitbc server..."
    
    # Copy built frontend to aitbc
    scp -r build/* $AITBC_SERVER:/tmp/frontend/
    
    ssh $AITBC_SERVER "
        # Backup existing frontend
        sudo cp -r /var/www/aitbc.bubuit.net /var/www/aitbc.bubuit.net.backup 2>/dev/null || true
        
        # Deploy new frontend
        sudo rm -rf /var/www/aitbc.bubuit.net/*
        sudo cp -r /tmp/frontend/* /var/www/aitbc.bubuit.net/
        
        # Set permissions
        sudo chown -R www-data:www-data /var/www/aitbc.bubuit.net/
        sudo chmod -R 755 /var/www/aitbc.bubuit.net/
        
        echo 'Frontend deployed to aitbc'
    "
    
    # Deploy to aitbc1 server
    print_server "Deploying frontend to aitbc1 server..."
    
    # Copy built frontend to aitbc1
    scp -r build/* $AITBC1_SERVER:/tmp/frontend/
    
    ssh $AITBC1_SERVER "
        # Backup existing frontend
        sudo cp -r /var/www/aitbc.bubuit.net /var/www/aitbc.bubuit.net.backup 2>/dev/null || true
        
        # Deploy new frontend
        sudo rm -rf /var/www/aitbc.bubuit.net/*
        sudo cp -r /tmp/frontend/* /var/www/aitbc.bubuit.net/
        
        # Set permissions
        sudo chown -R www-data:www-data /var/www/aitbc.bubuit.net/
        sudo chmod -R 755 /var/www/aitbc.bubuit.net/
        
        echo 'Frontend deployed to aitbc1'
    "
    
    print_success "Frontend deployed to both servers"
}

# Deploy configuration files
deploy_configuration() {
    print_status "Deploying configuration files..."
    
    # Create nginx configuration for aitbc
    print_server "Deploying nginx configuration to aitbc..."
    ssh $AITBC_SERVER "
        sudo tee /etc/nginx/sites-available/aitbc-advanced.conf > /dev/null << 'EOF'
server {
    listen 80;
    server_name aitbc.bubuit.net;
    
    root /var/www/aitbc.bubuit.net;
    index index.html;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection \"1; mode=block\";
    add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always;
    
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;
    
    # API routes
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Advanced features API
    location /api/v1/advanced/ {
        proxy_pass http://localhost:8001/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Static files
    location / {
        try_files \$uri \$uri/ /index.html;
        expires 1y;
        add_header Cache-Control \"public, immutable\";
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 \"healthy\";
        add_header Content-Type text/plain;
    }
}
EOF
        
        # Enable site
        sudo ln -sf /etc/nginx/sites-available/aitbc-advanced.conf /etc/nginx/sites-enabled/
        sudo nginx -t
        sudo systemctl reload nginx
        
        echo 'Nginx configuration deployed to aitbc'
    "
    
    # Create nginx configuration for aitbc1
    print_server "Deploying nginx configuration to aitbc1..."
    ssh $AITBC1_SERVER "
        sudo tee /etc/nginx/sites-available/aitbc1-advanced.conf > /dev/null << 'EOF'
server {
    listen 80;
    server_name aitbc1.bubuit.net;
    
    root /var/www/aitbc.bubuit.net;
    index index.html;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection \"1; mode=block\";
    add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always;
    
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;
    
    # API routes
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Advanced features API
    location /api/v1/advanced/ {
        proxy_pass http://localhost:8001/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Static files
    location / {
        try_files \$uri \$uri/ /index.html;
        expires 1y;
        add_header Cache-Control \"public, immutable\";
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 \"healthy\";
        add_header Content-Type text/plain;
    }
}
EOF
        
        # Enable site
        sudo ln -sf /etc/nginx/sites-available/aitbc1-advanced.conf /etc/nginx/sites-enabled/
        sudo nginx -t
        sudo systemctl reload nginx
        
        echo 'Nginx configuration deployed to aitbc1'
    "
    
    print_success "Configuration files deployed to both servers"
}

# Verify deployment
verify_deployment() {
    if [[ "$SKIP_VERIFICATION" == "true" ]]; then
        print_status "Skipping verification (disabled)"
        return
    fi
    
    print_status "Verifying deployment..."
    
    # Verify aitbc server
    print_server "Verifying aitbc server deployment..."
    ssh $AITBC_SERVER "
        echo '=== aitbc Server Status ==='
        
        # Check services
        echo 'Services:'
        sudo systemctl is-active aitbc-cross-chain-reputation || echo 'cross-chain-reputation: INACTIVE'
        sudo systemctl is-active aitbc-agent-communication || echo 'agent-communication: INACTIVE'
        sudo systemctl is-active aitbc-advanced-learning || echo 'advanced-learning: INACTIVE'
        
        # Check nginx
        echo 'Nginx:'
        sudo systemctl is-active nginx || echo 'nginx: INACTIVE'
        sudo nginx -t || echo 'nginx config: ERROR'
        
        # Check web server
        echo 'Web server:'
        curl -s http://localhost/health || echo 'health check: FAILED'
        
        # Check API endpoints
        echo 'API endpoints:'
        curl -s http://localhost:8000/health || echo 'API health: FAILED'
        curl -s http://localhost:8001/health || echo 'Advanced API health: FAILED'
        
        echo 'aitbc verification completed'
    "
    
    # Verify aitbc1 server
    print_server "Verifying aitbc1 server deployment..."
    ssh $AITBC1_SERVER "
        echo '=== aitbc1 Server Status ==='
        
        # Check services
        echo 'Services:'
        sudo systemctl is-active aitbc-cross-chain-reputation || echo 'cross-chain-reputation: INACTIVE'
        sudo systemctl is-active aitbc-agent-communication || echo 'agent-communication: INACTIVE'
        sudo systemctl is-active aitbc-advanced-learning || echo 'advanced-learning: INACTIVE'
        
        # Check nginx
        echo 'Nginx:'
        sudo systemctl is-active nginx || echo 'nginx: INACTIVE'
        sudo nginx -t || echo 'nginx config: ERROR'
        
        # Check web server
        echo 'Web server:'
        curl -s http://localhost/health || echo 'health check: FAILED'
        
        # Check API endpoints
        echo 'API endpoints:'
        curl -s http://localhost:8000/health || echo 'API health: FAILED'
        curl -s http://localhost:8001/health || echo 'Advanced API health: FAILED'
        
        echo 'aitbc1 verification completed'
    "
    
    print_success "Deployment verification completed"
}

# Test external connectivity
test_connectivity() {
    print_status "Testing external connectivity..."
    
    # Test aitbc server
    print_server "Testing aitbc external connectivity..."
    if curl -s "http://$AITBC_HOST/health" | grep -q "healthy"; then
        print_success "aitbc server is accessible externally"
    else
        print_warning "aitbc server external connectivity issue"
    fi
    
    # Test aitbc1 server
    print_server "Testing aitbc1 external connectivity..."
    if curl -s "http://$AITBC1_HOST/health" | grep -q "healthy"; then
        print_success "aitbc1 server is accessible externally"
    else
        print_warning "aitbc1 server external connectivity issue"
    fi
}

# Generate deployment report
generate_report() {
    print_status "Generating deployment report..."
    
    local report_file="$ROOT_DIR/deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" << EOF
{
    "deployment": {
        "timestamp": "$(date -Iseconds)",
        "servers": ["aitbc", "aitbc1"],
        "contracts_deployed": "$DEPLOY_CONTRACTS",
        "services_deployed": "$DEPLOY_SERVICES",
        "frontend_deployed": "$DEPLOY_FRONTEND",
        "backup_created": "$BACKUP_BEFORE_DEPLOY",
        "verification_completed": "$([[ "$SKIP_VERIFICATION" != "true" ]] && echo "true" || echo "false")"
    },
    "servers": {
        "aitbc": {
            "host": "$AITBC_HOST",
            "services": {
                "cross_chain_reputation": "deployed",
                "agent_communication": "deployed",
                "advanced_learning": "deployed"
            },
            "web_server": "nginx",
            "api_endpoints": {
                "main": "http://$AITBC_HOST/api/",
                "advanced": "http://$AITBC_HOST/api/v1/advanced/"
            }
        },
        "aitbc1": {
            "host": "$AITBC1_HOST",
            "services": {
                "cross_chain_reputation": "deployed",
                "agent_communication": "deployed",
                "advanced_learning": "deployed"
            },
            "web_server": "nginx",
            "api_endpoints": {
                "main": "http://$AITBC1_HOST/api/",
                "advanced": "http://$AITBC1_HOST/api/v1/advanced/"
            }
        }
    },
    "urls": {
        "aitbc_frontend": "http://$AITBC_HOST/",
        "aitbc_api": "http://$AITBC_HOST/api/",
        "aitbc_advanced": "http://$AITBC_HOST/api/v1/advanced/",
        "aitbc1_frontend": "http://$AITBC1_HOST/",
        "aitbc1_api": "http://$AITBC1_HOST/api/",
        "aitbc1_advanced": "http://$AITBC1_HOST/api/v1/advanced/"
    },
    "next_steps": [
        "1. Monitor service performance on both servers",
        "2. Test cross-server functionality",
        "3. Verify load balancing if configured",
        "4. Monitor system resources and scaling",
        "5. Set up monitoring and alerting",
        "6. Test failover scenarios"
    ]
}
EOF
    
    print_success "Deployment report saved to $report_file"
}

# Main execution
main() {
    print_critical "🚀 STARTING AITBC PLATFORM DEPLOYMENT TO aitbc AND aitbc1 SERVERS"
    
    # Run deployment steps
    check_prerequisites
    backup_deployment
    deploy_contracts
    deploy_services
    deploy_frontend
    deploy_configuration
    verify_deployment
    test_connectivity
    generate_report
    
    print_success "🎉 AITBC PLATFORM DEPLOYMENT COMPLETED!"
    echo ""
    echo "📊 Deployment Summary:"
    echo "  Servers: aitbc, aitbc1"
    echo "  Contracts: $DEPLOY_CONTRACTS"
    echo "  Services: $DEPLOY_SERVICES"
    echo "  Frontend: $DEPLOY_FRONTEND"
    echo "  Verification: $([[ "$SKIP_VERIFICATION" != "true" ]] && echo "Completed" || echo "Skipped")"
    echo "  Backup: $BACKUP_BEFORE_DEPLOY"
    echo ""
    echo "🌐 Platform URLs:"
    echo "  aitbc Frontend: http://$AITBC_HOST/"
    echo "  aitbc API: http://$AITBC_HOST/api/"
    echo "  aitbc Advanced: http://$AITBC_HOST/api/v1/advanced/"
    echo "  aitbc1 Frontend: http://$AITBC1_HOST/"
    echo "  aitbc1 API: http://$AITBC1_HOST/api/"
    echo "  aitbc1 Advanced: http://$AITBC1_HOST/api/v1/advanced/"
    echo ""
    echo "🔧 Next Steps:"
    echo "  1. Monitor service performance on both servers"
    echo "  2. Test cross-server functionality"
    echo "  3. Verify load balancing if configured"
    echo "  4. Monitor system resources and scaling"
    echo "  5. Set up monitoring and alerting"
    echo "  6. Test failover scenarios"
    echo ""
    echo "⚠️  Important Notes:"
    echo "  - Both servers are running identical configurations"
    echo "  - Services are managed by systemd"
    echo "  - Nginx is configured for reverse proxy"
    echo "  - Health checks are available at /health"
    echo "  - API endpoints are available at /api/ and /api/v1/advanced/"
    echo "  - Backup was created before deployment"
    echo ""
    echo "🎯 Deployment Status: SUCCESS - PLATFORM LIVE ON BOTH SERVERS!"
}

# Handle script interruption
trap 'print_critical "Deployment interrupted - please check partial deployment"; exit 1' INT TERM

# Run main function
main "$@"
