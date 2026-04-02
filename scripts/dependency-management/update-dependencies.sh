#!/bin/bash
# AITBC Dependency Management Script
# Consolidates and updates dependencies across all services

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Main directory
AITBC_ROOT="/opt/aitbc"
cd "$AITBC_ROOT"

# Backup current requirements
backup_requirements() {
    log_info "Creating backup of current requirements..."
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_dir="backups/dependency_backup_$timestamp"
    mkdir -p "$backup_dir"
    
    # Backup all requirements files
    find . -name "requirements*.txt" -not -path "./venv/*" -exec cp {} "$backup_dir/" \;
    find . -name "pyproject.toml" -not -path "./venv/*" -not -path "./project-config/*" -exec cp {} "$backup_dir/" \;
    
    log_success "Backup created in $backup_dir"
}

# Update central requirements
update_central_requirements() {
    log_info "Updating central requirements..."
    
    # Install consolidated dependencies
    if [ -f "requirements-consolidated.txt" ]; then
        log_info "Installing consolidated dependencies..."
        ./venv/bin/pip install -r requirements-consolidated.txt
        log_success "Consolidated dependencies installed"
    else
        log_error "requirements-consolidated.txt not found"
        return 1
    fi
}

# Update service-specific pyproject.toml files
update_service_configs() {
    log_info "Updating service configurations..."
    
    # List of services to update
    services=(
        "apps/coordinator-api"
        "apps/blockchain-node"
        "apps/pool-hub"
        "apps/wallet"
    )
    
    for service in "${services[@]}"; do
        if [ -f "$service/pyproject.toml" ]; then
            log_info "Updating $service..."
            # Create a simplified pyproject.toml that references central dependencies
            cat > "$service/pyproject.toml" << EOF
[tool.poetry]
name = "$(basename "$service")"
version = "v0.2.3"
description = "AITBC $(basename "$service") service"
authors = ["AITBC Team"]

[tool.poetry.dependencies]
python = "^3.13"
# All dependencies managed centrally in /opt/aitbc/requirements-consolidated.txt

[tool.poetry.group.dev.dependencies]
# Development dependencies managed centrally

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
EOF
            log_success "Updated $service/pyproject.toml"
        fi
    done
}

# Update CLI requirements
update_cli_requirements() {
    log_info "Updating CLI requirements..."
    
    if [ -f "cli/requirements-cli.txt" ]; then
        # Create minimal CLI requirements (others from central)
        cat > "cli/requirements-cli.txt" << EOF
# AITBC CLI Requirements
# Core CLI-specific dependencies (others from central requirements)

# CLI Enhancement Dependencies
click>=8.1.0
rich>=13.0.0
tabulate>=0.9.0
colorama>=0.4.4
keyring>=23.0.0
click-completion>=0.5.2
typer>=0.12.0

# Note: All other dependencies are managed in /opt/aitbc/requirements-consolidated.txt
EOF
        log_success "Updated CLI requirements"
    fi
}

# Create installation profiles script
create_profiles() {
    log_info "Creating installation profiles..."
    
    cat > "scripts/install-profiles.sh" << 'EOF'
#!/bin/bash
# AITBC Installation Profiles
# Install specific dependency sets for different use cases

set -euo pipefail

AITBC_ROOT="/opt/aitbc"
cd "$AITBC_ROOT"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Installation profiles
install_web() {
    log_info "Installing web profile..."
    ./venv/bin/pip install fastapi uvicorn gunicorn starlette
}

install_database() {
    log_info "Installing database profile..."
    ./venv/bin/pip install sqlalchemy sqlmodel alembic aiosqlite asyncpg
}

install_blockchain() {
    log_info "Installing blockchain profile..."
    ./venv/bin/pip install cryptography pynacl ecdsa base58 bech32 web3 eth-account
}

install_ml() {
    log_info "Installing ML profile..."
    ./venv/bin/pip install torch torchvision numpy pandas
}

install_cli() {
    log_info "Installing CLI profile..."
    ./venv/bin/pip install click rich typer click-completion tabulate colorama keyring
}

install_monitoring() {
    log_info "Installing monitoring profile..."
    ./venv/bin/pip install structlog sentry-sdk prometheus-client
}

install_image() {
    log_info "Installing image processing profile..."
    ./venv/bin/pip install pillow opencv-python
}

install_all() {
    log_info "Installing all profiles..."
    ./venv/bin/pip install -r requirements-consolidated.txt
}

install_minimal() {
    log_info "Installing minimal profile..."
    ./venv/bin/pip install fastapi pydantic python-dotenv
}

# Main menu
case "${1:-all}" in
    "web")
        install_web
        ;;
    "database")
        install_database
        ;;
    "blockchain")
        install_blockchain
        ;;
    "ml")
        install_ml
        ;;
    "cli")
        install_cli
        ;;
    "monitoring")
        install_monitoring
        ;;
    "image")
        install_image
        ;;
    "all")
        install_all
        ;;
    "minimal")
        install_minimal
        ;;
    *)
        echo "Usage: $0 {web|database|blockchain|ml|cli|monitoring|image|all|minimal}"
        echo ""
        echo "Profiles:"
        echo "  web        - Web framework dependencies"
        echo "  database   - Database and ORM dependencies"
        echo "  blockchain  - Cryptography and blockchain dependencies"
        echo "  ml         - Machine learning dependencies"
        echo "  cli        - CLI tool dependencies"
        echo "  monitoring - Logging and monitoring dependencies"
        echo "  image      - Image processing dependencies"
        echo "  all        - All dependencies (default)"
        echo "  minimal    - Minimal set for basic operation"
        exit 1
        ;;
esac

log_success "Installation completed"
EOF
    
    chmod +x "scripts/install-profiles.sh"
    log_success "Created installation profiles script"
}

# Validate dependency consistency
validate_dependencies() {
    log_info "Validating dependency consistency..."
    
    # Check for conflicts
    log_info "Checking for version conflicts..."
    conflicts=$(./venv/bin/pip check 2>&1 || true)
    
    if echo "$conflicts" | grep -q "No broken requirements"; then
        log_success "No dependency conflicts found"
    else
        log_warning "Dependency conflicts found:"
        echo "$conflicts"
        return 1
    fi
}

# Generate dependency report
generate_report() {
    log_info "Generating dependency report..."
    
    report_file="dependency-report-$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" << EOF
AITBC Dependency Report
====================
Generated: $(date)

Consolidated Dependencies:
$(wc -l requirements-consolidated.txt)

Installed Packages:
$(./venv/bin/pip list | wc -l)

Disk Usage:
$(du -sh venv/ | cut -f1)

Security Audit:
$(./venv/bin/safety check --json 2>/dev/null | ./venv/bin/python -c "import json, sys; data=json.load(sys.stdin); print(f'Vulnerabilities: {len(data)}')" 2>/dev/null || echo "Unable to check")

EOF
    
    log_success "Dependency report generated: $report_file"
}

# Main execution
main() {
    log_info "Starting AITBC dependency consolidation..."
    
    backup_requirements
    update_central_requirements
    update_service_configs
    update_cli_requirements
    create_profiles
    
    if validate_dependencies; then
        generate_report
        log_success "Dependency consolidation completed successfully!"
        
        echo ""
        log_info "Next steps:"
        echo "1. Test services with new dependencies"
        echo "2. Run './scripts/install-profiles.sh <profile>' for specific installations"
        echo "3. Monitor for any dependency-related issues"
    else
        log_error "Dependency consolidation failed - check conflicts"
        exit 1
    fi
}

# Run main function
main "$@"
