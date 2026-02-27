#!/usr/bin/env bash

# AITBC Developer Ecosystem Frontend Deployment Script
# Deploys the React frontend application to production
#
# Usage: ./deploy-frontend.sh [environment] [server]
# Environment: development, staging, production
# Server: aitbc-cascade (default), custom-server

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# Parse arguments
ENVIRONMENT="${1:-production}"
SERVER="${2:-aitbc-cascade}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
ROOT_DIR="$(dirname "$APP_DIR)"

echo "🚀 AITBC Frontend Deployment"
echo "============================="
echo "Environment: $ENVIRONMENT"
echo "Server: $SERVER"
echo "App Directory: $APP_DIR"
echo ""

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if we're in the correct directory
    if [[ ! -f "$APP_DIR/package.json" ]]; then
        print_error "package.json not found in $APP_DIR"
        exit 1
    fi
    
    # Check if build exists
    if [[ ! -d "$APP_DIR/dist" ]]; then
        print_warning "Build directory not found. Building application..."
        build_application
    fi
    
    # Check SSH connection to server
    if ! ssh -o ConnectTimeout=5 "$SERVER" "echo 'SSH connection successful'" 2>/dev/null; then
        print_error "Cannot connect to server $SERVER"
        print_error "Please ensure SSH keys are properly configured"
        exit 1
    fi
    
    print_success "Prerequisites check completed"
}

# Build application
build_application() {
    print_status "Building frontend application..."
    
    cd "$APP_DIR"
    
    # Set environment variables
    if [[ "$ENVIRONMENT" == "production" ]]; then
        export NODE_ENV=production
    elif [[ "$ENVIRONMENT" == "staging" ]]; then
        export NODE_ENV=staging
    else
        export NODE_ENV=development
    fi
    
    # Build the application
    if npm run build; then
        print_success "Application built successfully"
    else
        print_error "Application build failed"
        exit 1
    fi
}

# Deploy to server
deploy_to_server() {
    print_status "Deploying frontend to $SERVER..."
    
    # Create remote directory if it doesn't exist
    ssh "$SERVER" "mkdir -p /var/www/aitbc.bubuit.net/marketplace"
    
    # Copy files to server
    print_status "Copying files to server..."
    
    # Copy HTML files
    scp "$APP_DIR/dist/index.html" "$SERVER:/var/www/aitbc.bubuit.net/marketplace/"
    
    # Copy JavaScript files
    scp "$APP_DIR/dist/assets/"*.js "$SERVER:/var/www/aitbc.bubuit.net/marketplace/assets/" 2>/dev/null || true
    
    # Copy CSS files
    scp "$APP_DIR/dist/assets/"*.css "$SERVER:/var/www/aitbc.bubuit.net/marketplace/assets/" 2>/dev/null || true
    
    # Copy other assets
    scp -r "$APP_DIR/dist/assets/"* "$SERVER:/var/www/aitbc.bubuit.net/marketplace/assets/" 2>/dev/null || true
    
    print_success "Files copied to server"
}

# Configure nginx
configure_nginx() {
    print_status "Configuring nginx..."
    
    # Create nginx configuration
    ssh "$SERVER" "cat > /etc/nginx/sites-available/marketplace.conf << 'EOF'
server {
    listen 80;
    server_name aitbc.bubuit.net;
    
    location /marketplace/ {
        alias /var/www/aitbc.bubuit.net/marketplace/;
        try_files \$uri \$uri/ /marketplace/index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
            expires 1y;
            add_header Cache-Control \"public, immutable\";
        }
        
        # Security headers
        add_header X-Frame-Options \"SAMEORIGIN\" always;
        add_header X-Content-Type-Options \"nosniff\" always;
        add_header X-XSS-Protection \"1; mode=block\" always;
        add_header Referrer-Policy \"strict-origin-when-cross-origin\" always;
    }
    
    # Redirect root to marketplace
    location = / {
        return 301 /marketplace/;
    }
}
EOF"
    
    # Enable site
    ssh "$SERVER" "ln -sf /etc/nginx/sites-available/marketplace.conf /etc/nginx/sites-enabled/"
    
    # Test nginx configuration
    if ssh "$SERVER" "nginx -t"; then
        print_success "Nginx configuration is valid"
    else
        print_error "Nginx configuration is invalid"
        exit 1
    fi
    
    # Reload nginx
    ssh "$SERVER" "systemctl reload nginx"
    
    print_success "Nginx configured and reloaded"
}

# Set permissions
set_permissions() {
    print_status "Setting file permissions..."
    
    ssh "$SERVER" "chown -R www-data:www-data /var/www/aitbc.bubuit.net/marketplace"
    ssh "$SERVER" "chmod -R 755 /var/www/aitbc.bubuit.net/marketplace"
    
    print_success "Permissions set"
}

# Health check
health_check() {
    print_status "Performing health check..."
    
    # Wait a moment for nginx to reload
    sleep 5
    
    # Check if the site is accessible
    if curl -s -o /dev/null -w "%{http_code}" "http://aitbc.bubuit.net/marketplace/" | grep -q "200"; then
        print_success "Site is accessible and responding correctly"
    else
        print_warning "Site may not be accessible. Please check manually."
    fi
    
    # Check nginx status
    if ssh "$SERVER" "systemctl is-active nginx" | grep -q "active"; then
        print_success "Nginx is running"
    else
        print_error "Nginx is not running"
        exit 1
    fi
}

# Generate deployment report
generate_deployment_report() {
    print_status "Generating deployment report..."
    
    local report_file="$ROOT_DIR/frontend-deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" << EOF
{
    "deployment": {
        "environment": "$ENVIRONMENT",
        "server": "$SERVER",
        "timestamp": "$(date -Iseconds)",
        "app_directory": "$APP_DIR",
        "build_directory": "$APP_DIR/dist"
    },
    "configuration": {
        "nginx_config": "/etc/nginx/sites-available/marketplace.conf",
        "web_root": "/var/www/aitbc.bubuit.net/marketplace",
        "server_name": "aitbc.bubuit.net"
    },
    "urls": {
        "production": "http://aitbc.bubuit.net/marketplace/",
        "health_check": "http://aitbc.bubuit.net/marketplace/"
    }
}
EOF
    
    print_success "Deployment report saved to $report_file"
}

# Rollback function
rollback() {
    print_warning "Rolling back deployment..."
    
    # Restore previous version if exists
    if ssh "$SERVER" "test -d /var/www/aitbc.bubuit.net/marketplace.backup"; then
        ssh "$SERVER" "rm -rf /var/www/aitbc.bubuit.net/marketplace"
        ssh "$SERVER" "mv /var/www/aitbc.bubuit.net/marketplace.backup /var/www/aitbc.bubuit.net/marketplace"
        ssh "$SERVER" "systemctl reload nginx"
        print_success "Rollback completed"
    else
        print_error "No backup found for rollback"
        exit 1
    fi
}

# Main execution
main() {
    print_status "Starting frontend deployment..."
    
    # Create backup of current deployment
    if ssh "$SERVER" "test -d /var/www/aitbc.bubuit.net/marketplace"; then
        print_status "Creating backup of current deployment..."
        ssh "$SERVER" "cp -r /var/www/aitbc.bubuit.net/marketplace /var/www/aitbc.bubuit.net/marketplace.backup"
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Deploy to server
    deploy_to_server
    
    # Configure nginx
    configure_nginx
    
    # Set permissions
    set_permissions
    
    # Health check
    health_check
    
    # Generate deployment report
    generate_deployment_report
    
    print_success "🎉 Frontend deployment completed successfully!"
    echo ""
    echo "🌐 Application URL: http://aitbc.bubuit.net/marketplace/"
    echo "📊 Deployment report: $report_file"
    echo ""
    echo "Next steps:"
    echo "1. Test the application in browser"
    echo "2. Verify all functionality works"
    echo "3. Monitor application logs"
    echo "4. Update DNS if needed"
}

# Handle script interruption
trap 'print_error "Deployment interrupted"; rollback; exit 1' INT TERM

# Handle rollback on error
trap 'print_error "Deployment failed, initiating rollback..."; rollback; exit 1' ERR

# Run main function
main "$@"
