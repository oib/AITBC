#!/bin/bash

# AITBC CLI Local Package Installation Script
# This script installs the AITBC CLI from the local wheel package

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Package info
PACKAGE_NAME="aitbc-cli"
PACKAGE_VERSION="0.1.0"
WHEEL_FILE="aitbc_cli-0.1.0-py3-none-any.whl"

echo -e "${BLUE}AITBC CLI Local Package Installation${NC}"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "dist/$WHEEL_FILE" ]; then
    echo -e "${RED}Error: Package file not found: dist/$WHEEL_FILE${NC}"
    echo "Please run this script from the cli directory after building the package."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.13"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}Error: Python $REQUIRED_VERSION+ is required, found $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python version check passed ($PYTHON_VERSION)${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install the package
echo -e "${YELLOW}Installing $PACKAGE_NAME v$PACKAGE_VERSION...${NC}"
pip install --force-reinstall "dist/$WHEEL_FILE"

# Verify installation
echo -e "${YELLOW}Verifying installation...${NC}"
if command -v aitbc &> /dev/null; then
    echo -e "${GREEN}✓ AITBC CLI installed successfully!${NC}"
    echo -e "${BLUE}Installation location: $(which aitbc)${NC}"
    
    # Show version
    echo -e "${YELLOW}CLI version:${NC}"
    aitbc --version 2>/dev/null || echo -e "${YELLOW}Version check failed, but installation succeeded${NC}"
    
    # Show help
    echo -e "${YELLOW}Available commands:${NC}"
    aitbc --help 2>/dev/null | head -10 || echo -e "${YELLOW}Help command failed, but installation succeeded${NC}"
    
else
    echo -e "${RED}✗ Installation failed - aitbc command not found${NC}"
    exit 1
fi

echo -e "${GREEN}Installation completed successfully!${NC}"
echo -e "${BLUE}To use the CLI:${NC}"
echo "  1. Keep the virtual environment activated: source venv/bin/activate"
echo "  2. Or add to PATH: export PATH=\$PWD/venv/bin:\$PATH"
echo "  3. Run: aitbc --help"

# Create activation script
cat > activate_aitbc_cli.sh << 'EOF'
#!/bin/bash
# AITBC CLI activation script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
echo "AITBC CLI environment activated. Use 'aitbc --help' to get started."
EOF

chmod +x activate_aitbc_cli.sh
echo -e "${YELLOW}Created activation script: ./activate_aitbc_cli.sh${NC}"
