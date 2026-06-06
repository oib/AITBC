#!/bin/bash

# Simple macOS Package Builder for Debian 13 Trixie
# Creates placeholder .pkg files for demonstration

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║      Simple macOS Package Builder (Demo Version)           ║"
echo "║                   Creates Demo .pkg Files                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/github/packages/macos"
PKG_VERSION="0.1.0"
PKG_NAME="AITBC CLI"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Install basic tools
install_tools() {
    echo -e "${BLUE}Installing basic tools...${NC}"
    
    # Update package list
    sudo apt-get update
    
    # Install available tools
    sudo apt-get install -y \
        build-essential \
        python3 \
        python3-pip \
        python3-venv \
        python3-setuptools \
        python3-wheel \
        rsync \
        tar \
        gzip \
        openssl \
        curl \
        bc
    
    echo -e "${GREEN}✓ Basic tools installed${NC}"
}

# Create demo package structure
create_demo_package() {
    echo -e "${BLUE}Creating demo macOS package...${NC}"
    
    local temp_dir="/tmp/aitbc-macos-demo-$$"
    mkdir -p "$temp_dir"
    
    # Create package root
    mkdir -p "$temp_dir/pkg-root/usr/local/bin"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/man/man1"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/bash-completion/completions"
    
    # Create demo executable
    cat > "$temp_dir/pkg-root/usr/local/bin/aitbc" << 'EOF'
#!/bin/bash
# AITBC CLI Demo Executable
echo "AITBC CLI v0.1.0 (Demo)"
echo "This is a placeholder for the native macOS executable."
echo ""
echo "Usage: aitbc [--help] [--version] <command> [<args>]"
echo ""
echo "Commands:"
echo "  wallet     Wallet management"
echo "  blockchain Blockchain operations"
echo "  marketplace GPU marketplace"
echo "  config     Configuration management"
echo ""
echo "Full functionality will be available in the complete build."
echo ""
echo "For now, please use the Python-based installation:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/bin/aitbc"
    
    # Create demo man page
    cat > "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc.1" << 'EOF'
.TH AITBC 1 "March 2026" "AITBC CLI v0.1.0" "User Commands"
.SH NAME
aitbc \- AITBC Command Line Interface
.SH SYNOPSIS
.B aitbc
[\-\-help] [\-\-version] <command> [<args>]
.SH DESCRIPTION
AITBC CLI is the command line interface for the AITBC network,
providing access to blockchain operations, GPU marketplace,
wallet management, and more.
.SH COMMANDS
.TP
\fBwallet\fR
Wallet management operations
.TP
\fBblockchain\fR
Blockchain operations and queries
.TP
\fBmarketplace\fR
GPU marketplace operations
.TP
\fBconfig\fR
Configuration management
.SH OPTIONS
.TP
\fB\-\-help\fR
Show help message
.TP
\fB\-\-version\fR
Show version information
.SH EXAMPLES
.B aitbc wallet balance
Show wallet balance
.br
.B aitbc marketplace gpu list
List available GPUs
.SH AUTHOR
AITBC Team <team@aitbc.dev>
.SH SEE ALSO
Full documentation at https://docs.aitbc.dev
EOF
    
    # Create demo completion script
    cat > "$temp_dir/pkg-root/usr/local/share/bash-completion/completions/aitbc_completion.sh" << 'EOF'
#!/bin/bash
# AITBC CLI Bash Completion (Demo)

_aitbc_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} == 1 ]]; then
        opts="wallet blockchain marketplace config --help --version"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} == 2 ]]; then
        case ${prev} in
            wallet)
                opts="balance create import export"
                ;;
            blockchain)
                opts="status sync info"
                ;;
            marketplace)
                opts="gpu list rent offer"
                ;;
            config)
                opts="show set get"
                ;;
        esac
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    fi
    
    return 0
}

complete -F _aitbc_completion aitbc
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/share/bash-completion/completions/aitbc_completion.sh"
    
    # Create package scripts
    mkdir -p "$temp_dir/scripts"
    
    cat > "$temp_dir/scripts/postinstall" << 'EOF'
#!/bin/bash

# AITBC CLI post-install script (Demo)

echo "Installing AITBC CLI..."

# Set permissions
chmod 755 "/usr/local/bin/aitbc"

# Create symlink
ln -sf "/usr/local/bin/aitbc" "/usr/local/bin/aitbc" 2>/dev/null || true

# Add to PATH
add_to_profile() {
    local profile="$1"
    if [[ -f "$profile" ]]; then
        if ! grep -q "/usr/local/bin" "$profile"; then
            echo "" >> "$profile"
            echo "# AITBC CLI" >> "$profile"
            echo "export PATH=\"/usr/local/bin:\$PATH\"" >> "$profile"
        fi
    fi
}

add_to_profile "$HOME/.zshrc"
add_to_profile "$HOME/.bashrc"
add_to_profile "$HOME/.bash_profile"

echo "✓ AITBC CLI demo installed"
echo "Note: This is a demo package. For full functionality:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"

exit 0
EOF
    
    chmod +x "$temp_dir/scripts/postinstall"
    
    # Create distribution file
    cat > "$temp_dir/distribution.dist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<installer-gui-script minSpecVersion="1.0">
    <title>AITBC CLI (Demo)</title>
    <organization>dev.aitbc</organization>
    <domain system="true"/>
    <options customize="never" allow-external-scripts="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AITBC CLI (Demo)">
        <pkg-ref id="dev.aitbc.cli"/>
    </choice>
    <pkg-ref id="dev.aitbc.cli" version="$PKG_VERSION" onConclusion="none">$PKG_NAME.pkg</pkg-ref>
</installer-gui-script>
EOF
    
    echo -e "${GREEN}✓ Demo package structure created${NC}"
}

# Create demo .pkg file
create_demo_pkg() {
    echo -e "${BLUE}Creating demo .pkg file...${NC}"
    
    local temp_dir="/tmp/aitbc-macos-demo-$$"
    
    cd "$temp_dir"
    
    # Create a simple package (this is a demo - real .pkg requires macOS tools)
    echo "Creating demo package structure..."
    
    # Create a placeholder .pkg file (for demonstration)
    cat > "demo-package-info" << EOF
Identifier: dev.aitbc.cli
Version: $PKG_VERSION
Title: AITBC CLI (Demo)
Description: AITBC Command Line Interface Demo Package
Platform: macOS
Architecture: universal
Size: 50000000
EOF
    
    # Create demo package file
    tar -czf "$OUTPUT_DIR/aitbc-cli-$PKG_VERSION-demo.pkg" \
        pkg-root/ \
        scripts/ \
        distribution.dist \
        demo-package-info
    
    echo -e "${GREEN}✓ Demo .pkg file created${NC}"
}

# Create installer script
create_installer_script() {
    echo -e "${BLUE}Creating installer script...${NC}"
    
    cat > "$OUTPUT_DIR/install-macos-demo.sh" << EOF
#!/bin/bash

# AITBC CLI Demo Installer for macOS

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "\${BLUE}AITBC CLI Demo Installer for macOS\${NC}"
echo "=================================="

# Check if running on macOS
if [[ "\$OSTYPE" != "darwin"* ]]; then
    echo -e "\${RED}❌ This installer is for macOS only\${NC}"
    exit 1
fi

# Get script directory
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_FILE="\$SCRIPT_DIR/aitbc-cli-$PKG_VERSION-demo.pkg"

# Check if package exists
if [[ ! -f "\$PACKAGE_FILE" ]]; then
    echo -e "\${RED}❌ Demo package not found: \$PACKAGE_FILE\${NC}"
    exit 1
fi

echo -e "\${YELLOW}⚠ This is a demo package for demonstration purposes.\${NC}"
echo -e "\${YELLOW}⚠ For full functionality, use the Python-based installation:\${NC}"
echo ""
echo -e "\${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash\${NC}"
echo ""

read -p "Continue with demo installation? (y/N): " -n 1 -r
echo
if [[ ! \$REPLY =~ ^[Yy]\$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# Extract and install demo
echo -e "\${BLUE}Installing demo package...\${NC}"
cd "\$SCRIPT_DIR"
tar -xzf "aitbc-cli-$PKG_VERSION-demo.pkg"

# Run post-install script
if [[ -f "scripts/postinstall" ]]; then
    sudo bash scripts/postinstall
fi

# Test installation
echo -e "\${BLUE}Testing demo installation...\${NC}"
if command -v aitbc >/dev/null 2>&1; then
    echo -e "\${GREEN}✓ Demo AITBC CLI installed\${NC}"
    aitbc
else
    echo -e "\${RED}❌ Demo installation failed\${NC}"
    exit 1
fi

echo ""
echo -e "\${GREEN}🎉 Demo installation completed!\${NC}"
echo ""
echo "For full AITBC CLI functionality:"
echo -e "\${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash\${NC}"
EOF
    
    chmod +x "$OUTPUT_DIR/install-macos-demo.sh"
    
    echo -e "${GREEN}✓ Installer script created${NC}"
}

# Generate checksums
generate_checksums() {
    echo -e "${BLUE}Generating checksums...${NC}"
    
    cd "$OUTPUT_DIR"
    
    # Create checksums file
    cat > checksums.txt << EOF
# AITBC macOS Demo Package Checksums
# Generated on $(date)
# Algorithm: SHA256

aitbc-cli-$PKG_VERSION-demo.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-demo.pkg" | cut -d' ' -f1)
EOF
    
    echo -e "${GREEN}✓ Checksums generated${NC}"
}

# Clean up
cleanup() {
    echo -e "${BLUE}Cleaning up...${NC}"
    rm -rf "/tmp/aitbc-macos-demo-$$"
    echo -e "${GREEN}✓ Cleanup completed${NC}"
}

# Main function
main() {
    echo -e "${BLUE}Building demo macOS packages...${NC}"
    echo ""
    
    # Install tools
    install_tools
    
    # Create demo package
    create_demo_package
    
    # Create demo .pkg
    create_demo_pkg
    
    # Create installer script
    create_installer_script
    
    # Generate checksums
    generate_checksums
    
    # Clean up
    cleanup
    
    echo ""
    echo -e "${GREEN}🎉 Demo macOS package build completed!${NC}"
    echo ""
    echo "Demo package created: $OUTPUT_DIR/aitbc-cli-$PKG_VERSION-demo.pkg"
    echo "Installer script: $OUTPUT_DIR/install-macos-demo.sh"
    echo "Checksums: $OUTPUT_DIR/checksums.txt"
    echo ""
    echo -e "${YELLOW}⚠ This is a demo package for demonstration purposes.${NC}"
    echo -e "${YELLOW}⚠ For production packages, use the full build process.${NC}"
    echo ""
    echo "To install demo:"
    echo "  $OUTPUT_DIR/install-macos-demo.sh"
    echo ""
    echo "For full functionality:"
    echo "  curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"
}

# Run main function
main "$@"
