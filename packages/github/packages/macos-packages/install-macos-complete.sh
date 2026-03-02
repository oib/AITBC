#!/bin/bash

# AITBC CLI Complete Installer for Mac Studio (Apple Silicon)
# Installs all available packages

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              AITBC CLI Complete Installer                  ║"
echo "║                 Mac Studio (Apple Silicon)                 ║"
echo "║                    All Packages                             ║"
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

# Available packages
PACKAGES=(
    "aitbc-cli-0.1.0-apple-silicon.pkg:Main CLI Package"
    "aitbc-cli-dev-0.1.0-apple-silicon.pkg:Development Tools"
    "aitbc-cli-gpu-0.1.0-apple-silicon.pkg:GPU Optimization"
)

echo -e "${BLUE}Available packages:${NC}"
for i in "${!PACKAGES[@]}"; do
    IFS=':' read -r package_name description <<< "${PACKAGES[]}"
    echo "  $((i+1)). $description"
done

echo ""
read -p "Select packages to install (e.g., 1,2,3 or all): " selection

# Parse selection
if [[ "$selection" == "all" ]]; then
    SELECTED_PACKAGES=("${PACKAGES[@]}")
else
    IFS=',' read -ra INDICES <<< "$selection"
    SELECTED_PACKAGES=()
    for index in "${INDICES[@]}"; do
        idx=$((index-1))
        if [[ $idx -ge 0 && $idx -lt ${#PACKAGES[@]} ]]; then
            SELECTED_PACKAGES+=("${PACKAGES[$idx]}")
        fi
    done
fi

echo ""
echo -e "${BLUE}Selected packages:${NC}"
for package in "${SELECTED_PACKAGES[@]}"; do
    IFS=':' read -r package_name description <<< "$package"
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

# Install packages
for package in "${SELECTED_PACKAGES[@]}"; do
    IFS=':' read -r package_name description <<< "$package"
    package_path="$SCRIPT_DIR/$package_name"
    
    if [[ -f "$package_path" ]]; then
        echo -e "${BLUE}Installing $description...${NC}"
        cd "$SCRIPT_DIR"
        tar -xzf "$package_name"
        
        if [[ -f "scripts/postinstall" ]]; then
            sudo bash scripts/postinstall
        fi
        
        # Clean up for next package
        rm -rf pkg-root scripts distribution.dist *.pkg-info 2>/dev/null || true
        
        echo -e "${GREEN}✓ $description installed${NC}"
    else
        echo -e "${YELLOW}⚠ Package not found: $package_name${NC}"
    fi
done

# Test installation
echo -e "${BLUE}Testing installation...${NC}"
if command -v aitbc >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Main CLI available${NC}"
fi

if command -v aitbc-dev >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Development CLI available${NC}"
fi

if command -v aitbc-gpu >/dev/null 2>&1; then
    echo -e "${GREEN}✓ GPU CLI available${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Complete installation finished!${NC}"
echo ""
echo "Installed commands:"
if command -v aitbc >/dev/null 2>&1; then
    echo "  aitbc        - Main CLI"
fi
if command -v aitbc-dev >/dev/null 2>&1; then
    echo "  aitbc-dev    - Development CLI"
fi
if command -v aitbc-gpu >/dev/null 2>&1; then
    echo "  aitbc-gpu    - GPU Optimization CLI"
fi

echo ""
echo "Configuration files:"
echo "  ~/.config/aitbc/config.yaml"
echo "  ~/.config/aitbc/dev-config.yaml"
echo "  ~/.config/aitbc/gpu-config.yaml"

echo ""
echo "For full AITBC CLI functionality:"
echo -e "${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash${NC}"
