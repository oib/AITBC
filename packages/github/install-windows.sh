#!/bin/bash

# AITBC CLI & Services Windows/WSL2 Installer
# For Windows 10/11 with WSL2

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}AITBC Windows/WSL2 Installer${NC}"
echo "============================="

# Check if running on Windows
if [[ "$OSTYPE" != "msys" ]] && [[ "$OSTYPE" != "cygwin" ]]; then
    echo -e "${RED}❌ This installer is for Windows/WSL2 only${NC}"
    echo "Please run this from Windows Command Prompt, PowerShell, or Git Bash"
    exit 1
fi

# Check WSL
if command -v wsl >/dev/null 2>&1; then
    echo -e "${GREEN}✓ WSL found${NC}"
else
    echo -e "${RED}❌ WSL not found${NC}"
    echo "Please install WSL2 first:"
    echo "1. Open PowerShell as Administrator"
    echo "2. Run: wsl --install"
    echo "3. Restart Windows"
    echo "4. Run: wsl --install -d Debian"
    exit 1
fi

# Check if Debian is installed in WSL
if wsl --list --verbose | grep -q "Debian"; then
    echo -e "${GREEN}✓ Debian found in WSL${NC}"
else
    echo -e "${YELLOW}⚠ Debian not found in WSL, installing...${NC}"
    wsl --install -d Debian
    
    echo -e "${YELLOW}Please wait for Debian installation to complete, then run this script again.${NC}"
    exit 0
fi

# Get current user and script path
CURRENT_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WSL_SCRIPT_DIR="/mnt/c/Users/$CURRENT_USER/aitbc/packages/github"

# Copy packages to WSL
echo -e "${BLUE}Copying packages to WSL...${NC}"
wsl -d Debian -e "mkdir -p $WSL_SCRIPT_DIR"

# Copy all files to WSL
cp -r "$SCRIPT_DIR"/* "/mnt/c/Users/$CURRENT_USER/aitbc/packages/github/"

# Run installation in WSL
echo -e "${BLUE}Installing AITBC CLI in WSL...${NC}"
wsl -d Debian -e "
cd $WSL_SCRIPT_DIR
chmod +x install.sh
./install.sh --cli-only
"

# Create Windows shortcut
echo -e "${BLUE}Creating Windows shortcut...${NC}"

# Create batch file for easy access
cat > "$SCRIPT_DIR/aitbc-wsl.bat" << 'EOF'
@echo off
wsl -d Debian -e "cd /mnt/c/Users/%USERNAME%/aitbc/packages/github && source /usr/local/bin/activate && aitbc %*"
EOF

# Create PowerShell profile function
echo -e "${BLUE}Creating PowerShell function...${NC}"
POWERSHELL_PROFILE="$HOME/Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1"

if [[ ! -f "$POWERSHELL_PROFILE" ]]; then
    mkdir -p "$(dirname "$POWERSHELL_PROFILE")"
    touch "$POWERSHELL_PROFILE"
fi

if ! grep -q "function aitbc" "$POWERSHELL_PROFILE"; then
    cat >> "$POWERSHELL_PROFILE" << 'EOF'

# AITBC CLI function
function aitbc {
    wsl -d Debian -e "cd /mnt/c/Users/$env:USERNAME/aitbc/packages/github && source /usr/local/bin/activate && aitbc $args"
}
EOF
    echo -e "${GREEN}✓ PowerShell function added${NC}"
fi

# Test installation
echo -e "${BLUE}Testing installation...${NC}"
if wsl -d Debian -e "command -v aitbc" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ AITBC CLI installed in WSL${NC}"
    
    if wsl -d Debian -e "aitbc --version" >/dev/null 2>&1; then
        VERSION=$(wsl -d Debian -e "aitbc --version" 2>/dev/null | head -1)
        echo -e "${GREEN}✓ $VERSION${NC}"
    else
        echo -e "${YELLOW}⚠ CLI installed but version check failed${NC}"
    fi
else
    echo -e "${RED}❌ CLI installation failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 AITBC CLI installation completed on Windows/WSL2!${NC}"
echo ""
echo "Usage options:"
echo ""
echo "1. PowerShell (recommended):"
echo "   Open PowerShell and run: aitbc --help"
echo ""
echo "2. Command Prompt:"
echo "   Run: $SCRIPT_DIR/aitbc-wsl.bat --help"
echo ""
echo "3. WSL directly:"
echo "   wsl -d Debian -e 'aitbc --help'"
echo ""
echo "4. Git Bash:"
echo "   wsl -d Debian -e 'cd /mnt/c/Users/$CURRENT_USER/aitbc/packages/github && source /usr/local/bin/activate && aitbc --help'"
echo ""
echo "Installation location in WSL: /usr/local/aitbc/"
echo "Packages location: $SCRIPT_DIR/"
echo ""
echo "Note: Services are available in WSL but require Linux configuration."
echo "Use 'wsl -d Debian' to access the Linux environment for service management."
