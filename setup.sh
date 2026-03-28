#!/bin/bash

# AITBC Local Setup Script
# Sets up AITBC services on a new host with systemd

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "This script must be run as root (use sudo)"
    fi
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if required tools are installed
    command -v python3 >/dev/null 2>&1 || error "Python 3 is not installed"
    command -v pip3 >/dev/null 2>&1 || error "pip3 is not installed"
    command -v git >/dev/null 2>&1 || error "git is not installed"
    command -v systemctl >/dev/null 2>&1 || error "systemctl is not available"
    
    # Check Python version
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [ "$(printf '%s\n' "3.8" "$python_version" | sort -V | head -n1)" != "3.8" ]; then
        error "Python 3.8+ is required, found $python_version"
    fi
    
    success "Prerequisites check passed"
}

# Clone repository
clone_repo() {
    log "Cloning AITBC repository..."
    
    # Remove existing installation if present
    if [ -d "/opt/aitbc" ]; then
        warning "Removing existing /opt/aitbc"
        rm -rf /opt/aitbc
    fi
    
    # Clone repository
    cd /opt
    git clone https://gitea.bubuit.net/oib/aitbc.git aitbc || {
        # Try alternative URL
        git clone http://10.0.3.107:3000/oib/aitbc.git aitbc || error "Failed to clone repository"
    }
    
    cd /opt/aitbc
    success "Repository cloned successfully"
}

# Setup Python virtual environments
setup_venvs() {
    log "Setting up Python virtual environments..."
    
    # Wallet service
    log "Setting up wallet service..."
    cd /opt/aitbc/apps/wallet
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install fastapi uvicorn pydantic httpx python-dotenv websockets
    
    # Coordinator API
    log "Setting up coordinator API..."
    cd /opt/aitbc/apps/coordinator-api
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        pip install fastapi uvicorn pydantic httpx python-dotenv
    fi
    
    # Exchange API
    log "Setting up exchange API..."
    cd /opt/aitbc/apps/exchange
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        pip install fastapi uvicorn pydantic python-multipart
    fi
    
    success "Virtual environments setup completed"
}

# Install systemd services
install_services() {
    log "Installing systemd services..."
    
    # Install core services
    services=(
        "aitbc-wallet.service"
        "aitbc-coordinator-api.service"
        "aitbc-exchange-api.service"
        "aitbc-blockchain-rpc.service"
    )
    
    for service in "${services[@]}"; do
        if [ -f "/opt/aitbc/systemd/$service" ]; then
            log "Installing $service..."
            cp "/opt/aitbc/systemd/$service" /etc/systemd/system/
        else
            warning "Service file not found: $service"
        fi
    done
    
    # Reload systemd
    systemctl daemon-reload
    
    success "Systemd services installed"
}

# Create startup script
create_startup_script() {
    log "Creating startup script..."
    
    cat > /opt/aitbc/start-services.sh << 'EOF'
#!/bin/bash

# AITBC Services Startup Script

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting AITBC services..."

# Start wallet service
log "Starting wallet service..."
cd /opt/aitbc/apps/wallet
source .venv/bin/activate
nohup python simple_daemon.py > /var/log/aitbc-wallet.log 2>&1 &
echo $! > /var/run/aitbc-wallet.pid

# Start coordinator API
log "Starting coordinator API..."
cd /opt/aitbc/apps/coordinator-api/src
source ../.venv/bin/activate
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /var/log/aitbc-coordinator.log 2>&1 &
echo $! > /var/run/aitbc-coordinator.pid

# Start exchange API
log "Starting exchange API..."
cd /opt/aitbc/apps/exchange
source .venv/bin/activate
nohup python simple_exchange_api.py > /var/log/aitbc-exchange.log 2>&1 &
echo $! > /var/run/aitbc-exchange.pid

log "All services started"
EOF

    chmod +x /opt/aitbc/start-services.sh
    
    success "Startup script created"
}

# Create health check script
create_health_check() {
    log "Creating health check script..."
    
    cat > /opt/aitbc/health-check.sh << 'EOF'
#!/bin/bash

# AITBC Health Check Script

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_service() {
    local name=$1
    local url=$2
    local expected=${3:-200}
    
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "$expected"; then
        echo -e "${GREEN}✓${NC} $name is healthy"
        return 0
    else
        echo -e "${RED}✗${NC} $name is unhealthy"
        return 1
    fi
}

echo "AITBC Service Health Check"
echo "========================"

# Check wallet service
check_service "Wallet API" "http://localhost:8003/health"

# Check exchange API
check_service "Exchange API" "http://localhost:8001/api/health"

# Check coordinator API
check_service "Coordinator API" "http://localhost:8000/health"

# Check process status
echo ""
echo "Process Status:"
ps aux | grep -E "simple_daemon|uvicorn|simple_exchange_api" | grep -v grep | while read line; do
    echo -e "${GREEN}✓${NC} $line"
done
EOF

    chmod +x /opt/aitbc/health-check.sh
    
    success "Health check script created"
}

# Start services
start_services() {
    log "Starting AITBC services..."
    
    # Try systemd first
    if systemctl start aitbc-wallet aitbc-coordinator-api aitbc-exchange-api 2>/dev/null; then
        log "Services started via systemd"
        sleep 5
        
        # Check if services are running
        if systemctl is-active --quiet aitbc-wallet aitbc-coordinator-api aitbc-exchange-api; then
            success "Services started successfully via systemd"
        else
            warning "Some systemd services failed, falling back to manual startup"
            /opt/aitbc/start-services.sh
        fi
    else
        log "Systemd services not available, using manual startup"
        /opt/aitbc/start-services.sh
    fi
    
    # Wait for services to initialize
    sleep 10
    
    # Run health check
    /opt/aitbc/health-check.sh
}

# Setup auto-start
setup_autostart() {
    log "Setting up auto-start..."
    
    # Create systemd service for startup script
    cat > /etc/systemd/system/aitbc-startup.service << EOF
[Unit]
Description=AITBC Services Startup
After=network.target

[Service]
Type=oneshot
ExecStart=/opt/aitbc/start-services.sh
RemainAfterExit=yes
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

    systemctl enable aitbc-startup.service
    
    success "Auto-start configured"
}

# Main function
main() {
    log "Starting AITBC local setup..."
    
    check_root
    check_prerequisites
    clone_repo
    setup_venvs
    install_services
    create_startup_script
    create_health_check
    start_services
    setup_autostart
    
    success "AITBC setup completed!"
    echo ""
    echo "Service Information:"
    echo "  Wallet API: http://localhost:8003/health"
    echo "  Exchange API: http://localhost:8001/api/health"
    echo "  Coordinator API: http://localhost:8000/health"
    echo ""
    echo "Management Commands:"
    echo "  Health check: /opt/aitbc/health-check.sh"
    echo "  Restart services: /opt/aitbc/start-services.sh"
    echo "  View logs: tail -f /var/log/aitbc-*.log"
}

# Run main function
main "$@"
