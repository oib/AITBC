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
    command -v node >/dev/null 2>&1 || error "Node.js is not installed"
    command -v npm >/dev/null 2>&1 || error "npm is not installed"
    
    # Check Python version
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    if [ "$(printf '%s\n' "3.13.5" "$python_version" | sort -V | head -n1)" != "3.13.5" ]; then
        error "Python 3.13.5+ is required, found $python_version"
    fi
    
    # Check Node.js version
    node_version=$(node -v | sed 's/v//')
    if [ "$(printf '%s\n' "24.14.0" "$node_version" | sort -V | head -n1)" != "24.14.0" ]; then
        error "Node.js 24.14.0+ is required, found $node_version"
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
    git clone https://github.com/aitbc/aitbc.git aitbc || error "Failed to clone repository"
    
    cd /opt/aitbc
    success "Repository cloned successfully"
}

# Setup runtime directories
setup_runtime_directories() {
    log "Setting up runtime directories..."
    
    # Create standard Linux directories
    directories=(
        "/var/lib/aitbc"
        "/var/lib/aitbc/keystore"
        "/var/lib/aitbc/data"
        "/var/log/aitbc"
        "/etc/aitbc"
    )
    
    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        log "Created directory: $dir"
    done
    
    # Set permissions
    chmod 755 /var/lib/aitbc
    chmod 700 /var/lib/aitbc/keystore  # Secure keystore
    chmod 755 /var/lib/aitbc/data
    chmod 755 /var/log/aitbc
    chmod 755 /etc/aitbc
    
    # Set ownership
    chown root:root /var/lib/aitbc
    chown root:root /var/lib/aitbc/keystore
    chown root:root /var/lib/aitbc/data
    chown root:root /var/log/aitbc
    chown root:root /etc/aitbc
    
    # Create README files
    echo "# AITBC Runtime Data Directory" > /var/lib/aitbc/README.md
    echo "# Keystore for blockchain keys (SECURE)" > /var/lib/aitbc/keystore/README.md
    echo "# Application databases" > /var/lib/aitbc/data/README.md
    echo "# Application logs" > /var/log/aitbc/README.md
    echo "# AITBC Configuration Files" > /etc/aitbc/README.md
    
    success "Runtime directories setup completed"
}

# Setup Python virtual environments
setup_venvs() {
    log "Setting up Python virtual environments..."
    
    # Create central virtual environment if it doesn't exist
    if [ ! -d "/opt/aitbc/venv" ]; then
        log "Creating central virtual environment..."
        cd /opt/aitbc
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
    else
        log "Central virtual environment already exists, activating..."
        source /opt/aitbc/venv/bin/activate
    fi
    
    # Install all dependencies from central requirements.txt
    log "Installing all dependencies from central requirements.txt..."
    
    # Install main requirements (contains all service dependencies)
    if [ -f "/opt/aitbc/requirements.txt" ]; then
        pip install -r /opt/aitbc/requirements.txt
    else
        error "Main requirements.txt not found"
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
        "aitbc-blockchain-node.service"
        "aitbc-blockchain-rpc.service"
        "aitbc-gpu.service"
        "aitbc-marketplace.service"
        "aitbc-openclaw.service"
        "aitbc-ai.service"
        "aitbc-learning.service"
        "aitbc-explorer.service"
        "aitbc-web-ui.service"
        "aitbc-agent-coordinator.service"
        "aitbc-agent-registry.service"
        "aitbc-multimodal.service"
        "aitbc-modality-optimization.service"
    )
    
    for service in "${services[@]}"; do
        if [ -f "/opt/aitbc/systemd/$service" ]; then
            log "Installing $service..."
            ln -sf "/opt/aitbc/systemd/$service" /etc/systemd/system/
        else
            warning "Service file not found: $service"
        fi
    done
    
    # Reload systemd
    systemctl daemon-reload
    
    success "Systemd services installed"
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

# Core Services (8000-8009)
echo ""
echo "🔧 Core Services (8000-8009):"
check_service "Coordinator API" "http://localhost:8000/health"
check_service "Exchange API" "http://localhost:8001/api/health"
check_service "Wallet API" "http://localhost:8003/health"
check_service "Marketplace API" "http://localhost:8006/health"
check_service "Explorer" "http://localhost:8004/health"
check_service "Multimodal Service" "http://localhost:8005/health"

# AI/Agent/GPU Services (8010-8019)
echo ""
echo "🚀 AI/Agent/GPU Services (8010-8019):"
check_service "GPU Service" "http://localhost:8010/health"
check_service "Learning Service" "http://localhost:8010/health"
check_service "Agent Coordinator" "http://localhost:8011/health"
check_service "Agent Registry" "http://localhost:8012/health"
check_service "OpenClaw Service" "http://localhost:8013/health"
check_service "AI Service" "http://localhost:8009/health"
check_service "Web UI" "http://localhost:8016/health"

# Other Services (8020-8029)
echo ""
echo "📊 Other Services (8020-8029):"
check_service "Modality Optimization" "http://localhost:8023/health"

# Check blockchain node and RPC
echo ""
echo "Blockchain Services:"
if systemctl is-active --quiet aitbc-blockchain-node.service; then
    echo -e "${GREEN}✓${NC} Blockchain Node is running"
else
    echo -e "${RED}✗${NC} Blockchain Node is not running"
fi

if systemctl is-active --quiet aitbc-blockchain-rpc.service; then
    echo -e "${GREEN}✓${NC} Blockchain RPC is running"
else
    echo -e "${RED}✗${NC} Blockchain RPC is not running"
fi

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
    if systemctl start aitbc-wallet aitbc-coordinator-api aitbc-exchange-api aitbc-blockchain-node aitbc-blockchain-rpc aitbc-gpu aitbc-marketplace aitbc-openclaw aitbc-ai aitbc-learning aitbc-explorer aitbc-web-ui aitbc-agent-coordinator aitbc-agent-registry aitbc-multimodal aitbc-modality-optimization 2>/dev/null; then
        log "Services started via systemd"
        sleep 5
        
        # Check if services are running
        if systemctl is-active --quiet aitbc-wallet aitbc-coordinator-api aitbc-exchange-api aitbc-blockchain-node aitbc-blockchain-rpc aitbc-gpu aitbc-marketplace aitbc-openclaw aitbc-ai aitbc-learning aitbc-explorer aitbc-web-ui aitbc-agent-coordinator aitbc-agent-registry aitbc-multimodal aitbc-modality-optimization; then
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
    
    # Enable services for auto-start on boot
    systemctl enable aitbc-wallet.service
    systemctl enable aitbc-coordinator-api.service
    systemctl enable aitbc-exchange-api.service
    systemctl enable aitbc-blockchain-node.service
    systemctl enable aitbc-blockchain-rpc.service
    systemctl enable aitbc-gpu.service
    systemctl enable aitbc-marketplace.service
    systemctl enable aitbc-openclaw.service
    systemctl enable aitbc-ai.service
    systemctl enable aitbc-learning.service
    systemctl enable aitbc-explorer.service
    systemctl enable aitbc-web-ui.service
    systemctl enable aitbc-agent-coordinator.service
    systemctl enable aitbc-agent-registry.service
    systemctl enable aitbc-multimodal.service
    systemctl enable aitbc-modality-optimization.service
    
    success "Auto-start configured"
}

# Main function
main() {
    log "Starting AITBC setup..."
    
    check_root
    check_prerequisites
    clone_repo
    setup_runtime_directories
    setup_venvs
    install_services
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
    echo "Runtime Directories:"
    echo "  Keystore: /var/lib/aitbc/keystore/"
    echo "  Data: /var/lib/aitbc/data/"
    echo "  Logs: /var/lib/aitbc/logs/"
    echo "  Config: /etc/aitbc/"
    echo ""
    echo "Management Commands:"
    echo "  Health check: /opt/aitbc/health-check.sh"
    echo "  Restart services: systemctl restart aitbc-wallet aitbc-coordinator-api aitbc-exchange-api"
    echo "  View logs: journalctl -u aitbc-wallet -f"
}

# Run main function
main "$@"
