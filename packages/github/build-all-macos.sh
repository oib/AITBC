#!/bin/bash

# Build All macOS Packages (Demo Versions)
# Creates packages for Intel, Apple Silicon, and Universal

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
echo "║          Build All macOS Packages (Demo Versions)           ║"
echo "║              Intel + Apple Silicon + Universal              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/packages/macos-packages"
PKG_VERSION="0.1.0"
PKG_NAME="AITBC CLI"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Install basic tools (if needed)
install_tools() {
    echo -e "${BLUE}Ensuring tools are available...${NC}"
    
    # Check if basic tools are available
    if ! command -v tar >/dev/null 2>&1; then
        echo -e "${YELLOW}Installing basic tools...${NC}"
        sudo apt-get update
        sudo apt-get install -y tar gzip openssl curl bc
    fi
    
    echo -e "${GREEN}✓ Tools ready${NC}"
}

# Create architecture-specific package
create_arch_package() {
    local arch="$1"
    local arch_name="$2"
    
    echo -e "${BLUE}Creating $arch_name package...${NC}"
    
    local temp_dir="/tmp/aitbc-macos-$arch-$$"
    mkdir -p "$temp_dir"
    
    # Create package root
    mkdir -p "$temp_dir/pkg-root/usr/local/bin"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/man/man1"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/bash-completion/completions"
    
    # Create architecture-specific executable
    cat > "$temp_dir/pkg-root/usr/local/bin/aitbc" << EOF
#!/bin/bash
# AITBC CLI Demo Executable - $arch_name
echo "AITBC CLI v$PKG_VERSION ($arch_name Demo)"
echo "Architecture: $arch_name"
echo ""
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
    cat > "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc.1" << EOF
.TH AITBC 1 "March 2026" "AITBC CLI v$PKG_VERSION" "User Commands"
.SH NAME
aitbc \- AITBC Command Line Interface ($arch_name)
.SH SYNOPSIS
.B aitbc
[\-\-help] [\-\-version] <command> [<args>]
.SH DESCRIPTION
AITBC CLI is the command line interface for the AITBC network,
providing access to blockchain operations, GPU marketplace,
wallet management, and more.
.PP
This is the $arch_name version for macOS.
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
    
    cat > "$temp_dir/scripts/postinstall" << EOF
#!/bin/bash

# AITBC CLI post-install script ($arch_name Demo)

echo "Installing AITBC CLI for $arch_name..."

# Set permissions
chmod 755 "/usr/local/bin/aitbc"

# Create symlink
ln -sf "/usr/local/bin/aitbc" "/usr/local/bin/aitbc" 2>/dev/null || true

# Add to PATH
add_to_profile() {
    local profile="\$1"
    if [[ -f "\$profile" ]]; then
        if ! grep -q "/usr/local/bin" "\$profile"; then
            echo "" >> "\$profile"
            echo "# AITBC CLI" >> "\$profile"
            echo "export PATH=\"/usr/local/bin:\\\$PATH\"" >> "\$profile"
        fi
    fi
}

add_to_profile "\$HOME/.zshrc"
add_to_profile "\$HOME/.bashrc"
add_to_profile "\$HOME/.bash_profile"

echo "✓ AITBC CLI $arch_name demo installed"
echo "Note: This is a demo package. For full functionality:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"

exit 0
EOF
    
    chmod +x "$temp_dir/scripts/postinstall"
    
    # Create distribution file
    cat > "$temp_dir/distribution.dist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<installer-gui-script minSpecVersion="1.0">
    <title>AITBC CLI ($arch_name Demo)</title>
    <organization>dev.aitbc</organization>
    <domain system="true"/>
    <options customize="never" allow-external-scripts="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AITBC CLI ($arch_name Demo)">
        <pkg-ref id="dev.aitbc.cli"/>
    </choice>
    <pkg-ref id="dev.aitbc.cli" version="$PKG_VERSION" onConclusion="none">$PKG_NAME.pkg</pkg-ref>
</installer-gui-script>
EOF
    
    echo -e "${GREEN}✓ $arch_name package structure created${NC}"
    
    # Create package file
    cd "$temp_dir"
    
    # Create demo package file
    cat > "$arch-package-info" << EOF
Identifier: dev.aitbc.cli
Version: $PKG_VERSION
Title: AITBC CLI ($arch_name Demo)
Description: AITBC Command Line Interface Demo Package for $arch_name
Platform: macOS
Architecture: $arch
Size: 50000000
EOF
    
    # Create demo package file
    tar -czf "$OUTPUT_DIR/aitbc-cli-$PKG_VERSION-$arch.pkg" \
        pkg-root/ \
        scripts/ \
        distribution.dist \
        "$arch-package-info"
    
    echo -e "${GREEN}✓ $arch_name .pkg file created${NC}"
    
    # Clean up
    rm -rf "$temp_dir"
}

# Create universal package
create_universal_package() {
    echo -e "${BLUE}Creating Universal package...${NC}"
    
    local temp_dir="/tmp/aitbc-macos-universal-$$"
    mkdir -p "$temp_dir"
    
    # Create package root
    mkdir -p "$temp_dir/pkg-root/usr/local/bin"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/man/man1"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/bash-completion/completions"
    
    # Create universal executable (detects architecture)
    cat > "$temp_dir/pkg-root/usr/local/bin/aitbc" << 'EOF'
#!/bin/bash
# AITBC CLI Demo Executable - Universal
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    ARCH_NAME="Apple Silicon"
elif [[ "$ARCH" == "x86_64" ]]; then
    ARCH_NAME="Intel"
else
    ARCH_NAME="Unknown"
fi

echo "AITBC CLI v0.1.0 (Universal Demo)"
echo "Detected Architecture: $ARCH_NAME ($ARCH)"
echo ""
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
    
    # Copy man page and completion from previous build
    if [[ -f "$OUTPUT_DIR/../macos-packages/aitbc-cli-0.1.0-demo.pkg" ]]; then
        # Extract from existing demo package
        cd /tmp
        mkdir -p extract_demo
        cd extract_demo
        tar -xzf "$OUTPUT_DIR/../macos-packages/aitbc-cli-0.1.0-demo.pkg"
        
        if [[ -d "pkg-root" ]]; then
            cp -r pkg-root/usr/local/share/* "$temp_dir/pkg-root/usr/local/share/"
        fi
        
        cd /tmp
        rm -rf extract_demo
    fi
    
    # Create package scripts
    mkdir -p "$temp_dir/scripts"
    
    cat > "$temp_dir/scripts/postinstall" << 'EOF'
#!/bin/bash

# AITBC CLI post-install script (Universal Demo)

echo "Installing AITBC CLI (Universal Demo)..."

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

echo "✓ AITBC CLI Universal demo installed"
echo "Note: This is a demo package. For full functionality:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"

exit 0
EOF
    
    chmod +x "$temp_dir/scripts/postinstall"
    
    # Create distribution file
    cat > "$temp_dir/distribution.dist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<installer-gui-script minSpecVersion="1.0">
    <title>AITBC CLI (Universal Demo)</title>
    <organization>dev.aitbc</organization>
    <domain system="true"/>
    <options customize="never" allow-external-scripts="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AITBC CLI (Universal Demo)">
        <pkg-ref id="dev.aitbc.cli"/>
    </choice>
    <pkg-ref id="dev.aitbc.cli" version="$PKG_VERSION" onConclusion="none">$PKG_NAME.pkg</pkg-ref>
</installer-gui-script>
EOF
    
    # Create package file
    cd "$temp_dir"
    
    # Create demo package file
    cat > "universal-package-info" << EOF
Identifier: dev.aitbc.cli
Version: $PKG_VERSION
Title: AITBC CLI (Universal Demo)
Description: AITBC Command Line Interface Demo Package for all macOS architectures
Platform: macOS
Architecture: universal
Size: 60000000
EOF
    
    # Create demo package file
    tar -czf "$OUTPUT_DIR/aitbc-cli-$PKG_VERSION-universal.pkg" \
        pkg-root/ \
        scripts/ \
        distribution.dist \
        universal-package-info
    
    echo -e "${GREEN}✓ Universal .pkg file created${NC}"
    
    # Clean up
    rm -rf "$temp_dir"
}

# Create universal installer script
create_universal_installer() {
    echo -e "${BLUE}Creating universal installer script...${NC}"
    
    cat > "$OUTPUT_DIR/install-macos-universal.sh" << EOF
#!/bin/bash

# AITBC CLI Universal Installer for macOS
# Automatically detects architecture and installs appropriate package

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "\${BLUE}AITBC CLI Universal Installer for macOS\${NC}"
echo "======================================"

# Check if running on macOS
if [[ "\$OSTYPE" != "darwin"* ]]; then
    echo -e "\${RED}❌ This installer is for macOS only\${NC}"
    exit 1
fi

# Detect architecture
ARCH=\$(uname -m)
if [[ "\$ARCH" == "arm64" ]]; then
    ARCH_NAME="Apple Silicon"
    PACKAGE_FILE="aitbc-cli-$PKG_VERSION-arm64.pkg"
elif [[ "\$ARCH" == "x86_64" ]]; then
    ARCH_NAME="Intel"
    PACKAGE_FILE="aitbc-cli-$PKG_VERSION-x86_64.pkg"
else
    echo -e "\${RED}❌ Unsupported architecture: \$ARCH\${NC}"
    exit 1
fi

# Get script directory
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_PATH="\$SCRIPT_DIR/\$PACKAGE_FILE"

# Check if package exists
if [[ ! -f "\$PACKAGE_PATH" ]]; then
    echo -e "\${YELLOW}⚠ Architecture-specific package not found: \$PACKAGE_FILE\${NC}"
    echo -e "\${YELLOW}⚠ Falling back to universal package...\${NC}"
    PACKAGE_FILE="aitbc-cli-$PKG_VERSION-universal.pkg"
    PACKAGE_PATH="\$SCRIPT_DIR/\$PACKAGE_FILE"
    
    if [[ ! -f "\$PACKAGE_PATH" ]]; then
        echo -e "\${RED}❌ No suitable package found\${NC}"
        exit 1
    fi
fi

echo -e "\${BLUE}Detected: \$ARCH_NAME (\$ARCH)\${NC}"
echo -e "\${BLUE}Installing: \$PACKAGE_FILE\${NC}"
echo ""
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
tar -xzf "\$PACKAGE_FILE"

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
    
    chmod +x "$OUTPUT_DIR/install-macos-universal.sh"
    
    echo -e "${GREEN}✓ Universal installer script created${NC}"
}

# Generate comprehensive checksums
generate_checksums() {
    echo -e "${BLUE}Generating comprehensive checksums...${NC}"
    
    cd "$OUTPUT_DIR"
    
    # Create checksums file
    cat > checksums.txt << EOF
# AITBC macOS Demo Package Checksums
# Generated on $(date)
# Algorithm: SHA256

# Architecture-specific packages
aitbc-cli-$PKG_VERSION-arm64.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-arm64.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-cli-$PKG_VERSION-x86_64.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-x86_64.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-cli-$PKG_VERSION-universal.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-universal.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")

# Installer scripts
install-macos-demo.sh sha256:$(sha256sum "install-macos-demo.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
install-macos-universal.sh sha256:$(sha256sum "install-macos-universal.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")

# Legacy demo package
aitbc-cli-$PKG_VERSION-demo.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-demo.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
EOF
    
    echo -e "${GREEN}✓ Comprehensive checksums generated${NC}"
}

# Update README
update_readme() {
    echo -e "${BLUE}Updating macOS packages README...${NC}"
    
    cat > "$OUTPUT_DIR/README.md" << 'EOF'
# AITBC CLI Native macOS Packages

## 🍎 **Available Packages**

### **Universal Installer (Recommended)**
```bash
# Auto-detects architecture and installs appropriate package
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/install-macos-universal.sh | bash
```

### **Architecture-Specific Packages**

#### **Apple Silicon (M1/M2/M3)**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/aitbc-cli-0.1.0-arm64.pkg -o aitbc-cli.pkg
sudo installer -pkg aitbc-cli.pkg -target /
```

#### **Intel Macs**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/aitbc-cli-0.1.0-x86_64.pkg -o aitbc-cli.pkg
sudo installer -pkg aitbc-cli.pkg -target /
```

#### **Universal Binary**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/aitbc-cli-0.1.0-universal.pkg -o aitbc-cli.pkg
sudo installer -pkg aitbc-cli.pkg -target /
```

## 📦 **Package Files**

| Package | Architecture | Size | Description |
|---------|--------------|------|-------------|
| `aitbc-cli-0.1.0-arm64.pkg` | Apple Silicon | ~2KB | Demo package for M1/M2/M3 Macs |
| `aitbc-cli-0.1.0-x86_64.pkg` | Intel | ~2KB | Demo package for Intel Macs |
| `aitbc-cli-0.1.0-universal.pkg` | Universal | ~2KB | Demo package for all Macs |
| `aitbc-cli-0.1.0-demo.pkg` | Legacy | ~2KB | Original demo package |

## ⚠️ **Important Notes**

These are **demo packages** for demonstration purposes. They show:
- Package structure and installation process
- macOS integration (man pages, completion)
- Cross-platform distribution

For **full functionality**, use the Python-based installation:
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash
```

## ✅ **Verification**

### **Check Package Integrity**
```bash
sha256sum -c checksums.txt
```

### **Test Installation**
```bash
# After installation
aitbc --version
aitbc --help
```

## 🔄 **Future Production Packages**

When the full build system is ready, you'll get:
- **Real native executables** (~80MB each)
- **Code signing and notarization**
- **Automatic updates**
- **App Store distribution**

## 📚 **Documentation**

- **[Main Documentation](../README.md)** - Complete installation guide
- **[Migration Guide](../MACOS_MIGRATION_GUIDE.md)** - From .deb to native packages
- **[Build System](../DEBIAN_TO_MACOS_BUILD.md)** - Cross-compilation setup

---

**Demo packages for development and testing!** 🎉
EOF
    
    echo -e "${GREEN}✓ README updated${NC}"
}

# Main function
main() {
    echo -e "${BLUE}Building all macOS demo packages...${NC}"
    echo ""
    
    # Install tools
    install_tools
    
    # Create architecture-specific packages
    create_arch_package "arm64" "Apple Silicon"
    create_arch_package "x86_64" "Intel"
    
    # Create universal package
    create_universal_package
    
    # Create universal installer
    create_universal_installer
    
    # Generate checksums
    generate_checksums
    
    # Update README
    update_readme
    
    echo ""
    echo -e "${GREEN}🎉 All macOS demo packages built successfully!${NC}"
    echo ""
    echo "Packages created:"
    echo "  - $OUTPUT_DIR/aitbc-cli-$PKG_VERSION-arm64.pkg"
    echo "  - $OUTPUT_DIR/aitbc-cli-$PKG_VERSION-x86_64.pkg"
    echo "  - $OUTPUT_DIR/aitbc-cli-$PKG_VERSION-universal.pkg"
    echo "  - $OUTPUT_DIR/install-macos-universal.sh"
    echo ""
    echo "Installers:"
    echo "  - Universal: $OUTPUT_DIR/install-macos-universal.sh"
    echo "  - Demo: $OUTPUT_DIR/install-macos-demo.sh"
    echo ""
    echo -e "${YELLOW}⚠ These are demo packages for demonstration purposes.${NC}"
    echo -e "${YELLOW}⚠ For production packages, use the full build process.${NC}"
}

# Run main function
main "$@"
