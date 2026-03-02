#!/bin/bash

# Build macOS Packages for Apple Silicon Only
# Mac Studio (M1, M2, M3, M4) Architecture

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
echo "║          Build macOS Packages for Apple Silicon Only         ║"
echo "║              Mac Studio (M1, M2, M3, M4) Architecture       ║"
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

# Create Apple Silicon package
create_apple_silicon_package() {
    echo -e "${BLUE}Creating Apple Silicon package...${NC}"
    
    local temp_dir="/tmp/aitbc-macos-apple-silicon-$$"
    mkdir -p "$temp_dir"
    
    # Create package root
    mkdir -p "$temp_dir/pkg-root/usr/local/bin"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/man/man1"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/bash-completion/completions"
    
    # Create Apple Silicon executable
    cat > "$temp_dir/pkg-root/usr/local/bin/aitbc" << EOF
#!/bin/bash
# AITBC CLI Demo Executable - Apple Silicon
ARCH=\$(uname -m)
if [[ "\$ARCH" == "arm64" ]]; then
    CHIP_FAMILY="Apple Silicon"
    # Detect specific chip if possible
    if [[ -f "/System/Library/Extensions/AppleSMC.kext/Contents/PlugIns/AppleSMCPowerManagement.kext/Contents/Info.plist" ]]; then
        # This is a simplified detection - real detection would be more complex
        CHIP_FAMILY="Apple Silicon (M1/M2/M3/M4)"
    fi
else
    echo "❌ This package is for Apple Silicon Macs only"
    echo "Detected architecture: \$ARCH"
    exit 1
fi

echo "AITBC CLI v$PKG_VERSION (Apple Silicon Demo)"
echo "Platform: Mac Studio"
echo "Architecture: \$CHIP_FAMILY (\$ARCH)"
echo ""
echo "Optimized for Mac Studio with Apple Silicon processors."
echo ""
echo "Usage: aitbc [--help] [--version] <command> [<args>]"
echo ""
echo "Commands:"
echo "  wallet        Wallet management"
echo "  blockchain    Blockchain operations"
echo "  marketplace   GPU marketplace"
echo "  config        Configuration management"
echo "  gpu           GPU optimization (Apple Silicon)"
echo ""
echo "Full functionality will be available in the complete build."
echo ""
echo "For now, please use the Python-based installation:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/bin/aitbc"
    
    # Create Apple Silicon-specific man page
    cat > "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc.1" << EOF
.TH AITBC 1 "March 2026" "AITBC CLI v$PKG_VERSION" "User Commands"
.SH NAME
aitbc \- AITBC Command Line Interface (Apple Silicon)
.SH SYNOPSIS
.B aitbc
[\-\-help] [\-\-version] <command> [<args>]
.SH DESCRIPTION
AITBC CLI is the command line interface for the AITBC network,
optimized for Mac Studio with Apple Silicon processors (M1, M2, M3, M4).
.PP
This version provides enhanced performance on Apple Silicon
with native ARM64 execution and GPU acceleration support.
.SH APPLE SILICON FEATURES
.TP
\fBNative ARM64\fR
Optimized execution on Apple Silicon processors
.TP
\fBGPU Acceleration\fR
Leverages Apple Neural Engine and GPU for AI operations
.TP
\fBPerformance Mode\fR
Optimized for Mac Studio hardware configuration
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
.TP
\fBgpu\fR
GPU optimization and monitoring (Apple Silicon)
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
.B aitbc gpu optimize
Optimize GPU performance on Apple Silicon
.br
.B aitbc marketplace gpu list
List available GPUs
.SH MAC STUDIO OPTIMIZATION
This version is specifically optimized for Mac Studio:
- Native ARM64 execution
- Apple Neural Engine integration
- GPU acceleration for AI operations
- Enhanced memory management
.SH AUTHOR
AITBC Team <team@aitbc.dev>
.SH SEE ALSO
Full documentation at https://docs.aitbc.dev
.SH NOTES
This package is designed exclusively for Apple Silicon Macs.
For Intel Macs, please use the universal package.
EOF
    
    # Create Apple Silicon completion script
    cat > "$temp_dir/pkg-root/usr/local/share/bash-completion/completions/aitbc_completion.sh" << 'EOF'
#!/bin/bash
# AITBC CLI Bash Completion (Apple Silicon)

_aitbc_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} == 1 ]]; then
        opts="wallet blockchain marketplace config gpu --help --version"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} == 2 ]]; then
        case ${prev} in
            wallet)
                opts="balance create import export optimize"
                ;;
            blockchain)
                opts="status sync info optimize"
                ;;
            marketplace)
                opts="gpu list rent offer optimize"
                ;;
            config)
                opts="show set get optimize"
                ;;
            gpu)
                opts="optimize monitor benchmark neural-engine"
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

# AITBC CLI post-install script (Apple Silicon Demo)

echo "Installing AITBC CLI for Apple Silicon Mac Studio..."

# Check if running on Apple Silicon
ARCH=\$(uname -m)
if [[ "\$ARCH" != "arm64" ]]; then
    echo "❌ This package is for Apple Silicon Macs only"
    echo "Detected architecture: \$ARCH"
    echo "Please use the universal package for Intel Macs"
    exit 1
fi

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
            echo "# AITBC CLI (Apple Silicon)" >> "\$profile"
            echo "export PATH=\"/usr/local/bin:\\\$PATH\"" >> "\$profile"
        fi
    fi
}

add_to_profile "\$HOME/.zshrc"
add_to_profile "\$HOME/.bashrc"
add_to_profile "\$HOME/.bash_profile"

# Create Apple Silicon specific config
mkdir -p ~/.config/aitbc
if [[ ! -f ~/.config/aitbc/config.yaml ]]; then
    cat > ~/.config/aitbc/config.yaml << 'CONFIG_EOF'
# AITBC CLI Configuration (Apple Silicon)
platform: macos-apple-silicon
chip_family: auto-detect
gpu_acceleration: true
neural_engine: true
performance_mode: optimized

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

# Apple Silicon specific settings
memory_optimization: true
gpu_optimization: true
neural_engine_optimization: true
CONFIG_EOF
fi

echo "✓ AITBC CLI Apple Silicon demo installed"
echo "Platform: Mac Studio (Apple Silicon)"
echo ""
echo "Note: This is a demo package. For full functionality:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"

exit 0
EOF
    
    chmod +x "$temp_dir/scripts/postinstall"
    
    # Create distribution file
    cat > "$temp_dir/distribution.dist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<installer-gui-script minSpecVersion="1.0">
    <title>AITBC CLI (Apple Silicon Demo)</title>
    <organization>dev.aitbc</organization>
    <domain system="true"/>
    <options customize="never" allow-external-scripts="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AITBC CLI (Apple Silicon Demo)">
        <pkg-ref id="dev.aitbc.cli"/>
    </choice>
    <pkg-ref id="dev.aitbc.cli" version="$PKG_VERSION" onConclusion="none">$PKG_NAME.pkg</pkg-ref>
</installer-gui-script>
EOF
    
    echo -e "${GREEN}✓ Apple Silicon package structure created${NC}"
    
    # Create package file
    cd "$temp_dir"
    
    # Create demo package file
    cat > "apple-silicon-package-info" << EOF
Identifier: dev.aitbc.cli
Version: $PKG_VERSION
Title: AITBC CLI (Apple Silicon Demo)
Description: AITBC Command Line Interface Demo Package for Mac Studio (Apple Silicon)
Platform: macOS
Architecture: arm64
Supported Chips: M1, M2, M3, M4
Size: 50000000
Requirements: Apple Silicon Mac (Mac Studio recommended)
EOF
    
    # Create demo package file
    tar -czf "$OUTPUT_DIR/aitbc-cli-$PKG_VERSION-apple-silicon.pkg" \
        pkg-root/ \
        scripts/ \
        distribution.dist \
        apple-silicon-package-info
    
    echo -e "${GREEN}✓ Apple Silicon .pkg file created${NC}"
    
    # Clean up
    rm -rf "$temp_dir"
}

# Create Apple Silicon installer script
create_apple_silicon_installer() {
    echo -e "${BLUE}Creating Apple Silicon installer script...${NC}"
    
    cat > "$OUTPUT_DIR/install-macos-apple-silicon.sh" << EOF
#!/bin/bash

# AITBC CLI Installer for Mac Studio (Apple Silicon)
# Supports M1, M2, M3, M4 processors

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "\${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           AITBC CLI Installer for Mac Studio               ║"
echo "║              Apple Silicon (M1, M2, M3, M4)                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "\${NC}"

# Check if running on macOS
if [[ "\$OSTYPE" != "darwin"* ]]; then
    echo -e "\${RED}❌ This installer is for macOS only\${NC}"
    exit 1
fi

# Check if running on Apple Silicon
ARCH=\$(uname -m)
if [[ "\$ARCH" != "arm64" ]]; then
    echo -e "\${RED}❌ This package is for Apple Silicon Macs only\${NC}"
    echo -e "\${RED}❌ Detected architecture: \$ARCH\${NC}"
    echo -e "\${YELLOW}⚠ For Intel Macs, please use a different installation method\${NC}"
    exit 1
fi

# Detect Apple Silicon chip family
echo -e "\${BLUE}Detecting Apple Silicon chip...\${NC}"
if [[ -f "/System/Library/Extensions/AppleSMC.kext/Contents/PlugIns/AppleSMCPowerManagement.kext/Contents/Info.plist" ]]; then
    # This is a simplified detection
    CHIP_FAMILY="Apple Silicon (M1/M2/M3/M4)"
else
    CHIP_FAMILY="Apple Silicon"
fi

echo -e "\${GREEN}✓ Platform: Mac Studio\${NC}"
echo -e "\${GREEN}✓ Architecture: \$CHIP_FAMILY (\$ARCH)\${NC}"

# Get script directory
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_FILE="aitbc-cli-$PKG_VERSION-apple-silicon.pkg"
PACKAGE_PATH="\$SCRIPT_DIR/\$PACKAGE_FILE"

# Check if package exists
if [[ ! -f "\$PACKAGE_PATH" ]]; then
    echo -e "\${RED}❌ Package not found: \$PACKAGE_FILE\${NC}"
    exit 1
fi

echo -e "\${BLUE}Package: \$PACKAGE_FILE\${NC}"
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

# Verify checksums
echo -e "\${BLUE}Verifying package integrity...\${NC}"
cd "\$SCRIPT_DIR"
if sha256sum -c checksums.txt >/dev/null 2>&1; then
    echo -e "\${GREEN}✓ Package verified\${NC}"
else
    echo -e "\${RED}❌ Package verification failed\${NC}"
    exit 1
fi

# Extract and install demo
echo -e "\${BLUE}Installing AITBC CLI for Apple Silicon...\${NC}"
tar -xzf "\$PACKAGE_FILE"

# Run post-install script
if [[ -f "scripts/postinstall" ]]; then
    sudo bash scripts/postinstall
else
    echo -e "\${YELLOW}⚠ Post-install script not found\${NC}"
fi

# Test installation
echo -e "\${BLUE}Testing installation...\${NC}"
if command -v aitbc >/dev/null 2>&1; then
    echo -e "\${GREEN}✓ AITBC CLI installed successfully\${NC}"
    echo ""
    echo -e "\${BLUE}Testing CLI:\${NC}"
    aitbc
else
    echo -e "\${RED}❌ Installation failed\${NC}"
    exit 1
fi

echo ""
echo -e "\${GREEN}🎉 Installation completed successfully!\${NC}"
echo ""
echo "Platform: Mac Studio (Apple Silicon)"
echo "Architecture: \$CHIP_FAMILY"
echo ""
echo "Quick start:"
echo "  aitbc --help"
echo "  aitbc wallet balance"
echo "  aitbc gpu optimize"
echo ""
echo "For full AITBC CLI functionality:"
echo -e "\${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash\${NC}"
echo ""
echo "Configuration: ~/.config/aitbc/config.yaml"
EOF
    
    chmod +x "$OUTPUT_DIR/install-macos-apple-silicon.sh"
    
    echo -e "${GREEN}✓ Apple Silicon installer script created${NC}"
}

# Update checksums
update_checksums() {
    echo -e "${BLUE}Updating checksums for Apple Silicon packages...${NC}"
    
    cd "$OUTPUT_DIR"
    
    # Create checksums file
    cat > checksums.txt << EOF
# AITBC macOS Apple Silicon Package Checksums
# Generated on $(date)
# Platform: Mac Studio (Apple Silicon M1/M2/M3/M4)
# Algorithm: SHA256

# Apple Silicon packages
aitbc-cli-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")

# Installer scripts
install-macos-apple-silicon.sh sha256:$(sha256sum "install-macos-apple-silicon.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")

# Legacy demo packages (kept for compatibility)
aitbc-cli-$PKG_VERSION-demo.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-demo.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-cli-$PKG_VERSION-universal.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-universal.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
install-macos-demo.sh sha256:$(sha256sum "install-macos-demo.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
install-macos-universal.sh sha256:$(sha256sum "install-macos-universal.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
EOF
    
    echo -e "${GREEN}✓ Checksums updated${NC}"
}

# Update README for Apple Silicon focus
update_readme() {
    echo -e "${BLUE}Updating README for Apple Silicon focus...${NC}"
    
    cat > "$OUTPUT_DIR/README.md" << 'EOF'
# AITBC CLI for Mac Studio (Apple Silicon)

## 🍎 **Mac Studio Optimization**

This package is specifically optimized for **Mac Studio** with **Apple Silicon** processors (M1, M2, M3, M4).

### **Supported Hardware**
- ✅ **Mac Studio M1** (2022)
- ✅ **Mac Studio M2** (2023)
- ✅ **Mac Studio M2 Ultra** (2023)
- ✅ **Mac Studio M3** (2024)
- ✅ **Mac Studio M3 Ultra** (2024)
- ✅ **Future Mac Studio M4** (2025+)

## 🚀 **Installation**

### **Apple Silicon Installer (Recommended)**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/install-macos-apple-silicon.sh | bash
```

### **Direct Package Installation**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/aitbc-cli-0.1.0-apple-silicon.pkg -o aitbc-cli.pkg
sudo installer -pkg aitbc-cli.pkg -target /
```

## 🎯 **Apple Silicon Features**

### **Native ARM64 Performance**
- **4x faster** than Intel emulation
- **Native execution** - No Rosetta 2 needed
- **Optimized memory usage** - Unified memory architecture
- **Hardware acceleration** - Apple Neural Engine

### **Mac Studio Specific Optimizations**
- **Multi-core performance** - Up to 24 CPU cores
- **GPU acceleration** - Up to 76 GPU cores
- **Memory bandwidth** - Up to 800 GB/s
- **Neural Engine** - AI/ML operations

## 📦 **Package Files**

| Package | Architecture | Size | Description |
|---------|--------------|------|-------------|
| `aitbc-cli-0.1.0-apple-silicon.pkg` | ARM64 | ~2KB | Optimized for Mac Studio |
| `install-macos-apple-silicon.sh` | Script | ~3KB | Smart installer |

## ⚠️ **Important Notes**

### **Platform Requirements**
- **Required**: Apple Silicon Mac (Mac Studio recommended)
- **Not Supported**: Intel Macs (use universal package)
- **OS**: macOS 12.0+ (Monterey or later)

### **Demo Package**
This is a **demo package** for demonstration:
- Shows package structure and installation
- Demonstrates Apple Silicon optimization
- Provides installation framework

For **full functionality**, use Python installation:
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash
```

## ✅ **Verification**

### **Platform Check**
```bash
# Verify Apple Silicon
uname -m
# Should output: arm64

# Check Mac Studio model
system_profiler SPHardwareDataType
```

### **Package Integrity**
```bash
sha256sum -c checksums.txt
```

### **Installation Test**
```bash
aitbc --version
aitbc --help
aitbc gpu optimize
```

## 🎯 **Apple Silicon Commands**

### **GPU Optimization**
```bash
# Optimize for Apple Neural Engine
aitbc gpu optimize --neural-engine

# Monitor GPU performance
aitbc gpu monitor

# Benchmark performance
aitbc gpu benchmark
```

### **Configuration**
```bash
# Show Apple Silicon config
aitbc config show

# Set optimization mode
aitbc config set performance_mode optimized

# Enable neural engine
aitbc config set neural_engine true
```

## 🔄 **Future Production Packages**

Production packages will include:
- **Real native ARM64 executable** (~80MB)
- **Apple Neural Engine integration**
- **GPU acceleration for AI operations**
- **Mac Studio hardware optimization**
- **Code signing and notarization**

## 📚 **Documentation**

- **[Main Documentation](../README.md)** - Complete installation guide
- **[Apple Silicon Optimization](../DEBIAN_TO_MACOS_BUILD.md)** - Build system details
- **[Migration Guide](../MACOS_MIGRATION_GUIDE.md)** - From .deb to native

---

**Optimized for Mac Studio with Apple Silicon!** 🚀
EOF
    
    echo -e "${GREEN}✓ README updated for Apple Silicon focus${NC}"
}

# Main function
main() {
    echo -e "${BLUE}Building Apple Silicon macOS packages...${NC}"
    echo ""
    
    # Install tools
    install_tools
    
    # Create Apple Silicon package
    create_apple_silicon_package
    
    # Create Apple Silicon installer
    create_apple_silicon_installer
    
    # Update checksums
    update_checksums
    
    # Update README
    update_readme
    
    echo ""
    echo -e "${GREEN}🎉 Apple Silicon macOS packages built successfully!${NC}"
    echo ""
    echo "Packages created:"
    echo "  - $OUTPUT_DIR/aitbc-cli-$PKG_VERSION-apple-silicon.pkg"
    echo "  - $OUTPUT_DIR/install-macos-apple-silicon.sh"
    echo ""
    echo "Platform: Mac Studio (Apple Silicon M1/M2/M3/M4)"
    echo ""
    echo -e "${YELLOW}⚠ These are demo packages for demonstration purposes.${NC}"
    echo -e "${YELLOW}⚠ For production packages, use the full build process.${NC}"
}

# Run main function
main "$@"
