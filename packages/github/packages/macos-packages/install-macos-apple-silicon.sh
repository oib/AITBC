#!/bin/bash

# AITBC CLI Installer for Mac Studio (Apple Silicon)
# Merged General CLI + GPU Optimization

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
echo "║                AITBC CLI Installer                        ║"
echo "║           General CLI + GPU Optimization                  ║"
echo "║              Apple Silicon (M1/M2/M3/M4)                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}❌ This installer is for macOS only${NC}"
    exit 1
fi

# Check if running on Apple Silicon
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo -e "${RED}❌ This package is for Apple Silicon Macs only${NC}"
    echo -e "${RED}❌ Detected architecture: $ARCH${NC}"
    exit 1
fi

# Detect Apple Silicon chip family
echo -e "${BLUE}Detecting Apple Silicon chip...${NC}"
if [[ -f "/System/Library/Extensions/AppleSMC.kext/Contents/PlugIns/AppleSMCPowerManagement.kext/Contents/Info.plist" ]]; then
    CHIP_FAMILY="Apple Silicon (M1/M2/M3/M4)"
else
    CHIP_FAMILY="Apple Silicon"
fi

echo -e "${GREEN}✓ Platform: Mac Studio${NC}"
echo -e "${GREEN}✓ Architecture: $CHIP_FAMILY ($ARCH)${NC}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_FILE="aitbc-cli-0.1.0-apple-silicon.pkg"
PACKAGE_PATH="$SCRIPT_DIR/$PACKAGE_FILE"

# Check if package exists
if [[ ! -f "$PACKAGE_PATH" ]]; then
    echo -e "${RED}❌ Package not found: $PACKAGE_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}Package: $PACKAGE_FILE${NC}"
echo ""
echo -e "${YELLOW}⚠ This is a demo package for demonstration purposes.${NC}"
echo -e "${YELLOW}⚠ For full functionality, use the Python-based installation:${NC}"
echo ""
echo -e "${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash${NC}"
echo ""

read -p "Continue with demo installation? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# Verify checksums
echo -e "${BLUE}Verifying package integrity...${NC}"
cd "$SCRIPT_DIR"
if sha256sum -c checksums.txt >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Package verified${NC}"
else
    echo -e "${RED}❌ Package verification failed${NC}"
    exit 1
fi

# Extract and install demo
echo -e "${BLUE}Installing AITBC CLI (General + GPU)...${NC}"
tar -xzf "$PACKAGE_FILE"

# Run post-install script
if [[ -f "scripts/postinstall" ]]; then
    sudo bash scripts/postinstall
else
    echo -e "${YELLOW}⚠ Post-install script not found${NC}"
fi

# Test installation
echo -e "${BLUE}Testing installation...${NC}"
if command -v aitbc >/dev/null 2>&1; then
    echo -e "${GREEN}✓ AITBC CLI installed successfully${NC}"
    echo ""
    echo -e "${BLUE}Testing CLI:${NC}"
    aitbc --help
else
    echo -e "${RED}❌ Installation failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 Installation completed successfully!${NC}"
echo ""
echo "Platform: Mac Studio (Apple Silicon)"
echo "Architecture: $CHIP_FAMILY"
echo ""
echo "Quick start:"
echo "  aitbc --help"
echo "  aitbc wallet balance"
echo "  aitbc gpu optimize"
echo "  aitbc gpu benchmark"
echo ""
echo "For full AITBC CLI functionality:"
echo -e "${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash${NC}"
echo ""
echo "Configuration: ~/.config/aitbc/config.yaml"
