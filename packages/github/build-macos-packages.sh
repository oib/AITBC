#!/bin/bash

# Build Native macOS Packages from Debian 13 Trixie
# Cross-compilation setup for Mac Studio native .pkg packages

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║      Build Native macOS Packages from Debian 13 Trixie       ║"
echo "║                   Mac Studio Compatible                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build-macos"
OUTPUT_DIR="$SCRIPT_DIR/github/packages/macos"
SOURCE_DIR="$SCRIPT_DIR/../cli"

# macOS package configuration
PKG_VERSION="0.1.0"
PKG_IDENTIFIER="dev.aitbc.cli"
PKG_INSTALL_LOCATION="/usr/local"
PKG_NAME="AITBC CLI"

# Check if running on Debian
if [[ ! -f /etc/debian_version ]]; then
    echo -e "${RED}❌ This script must be run on Debian 13 Trixie${NC}"
    exit 1
fi

# Check Debian version
DEBIAN_VERSION=$(cat /etc/debian_version)
if [[ ! "$DEBIAN_VERSION" =~ ^13 ]]; then
    echo -e "${YELLOW}⚠ This script is optimized for Debian 13 Trixie${NC}"
    echo "Current version: $DEBIAN_VERSION"
fi

# Install required tools
install_build_tools() {
    echo -e "${BLUE}Installing build tools...${NC}"
    
    # Update package list
    sudo apt-get update
    
    # Install basic build tools
    sudo apt-get install -y \
        build-essential \
        python3.13 \
        python3.13-venv \
        python3.13-pip \
        python3.13-dev \
        python3-setuptools \
        python3-wheel \
        rsync \
        tar \
        gzip
    
    # Install macOS packaging tools
    sudo apt-get install -y \
        xar \
        cpio \
        openssl \
        python3-cryptography
    
    echo -e "${GREEN}✓ Build tools installed${NC}"
}

# Create build directory
setup_build_environment() {
    echo -e "${BLUE}Setting up build environment...${NC}"
    
    # Clean and create directories
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
    mkdir -p "$OUTPUT_DIR"
    
    # Create package structure
    mkdir -p "$BUILD_DIR/pkg-root/$PKG_INSTALL_LOCATION/bin"
    mkdir -p "$BUILD_DIR/pkg-root/$PKG_INSTALL_LOCATION/aitbc"
    mkdir -p "$BUILD_DIR/pkg-root/$PKG_INSTALL_LOCATION/share/man/man1"
    mkdir -p "$BUILD_DIR/pkg-root/$PKG_INSTALL_LOCATION/share/bash-completion/completions"
    mkdir -p "$BUILD_DIR/pkg-root/Library/LaunchDaemons"
    mkdir -p "$BUILD_DIR/scripts"
    mkdir -p "$BUILD_DIR/resources"
    
    echo -e "${GREEN}✓ Build environment ready${NC}"
}

# Build CLI package
build_cli_package() {
    echo -e "${BLUE}Building CLI package...${NC}"
    
    # Create virtual environment for building
    cd "$BUILD_DIR"
    python3.13 -m venv build-env
    source build-env/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    
    # Install build dependencies
    pip install pyinstaller
    
    # Copy source code
    if [[ -d "$SOURCE_DIR" ]]; then
        cp -r "$SOURCE_DIR" "$BUILD_DIR/cli-source"
        cd "$BUILD_DIR/cli-source"
    else
        echo -e "${RED}❌ CLI source directory not found: $SOURCE_DIR${NC}"
        exit 1
    fi
    
    # Install dependencies
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
    fi
    
    # Install CLI in development mode
    pip install -e .
    
    # Create standalone executable with PyInstaller
    echo -e "${BLUE}Creating standalone executable...${NC}"
    
    cat > aitbc.spec << 'EOF'
# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

a = Analysis(
    ['aitbc_cli/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('aitbc_cli/commands', 'aitbc_cli/commands'),
        ('aitbc_cli/core', 'aitbc_cli/core'),
        ('aitbc_cli/config', 'aitbc_cli/config'),
        ('aitbc_cli/auth', 'aitbc_cli/auth'),
        ('aitbc_cli/utils', 'aitbc_cli/utils'),
        ('aitbc_cli/models', 'aitbc_cli/models'),
    ],
    hiddenimports=[
        'click',
        'click_completion',
        'pydantic',
        'httpx',
        'cryptography',
        'keyring',
        'rich',
        'yaml',
        'tabulate',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='aitbc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
EOF
    
    # Build executable
    pyinstaller aitbc.spec --clean --noconfirm
    
    # Copy executable to package root
    cp dist/aitbc "$BUILD_DIR/pkg-root/$PKG_INSTALL_LOCATION/bin/"
    
    # Copy additional files
    if [[ -f "../cli/man/aitbc.1" ]]; then
        cp ../cli/man/aitbc.1 "$BUILD_DIR/pkg-root/$PKG_INSTALL_LOCATION/share/man/man1/"
    fi
    
    if [[ -f "../cli/aitbc_completion.sh" ]]; then
        cp ../cli/aitbc_completion.sh "$BUILD_DIR/pkg-root/$PKG_INSTALL_LOCATION/share/bash-completion/completions/"
    fi
    
    echo -e "${GREEN}✓ CLI package built${NC}"
}

# Create macOS package scripts
create_package_scripts() {
    echo -e "${BLUE}Creating package scripts...${NC}"
    
    # Pre-install script
    cat > "$BUILD_DIR/scripts/preinstall" << 'EOF'
#!/bin/bash

# AITBC CLI pre-install script for macOS

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "This package is for macOS only"
    exit 1
fi

# Check Python version
if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [[ $(echo "$PYTHON_VERSION >= 3.8" | bc -l) -eq 1 ]]; then
        echo "✓ Python $PYTHON_VERSION found"
    else
        echo "⚠ Python $PYTHON_VERSION found, 3.8+ recommended"
    fi
else
    echo "⚠ Python not found, please install Python 3.8+"
fi

# Create installation directory if needed
if [[ ! -d "/usr/local/aitbc" ]]; then
    mkdir -p "/usr/local/aitbc"
fi

exit 0
EOF
    
    # Post-install script
    cat > "$BUILD_DIR/scripts/postinstall" << 'EOF'
#!/bin/bash

# AITBC CLI post-install script for macOS

# Set permissions
chmod 755 "/usr/local/bin/aitbc"

# Create symlink if it doesn't exist
if [[ ! -L "/usr/local/bin/aitbc" ]]; then
    ln -sf "/usr/local/aitbc/bin/aitbc" "/usr/local/bin/aitbc"
fi

# Add to PATH in shell profiles
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

# Add to common shell profiles
add_to_profile "$HOME/.zshrc"
add_to_profile "$HOME/.bashrc"
add_to_profile "$HOME/.bash_profile"

# Install man page
if [[ -f "/usr/local/aitbc/share/man/man1/aitbc.1" ]]; then
    gzip -c "/usr/local/aitbc/share/man/man1/aitbc.1" > "/usr/local/share/man/man1/aitbc.1.gz" 2>/dev/null || true
fi

# Install bash completion
if [[ -f "/usr/local/aitbc/share/bash-completion/completions/aitbc_completion.sh" ]]; then
    mkdir -p "/usr/local/etc/bash_completion.d"
    ln -sf "/usr/local/aitbc/share/bash-completion/completions/aitbc_completion.sh" "/usr/local/etc/bash_completion.d/aitbc"
fi

echo "✓ AITBC CLI installed successfully"
echo "Run 'aitbc --help' to get started"

exit 0
EOF
    
    # Pre-uninstall script
    cat > "$BUILD_DIR/scripts/preuninstall" << 'EOF'
#!/bin/bash

# AITBC CLI pre-uninstall script for macOS

# Stop any running processes
pkill -f aitbc || true

# Remove symlink
if [[ -L "/usr/local/bin/aitbc" ]]; then
    rm -f "/usr/local/bin/aitbc"
fi

exit 0
EOF
    
    # Post-uninstall script
    cat > "$BUILD_DIR/scripts/postuninstall" << 'EOF'
#!/bin/bash

# AITBC CLI post-uninstall script for macOS

# Remove installation directory
if [[ -d "/usr/local/aitbc" ]]; then
    rm -rf "/usr/local/aitbc"
fi

# Remove man page
if [[ -f "/usr/local/share/man/man1/aitbc.1.gz" ]]; then
    rm -f "/usr/local/share/man/man1/aitbc.1.gz"
fi

# Remove bash completion
if [[ -f "/usr/local/etc/bash_completion.d/aitbc" ]]; then
    rm -f "/usr/local/etc/bash_completion.d/aitbc"
fi

echo "✓ AITBC CLI uninstalled successfully"

exit 0
EOF
    
    # Make scripts executable
    chmod +x "$BUILD_DIR/scripts"/*
    
    echo -e "${GREEN}✓ Package scripts created${NC}"
}

# Create package distribution file
create_distribution_file() {
    echo -e "${BLUE}Creating distribution file...${NC}"
    
    cat > "$BUILD_DIR/distribution.dist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<installer-gui-script minSpecVersion="1.0">
    <title>AITBC CLI</title>
    <organization>dev.aitbc</organization>
    <domain system="true"/>
    <options customize="never" allow-external-scripts="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AITBC CLI">
        <pkg-ref id="dev.aitbc.cli"/>
    </choice>
    <pkg-ref id="dev.aitbc.cli" version="$PKG_VERSION" onConclusion="none">$PKG_NAME.pkg</pkg-ref>
</installer-gui-script>
EOF
    
    echo -e "${GREEN}✓ Distribution file created${NC}"
}

# Build macOS package
build_macos_package() {
    echo -e "${BLUE}Building macOS package...${NC}"
    
    cd "$BUILD_DIR"
    
    # Create package component
    pkgbuild \
        --root "pkg-root" \
        --identifier "$PKG_IDENTIFIER" \
        --version "$PKG_VERSION" \
        --install-location "$PKG_INSTALL_LOCATION" \
        --scripts "scripts" \
        --ownership "recommended" \
        "$PKG_NAME.pkg"
    
    # Create product archive
    productbuild \
        --distribution "distribution.dist" \
        --package-path "." \
        --resources "resources" \
        --version "$PKG_VERSION" \
        "$OUTPUT_DIR/aitbc-cli-$PKG_VERSION.pkg"
    
    echo -e "${GREEN}✓ macOS package built: $OUTPUT_DIR/aitbc-cli-$PKG_VERSION.pkg${NC}"
}

# Create additional resources
create_resources() {
    echo -e "${BLUE}Creating package resources...${NC}"
    
    # Create license file
    cat > "$BUILD_DIR/resources/License.txt" << 'EOF'
MIT License

Copyright (c) 2026 AITBC Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
    
    # Create welcome text
    cat > "$BUILD_DIR/resources/Welcome.txt" << 'EOF'
AITBC CLI - Command Line Interface for AITBC Network

This package installs the AITBC CLI on your macOS system.

Features:
• Complete CLI functionality
• 22 command groups with 100+ subcommands
• Wallet management
• Blockchain operations
• GPU marketplace access
• Multi-chain support
• Shell completion
• Man page documentation

After installation, run 'aitbc --help' to get started.

For more information, visit: https://docs.aitbc.dev
EOF
    
    # Create conclusion text
    cat > "$BUILD_DIR/resources/Conclusion.txt" << 'EOF'
Installation Complete!

The AITBC CLI has been successfully installed on your system.

To get started:
1. Open a new terminal window
2. Run: aitbc --help
3. Configure: aitbc config set api_key your_key

Documentation: https://docs.aitbc.dev
Community: https://community.aitbc.dev
Issues: https://github.com/aitbc/aitbc/issues

Thank you for installing AITBC CLI!
EOF
    
    echo -e "${GREEN}✓ Package resources created${NC}"
}

# Generate checksums
generate_checksums() {
    echo -e "${BLUE}Generating checksums...${NC}"
    
    cd "$OUTPUT_DIR"
    
    # Create checksums file
    cat > checksums.txt << EOF
# AITBC macOS Package Checksums
# Generated on $(date)
# Algorithm: SHA256

aitbc-cli-$PKG_VERSION.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION.pkg" | cut -d' ' -f1)
EOF
    
    echo -e "${GREEN}✓ Checksums generated${NC}"
}

# Verify package
verify_package() {
    echo -e "${BLUE}Verifying package...${NC}"
    
    local package_file="$OUTPUT_DIR/aitbc-cli-$PKG_VERSION.pkg"
    
    if [[ -f "$package_file" ]]; then
        # Check package size
        local size=$(du -h "$package_file" | cut -f1)
        echo -e "${GREEN}✓ Package size: $size${NC}"
        
        # Verify package structure
        if xar -tf "$package_file" | grep -q "Distribution"; then
            echo -e "${GREEN}✓ Package structure valid${NC}"
        else
            echo -e "${RED}❌ Package structure invalid${NC}"
            return 1
        fi
        
        # Check checksums
        if sha256sum -c checksums.txt >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Checksums verified${NC}"
        else
            echo -e "${RED}❌ Checksum verification failed${NC}"
            return 1
        fi
    else
        echo -e "${RED}❌ Package file not found${NC}"
        return 1
    fi
}

# Create installation script for macOS
create_installer_script() {
    echo -e "${BLUE}Creating macOS installer script...${NC}"
    
    cat > "$OUTPUT_DIR/install-macos-native.sh" << EOF
#!/bin/bash

# AITBC CLI Native macOS Installer
# Built from Debian 13 Trixie

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "\${BLUE}AITBC CLI Native macOS Installer\${NC}"
echo "=================================="

# Check if running on macOS
if [[ "\$OSTYPE" != "darwin"* ]]; then
    echo -e "\${RED}❌ This installer is for macOS only\${NC}"
    exit 1
fi

# Get script directory
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_FILE="\$SCRIPT_DIR/aitbc-cli-$PKG_VERSION.pkg"

# Check if package exists
if [[ ! -f "\$PACKAGE_FILE" ]]; then
    echo -e "\${RED}❌ Package not found: \$PACKAGE_FILE\${NC}"
    exit 1
fi

# Verify checksums
if [[ -f "\$SCRIPT_DIR/checksums.txt" ]]; then
    echo -e "\${BLUE}Verifying package integrity...\${NC}"
    cd "\$SCRIPT_DIR"
    if sha256sum -c checksums.txt >/dev/null 2>&1; then
        echo -e "\${GREEN}✓ Package verified\${NC}"
    else
        echo -e "\${RED}❌ Package verification failed\${NC}"
        exit 1
    fi
fi

# Install package
echo -e "\${BLUE}Installing AITBC CLI...\${NC}"
sudo installer -pkg "\$PACKAGE_FILE" -target /

# Test installation
echo -e "\${BLUE}Testing installation...\${NC}"
if command -v aitbc >/dev/null 2>&1; then
    echo -e "\${GREEN}✓ AITBC CLI installed successfully\${NC}"
    
    if aitbc --version >/dev/null 2>&1; then
        VERSION=\$(aitbc --version 2>/dev/null | head -1)
        echo -e "\${GREEN}✓ \$VERSION\${NC}"
    fi
    
    echo ""
    echo -e "\${GREEN}🎉 Installation completed!\${NC}"
    echo ""
    echo "Quick start:"
    echo "  aitbc --help"
    echo "  aitbc wallet balance"
    echo ""
    echo "Documentation: https://docs.aitbc.dev"
else
    echo -e "\${RED}❌ Installation failed\${NC}"
    exit 1
fi
EOF
    
    chmod +x "$OUTPUT_DIR/install-macos-native.sh"
    
    echo -e "${GREEN}✓ Installer script created${NC}"
}

# Main build function
main() {
    echo -e "${BLUE}Starting macOS package build from Debian 13 Trixie...${NC}"
    echo ""
    
    # Install build tools
    install_build_tools
    
    # Setup build environment
    setup_build_environment
    
    # Build CLI package
    build_cli_package
    
    # Create package scripts
    create_package_scripts
    
    # Create resources
    create_resources
    
    # Create distribution file
    create_distribution_file
    
    # Build macOS package
    build_macos_package
    
    # Generate checksums
    generate_checksums
    
    # Verify package
    verify_package
    
    # Create installer script
    create_installer_script
    
    echo ""
    echo -e "${GREEN}🎉 macOS package build completed successfully!${NC}"
    echo ""
    echo "Package created: $OUTPUT_DIR/aitbc-cli-$PKG_VERSION.pkg"
    echo "Installer script: $OUTPUT_DIR/install-macos-native.sh"
    echo "Checksums: $OUTPUT_DIR/checksums.txt"
    echo ""
    echo "To install on macOS:"
    echo "  curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos/install-macos-native.sh | bash"
    echo ""
    echo "Or download and run:"
    echo "  scp $OUTPUT_DIR/aitbc-cli-$PKG_VERSION.pkg user@mac-mini:/tmp/"
    echo "  ssh user@mac-mini 'sudo installer -pkg /tmp/aitbc-cli-$PKG_VERSION.pkg -target /'"
}

# Run main function
main "$@"
