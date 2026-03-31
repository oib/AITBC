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
    ./venv/bin/pip install fastapi==0.115.6 uvicorn[standard]==0.32.1 gunicorn==22.0.0 "starlette>=0.40.0,<0.42.0"
}

install_database() {
    log_info "Installing database profile..."
    ./venv/bin/pip install sqlalchemy==2.0.47 sqlmodel==0.0.37 alembic==1.18.0 aiosqlite==0.20.0 asyncpg==0.29.0
}

install_blockchain() {
    log_info "Installing blockchain profile..."
    ./venv/bin/pip install cryptography==46.0.0 pynacl==1.5.0 ecdsa==0.19.0 base58==2.1.1 bech32==1.2.0 web3==6.11.0 eth-account==0.13.0
}

install_ml() {
    log_info "Installing ML profile..."
    ./venv/bin/pip install torch==2.10.0 torchvision==0.15.0 numpy==1.26.0 pandas==2.2.0
}

install_cli() {
    log_info "Installing CLI profile..."
    ./venv/bin/pip install click==8.1.0 rich==13.0.0 typer==0.12.0 click-completion==0.5.2 tabulate==0.9.0 colorama==0.4.4 keyring==23.0.0
}

install_monitoring() {
    log_info "Installing monitoring profile..."
    ./venv/bin/pip install structlog==24.1.0 sentry-sdk==2.0.0 prometheus-client==0.24.0
}

install_image() {
    log_info "Installing image processing profile..."
    ./venv/bin/pip install pillow==10.0.0 opencv-python==4.9.0
}

install_all() {
    log_info "Installing all profiles..."
    if [ -f "requirements-consolidated.txt" ]; then
        ./venv/bin/pip install -r requirements-consolidated.txt
    else
        log_info "Installing profiles individually..."
        install_web
        install_database
        install_blockchain
        install_cli
        install_monitoring
        # ML and Image processing are optional - install separately if needed
    fi
}

install_minimal() {
    log_info "Installing minimal profile..."
    ./venv/bin/pip install fastapi==0.115.6 pydantic==2.12.0 python-dotenv==1.2.0
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
