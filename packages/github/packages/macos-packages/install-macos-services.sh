#!/bin/bash

# AITBC Services Installer for Mac Studio (Apple Silicon)
# Install individual service packages

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                AITBC Services Installer                   ║"
echo "║                 Mac Studio (Apple Silicon)                 ║"
echo "║                    Individual Services                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}❌ This installer is for macOS only${NC}"
    exit 1
fi

# Check Apple Silicon
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo -e "${RED}❌ This package is for Apple Silicon Macs only${NC}"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Available services
SERVICES=(
    "aitbc-node-service-0.1.0-apple-silicon.pkg:Blockchain Node Service"
    "aitbc-coordinator-service-0.1.0-apple-silicon.pkg:Coordinator API Service"
    "aitbc-miner-service-0.1.0-apple-silicon.pkg:GPU Miner Service"
    "aitbc-marketplace-service-0.1.0-apple-silicon.pkg:Marketplace Service"
    "aitbc-explorer-service-0.1.0-apple-silicon.pkg:Blockchain Explorer Service"
    "aitbc-wallet-service-0.1.0-apple-silicon.pkg:Wallet Service"
    "aitbc-multimodal-service-0.1.0-apple-silicon.pkg:Multimodal AI Service"
    "aitbc-all-services-0.1.0-apple-silicon.pkg:Complete Service Stack"
)

echo -e "${BLUE}Available services:${NC}"
for i in "${!SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "${SERVICES[$i]}"
    echo "  $((i+1)). $description"
done

echo ""
read -p "Select services to install (e.g., 1,2,3 or all): " selection

# Parse selection
if [[ "$selection" == "all" ]]; then
    SELECTED_SERVICES=("${SERVICES[@]}")
else
    IFS=',' read -ra INDICES <<< "$selection"
    SELECTED_SERVICES=()
    for index in "${INDICES[@]}"; do
        idx=$((index-1))
        if [[ $idx -ge 0 && $idx -lt ${#SERVICES[@]} ]]; then
            SELECTED_SERVICES+=("${SERVICES[$idx]}")
        fi
    done
fi

echo ""
echo -e "${BLUE}Selected services:${NC}"
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    echo "  ✓ $description"
done

echo ""
echo -e "${YELLOW}⚠ These are demo packages for demonstration purposes.${NC}"
echo -e "${YELLOW}⚠ For full functionality, use the Python-based installation:${NC}"
echo ""
echo -e "${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash${NC}"
echo ""

read -p "Continue with installation? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# Install services
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    package_path="$SCRIPT_DIR/$package_name"
    
    if [[ -f "$package_path" ]]; then
        echo -e "${BLUE}Installing $description...${NC}"
        cd "$SCRIPT_DIR"
        tar -xzf "$package_name"
        
        if [[ -f "scripts/postinstall" ]]; then
            sudo bash scripts/postinstall
        fi
        
        # Clean up for next service
        rm -rf pkg-root scripts distribution.dist *.pkg-info 2>/dev/null || true
        
        echo -e "${GREEN}✓ $description installed${NC}"
    else
        echo -e "${YELLOW}⚠ Service package not found: $package_name${NC}"
    fi
done

echo ""
echo -e "${GREEN}🎉 Services installation completed!${NC}"
echo ""
echo "Installed services:"
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    service_executable=$(echo "$package_name" | sed 's/-0.1.0-apple-silicon.pkg//')
    if command -v "$service_executable" >/dev/null 2>&1; then
        echo "  ✓ $service_executable"
    fi
done

echo ""
echo "Configuration files:"
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    service_config=$(echo "$package_name" | sed 's/-0.1.0-apple-silicon.pkg/.yaml/')
    echo "  ~/.config/aitbc/$service_config"
done

echo ""
echo "For full AITBC CLI functionality:"
echo -e "${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash${NC}"
