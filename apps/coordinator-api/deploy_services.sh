#!/bin/bash

# AITBC Enhanced Services Deployment Script
# Deploys systemd services for all enhanced AITBC services

set -e

echo "🚀 Deploying AITBC Enhanced Services..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if user is root or debian
if [[ $(whoami) != "root" && $(whoami) != "debian" ]]; then
    print_error "This script should be run as root or debian user."
    exit 1
fi

# Set SUDO command based on user
if [[ $(whoami) == "root" ]]; then
    SUDO=""
else
    SUDO="sudo"
fi

# Service definitions
SERVICES=(
    "aitbc-multimodal:8002:Multi-Modal Agent Processing"
    "aitbc-gpu-multimodal:8003:GPU Multi-Modal Processing"
    "aitbc-modality-optimization:8004:Modality Optimization"
    "aitbc-adaptive-learning:8005:Adaptive Learning"
    "aitbc-marketplace-enhanced:8006:Enhanced Marketplace"
    "aitbc-openclaw-enhanced:8007:OpenClaw Enhanced"
)

# Install systemd services
print_status "Installing systemd services..."

for service_info in "${SERVICES[@]}"; do
    IFS=':' read -r service_name port description <<< "$service_info"
    
    print_status "Installing $service_name ($description)..."
    
    # Copy service file
    $SUDO cp "/home/oib/aitbc/apps/coordinator-api/systemd/${service_name}.service" "/etc/systemd/system/"
    
    # Reload systemd
    $SUDO systemctl daemon-reload
    
    # Enable service
    $SUDO systemctl enable "$service_name"
    
    print_status "✅ $service_name installed and enabled"
done

# Update systemd files to use correct app entry points
print_status "Updating systemd service files..."

# Update multimodal service
$SUDO sed -i 's|src.app.services.multimodal_agent:app|src.app.services.multimodal_app:app|' /etc/systemd/system/aitbc-multimodal.service

# Update gpu multimodal service
$SUDO sed -i 's|src.app.services.gpu_multimodal:app|src.app.services.gpu_multimodal_app:app|' /etc/systemd/system/aitbc-gpu-multimodal.service

# Update modality optimization service
$SUDO sed -i 's|src.app.services.modality_optimization:app|src.app.services.modality_optimization_app:app|' /etc/systemd/system/aitbc-modality-optimization.service

# Update adaptive learning service
$SUDO sed -i 's|src.app.services.adaptive_learning:app|src.app.services.adaptive_learning_app:app|' /etc/systemd/system/aitbc-adaptive-learning.service

# Update marketplace enhanced service
$SUDO sed -i 's|src.app.routers.marketplace_enhanced_simple:router|src.app.routers.marketplace_enhanced_app:app|' /etc/systemd/system/aitbc-marketplace-enhanced.service

# Update openclaw enhanced service
$SUDO sed -i 's|src.app.routers.openclaw_enhanced_simple:router|src.app.routers.openclaw_enhanced_app:app|' /etc/systemd/system/aitbc-openclaw-enhanced.service

# Reload systemd
$SUDO systemctl daemon-reload

# Start services
print_status "Starting enhanced services..."

for service_info in "${SERVICES[@]}"; do
    IFS=':' read -r service_name port description <<< "$service_info"
    
    print_status "Starting $service_name..."
    
    if $SUDO systemctl start "$service_name"; then
        print_status "✅ $service_name started successfully"
    else
        print_error "❌ Failed to start $service_name"
    fi
done

# Wait a moment for services to start
sleep 3

# Check service status
print_status "Checking service status..."

for service_info in "${SERVICES[@]}"; do
    IFS=':' read -r service_name port description <<< "$service_info"
    
    if $SUDO systemctl is-active --quiet "$service_name"; then
        print_status "✅ $service_name is running"
        
        # Test health endpoint
        if curl -s "http://127.0.0.1:$port/health" > /dev/null; then
            print_status "✅ $service_name health check passed"
        else
            print_warning "⚠️  $service_name health check failed"
        fi
    else
        print_error "❌ $service_name is not running"
        
        # Show logs for failed service
        echo "=== Logs for $service_name ==="
        $SUDO journalctl -u "$service_name" --no-pager -l | tail -10
        echo "========================"
    fi
done

# Create service status script
print_status "Creating service status script..."

cat > /home/oib/aitbc/apps/coordinator-api/check_services.sh << 'EOF'
#!/bin/bash

echo "🔍 AITBC Enhanced Services Status"
echo "=============================="

SERVICES=(
    "aitbc-multimodal:8002"
    "aitbc-gpu-multimodal:8003"
    "aitbc-modality-optimization:8004"
    "aitbc-adaptive-learning:8005"
    "aitbc-marketplace-enhanced:8006"
    "aitbc-openclaw-enhanced:8007"
)

for service_info in "${SERVICES[@]}"; do
    IFS=':' read -r service_name port <<< "$service_info"
    
    echo -n "$service_name: "
    
    if systemctl is-active --quiet "$service_name"; then
        echo -n "✅ RUNNING"
        
        if curl -s "http://127.0.0.1:$port/health" > /dev/null 2>&1; then
            echo " (Healthy)"
        else
            echo " (Unhealthy)"
        fi
    else
        echo "❌ STOPPED"
    fi
done

echo ""
echo "📊 Service Logs:"
echo "$SUDO journalctl -u aitbc-multimodal -f"
echo "$SUDO journalctl -u aitbc-gpu-multimodal -f"
echo "$SUDO journalctl -u aitbc-modality-optimization -f"
echo "$SUDO journalctl -u aitbc-adaptive-learning -f"
echo "$SUDO journalctl -u aitbc-marketplace-enhanced -f"
echo "$SUDO journalctl -u aitbc-openclaw-enhanced -f"
EOF

chmod +x /home/oib/aitbc/apps/coordinator-api/check_services.sh

# Create service management script
print_status "Creating service management script..."

cat > /home/oib/aitbc/apps/coordinator-api/manage_services.sh << 'EOF'
#!/bin/bash

# AITBC Enhanced Services Management Script

case "$1" in
    start)
        echo "🚀 Starting all enhanced services..."
        $SUDO systemctl start aitbc-multimodal aitbc-gpu-multimodal aitbc-modality-optimization aitbc-adaptive-learning aitbc-marketplace-enhanced aitbc-openclaw-enhanced
        ;;
    stop)
        echo "🛑 Stopping all enhanced services..."
        $SUDO systemctl stop aitbc-multimodal aitbc-gpu-multimodal aitbc-modality-optimization aitbc-adaptive-learning aitbc-marketplace-enhanced aitbc-openclaw-enhanced
        ;;
    restart)
        echo "🔄 Restarting all enhanced services..."
        $SUDO systemctl restart aitbc-multimodal aitbc-gpu-multimodal aitbc-modality-optimization aitbc-adaptive-learning aitbc-marketplace-enhanced aitbc-openclaw-enhanced
        ;;
    status)
        /home/oib/aitbc/apps/coordinator-api/check_services.sh
        ;;
    logs)
        if [ -n "$2" ]; then
            echo "📋 Showing logs for $2..."
            $SUDO journalctl -u "$2" -f
        else
            echo "📋 Available services for logs:"
            echo "aitbc-multimodal"
            echo "aitbc-gpu-multimodal"
            echo "aitbc-modality-optimization"
            echo "aitbc-adaptive-learning"
            echo "aitbc-marketplace-enhanced"
            echo "aitbc-openclaw-enhanced"
            echo ""
            echo "Usage: $0 logs <service-name>"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [service]}"
        echo ""
        echo "Commands:"
        echo "  start   - Start all enhanced services"
        echo "  stop    - Stop all enhanced services"
        echo "  restart - Restart all enhanced services"
        echo "  status  - Show service status"
        echo "  logs    - Show logs for specific service"
        echo ""
        echo "Examples:"
        echo "  $0 start"
        echo "  $0 status"
        echo "  $0 logs aitbc-multimodal"
        exit 1
        ;;
esac
EOF

chmod +x /home/oib/aitbc/apps/coordinator-api/manage_services.sh

print_status "✅ Deployment completed!"
print_status ""
print_status "📋 Service Management:"
print_status "  Check status: ./check_services.sh"
print_status "  Manage services: ./manage_services.sh {start|stop|restart|status|logs}"
print_status ""
print_status "🔗 Service Endpoints:"
print_status "  Multi-Modal: http://127.0.0.1:8002"
print_status "  GPU Multi-Modal: http://127.0.0.1:8003"
print_status "  Modality Optimization: http://127.0.0.1:8004"
print_status "  Adaptive Learning: http://127.0.0.1:8005"
print_status "  Enhanced Marketplace: http://127.0.0.1:8006"
print_status "  OpenClaw Enhanced: http://127.0.0.1:8007"
print_status ""
print_status "📊 Monitoring:"
print_status "  $SUDO systemctl status aitbc-multimodal"
print_status "  $SUDO journalctl -u aitbc-multimodal -f"
print_status "  $SUDO journalctl -u aitbc-gpu-multimodal -f"
print_status "  $SUDO journalctl -u aitbc-modality-optimization -f"
print_status "  $SUDO journalctl -u aitbc-adaptive-learning -f"
print_status "  $SUDO journalctl -u aitbc-marketplace-enhanced -f"
print_status "  $SUDO journalctl -u aitbc-openclaw-enhanced -f"
