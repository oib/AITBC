#!/bin/bash

# AITBC CLI & Services macOS Installer
# Supports Intel and Apple Silicon Macs

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}AITBC macOS Installer${NC}"
echo "====================="

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}❌ This installer is for macOS only${NC}"
    exit 1
fi

# Check architecture
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    echo -e "${GREEN}✓ Apple Silicon Mac detected${NC}"
elif [[ "$ARCH" == "x86_64" ]]; then
    echo -e "${GREEN}✓ Intel Mac detected${NC}"
else
    echo -e "${RED}❌ Unsupported architecture: $ARCH${NC}"
    exit 1
fi

# Check Homebrew
if command -v brew >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Homebrew found${NC}"
else
    echo -e "${YELLOW}⚠ Homebrew not found, installing...${NC}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for Apple Silicon
    if [[ "$ARCH" == "arm64" ]]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

# Install Python 3.13
if command -v python3.13 >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Python 3.13 found${NC}"
else
    echo -e "${YELLOW}⚠ Installing Python 3.13...${NC}"
    brew install python@3.13
fi

# Create installation directory
INSTALL_DIR="/usr/local/aitbc"
sudo mkdir -p "$INSTALL_DIR"

# Create virtual environment
echo -e "${BLUE}Creating virtual environment...${NC}"
sudo python3.13 -m venv "$INSTALL_DIR/venv"

# Activate virtual environment and install CLI
echo -e "${BLUE}Installing AITBC CLI...${NC}"
sudo "$INSTALL_DIR/venv/bin/pip" install --upgrade pip

# Install from wheel if available, otherwise from source
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/packages/aitbc-cli_0.1.0-py3-none-any.whl" ]]; then
    sudo "$INSTALL_DIR/venv/bin/pip" install "$SCRIPT_DIR/packages/aitbc-cli_0.1.0-py3-none-any.whl"
else
    sudo "$INSTALL_DIR/venv/bin/pip" install git+https://github.com/aitbc/aitbc.git#subdirectory=cli
fi

# Create symlink
sudo ln -sf "$INSTALL_DIR/venv/bin/aitbc" /usr/local/bin/aitbc

# Install shell completion
echo -e "${BLUE}Installing shell completion...${NC}"
COMPLETION_DIR="$INSTALL_DIR/completion"
sudo mkdir -p "$COMPLETION_DIR"

# Copy completion script
if [[ -f "$SCRIPT_DIR/../cli/aitbc_completion.sh" ]]; then
    sudo cp "$SCRIPT_DIR/../cli/aitbc_completion.sh" "$COMPLETION_DIR/"
    sudo chmod +x "$COMPLETION_DIR/aitbc_completion.sh"
fi

# Add to shell profile
SHELL_PROFILE=""
if [[ -f ~/.zshrc ]]; then
    SHELL_PROFILE=~/.zshrc
elif [[ -f ~/.bashrc ]]; then
    SHELL_PROFILE=~/.bashrc
elif [[ -f ~/.bash_profile ]]; then
    SHELL_PROFILE=~/.bash_profile
fi

if [[ -n "$SHELL_PROFILE" ]]; then
    if ! grep -q "aitbc_completion.sh" "$SHELL_PROFILE"; then
        echo "" >> "$SHELL_PROFILE"
        echo "# AITBC CLI completion" >> "$SHELL_PROFILE"
        echo "source $COMPLETION_DIR/aitbc_completion.sh" >> "$SHELL_PROFILE"
        echo -e "${GREEN}✓ Shell completion added to $SHELL_PROFILE${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Could not find shell profile. Add this manually:${NC}"
    echo "source $COMPLETION_DIR/aitbc_completion.sh"
fi

# Create configuration directory
CONFIG_DIR="$HOME/.config/aitbc"
mkdir -p "$CONFIG_DIR"

# Create default config
if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
    cat > "$CONFIG_DIR/config.yaml" << 'EOF'
# AITBC CLI Configuration
coordinator_url: http://localhost:8000
api_key: null
output_format: table
timeout: 30
log_level: INFO
default_wallet: default
wallet_dir: ~/.aitbc/wallets
chain_id: mainnet
default_region: localhost
analytics_enabled: true
verify_ssl: true
EOF
    echo -e "${GREEN}✓ Default configuration created${NC}"
fi

# Test installation
echo -e "${BLUE}Testing installation...${NC}"
if command -v aitbc >/dev/null 2>&1; then
    echo -e "${GREEN}✓ AITBC CLI installed successfully${NC}"
    
    if aitbc --version >/dev/null 2>&1; then
        VERSION=$(aitbc --version 2>/dev/null | head -1)
        echo -e "${GREEN}✓ $VERSION${NC}"
    else
        echo -e "${YELLOW}⚠ CLI installed but version check failed${NC}"
    fi
    
    if aitbc --help >/dev/null 2>&1; then
        echo -e "${GREEN}✓ CLI help working${NC}"
    else
        echo -e "${YELLOW}⚠ CLI help failed${NC}"
    fi
else
    echo -e "${RED}❌ CLI installation failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 AITBC CLI installation completed on macOS!${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart your terminal or run: source $SHELL_PROFILE"
echo "  2. Test CLI: aitbc --help"
echo "  3. Configure: aitbc config set api_key your_key"
echo ""
echo "Installation location: $INSTALL_DIR"
echo "Configuration: $CONFIG_DIR/config.yaml"
echo ""
echo "Note: Services are not supported on macOS. Use Linux for full functionality."
