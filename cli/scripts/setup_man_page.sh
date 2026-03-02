#!/bin/bash

# AITBC CLI Man Page and Completion Setup Script

set -e

echo "AITBC CLI - Setting up man page and shell completion..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install man page
echo -e "${BLUE}Installing man page...${NC}"
if [[ $EUID -eq 0 ]]; then
    # Running as root
    mkdir -p /usr/local/share/man/man1
    cp "$SCRIPT_DIR/man/aitbc.1" /usr/local/share/man/man1/
    mandb -q
    echo -e "${GREEN}✓ Man page installed system-wide${NC}"
else
    # Running as user
    mkdir -p "$HOME/.local/share/man/man1"
    cp "$SCRIPT_DIR/man/aitbc.1" "$HOME/.local/share/man/man1/"
    echo -e "${GREEN}✓ Man page installed for user${NC}"
    echo -e "${YELLOW}Note: Make sure ~/.local/share/man is in your MANPATH${NC}"
fi

# Setup shell completion
echo -e "${BLUE}Setting up shell completion...${NC}"

# Detect shell
if [[ -n "$ZSH_VERSION" ]]; then
    SHELL_RC="$HOME/.zshrc"
    echo -e "${GREEN}Detected ZSH shell${NC}"
elif [[ -n "$BASH_VERSION" ]]; then
    SHELL_RC="$HOME/.bashrc"
    echo -e "${GREEN}Detected BASH shell${NC}"
else
    echo -e "${YELLOW}Unknown shell, please manually add completion${NC}"
    exit 1
fi

# Add completion to shell rc
COMPLETION_LINE="source \"$SCRIPT_DIR/aitbc_completion.sh\""

if grep -q "aitbc_completion.sh" "$SHELL_RC" 2>/dev/null; then
    echo -e "${YELLOW}✓ Completion already configured in $SHELL_RC${NC}"
else
    echo "" >> "$SHELL_RC"
    echo "# AITBC CLI completion" >> "$SHELL_RC"
    echo "$COMPLETION_LINE" >> "$SHELL_RC"
    echo -e "${GREEN}✓ Added completion to $SHELL_RC${NC}"
fi

# Test man page
echo -e "${BLUE}Testing man page...${NC}"
if man aitbc >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Man page working: try 'man aitbc'${NC}"
else
    echo -e "${YELLOW}⚠ Man page may need manual setup${NC}"
fi

# Test completion (source in current shell)
echo -e "${BLUE}Loading completion for current session...${NC}"
source "$SCRIPT_DIR/aitbc_completion.sh"
echo -e "${GREEN}✓ Completion loaded for current session${NC}"

echo ""
echo -e "${GREEN}🎉 Setup complete!${NC}"
echo ""
echo "To use the AITBC CLI:"
echo "  1. Activate virtual environment: source $SCRIPT_DIR/venv/bin/activate"
echo "  2. Use man page: man aitbc"
echo "  3. Use tab completion: aitbc <TAB>"
echo ""
echo "Restart your shell or run 'source $SHELL_RC' to enable completion permanently."
