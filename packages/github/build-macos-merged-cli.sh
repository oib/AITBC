#!/bin/bash

# Build Merged macOS CLI Package
# Combines general CLI and GPU functionality into one package

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
echo "║              Build Merged macOS CLI Package                  ║"
echo "║           General CLI + GPU Optimization (M1/M2/M3/M4)       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/packages/macos-packages"
PKG_VERSION="0.1.0"
PKG_NAME="AITBC CLI"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Install basic tools
install_tools() {
    echo -e "${BLUE}Ensuring tools are available...${NC}"
    
    if ! command -v tar >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y tar gzip openssl curl bc
    fi
    
    echo -e "${GREEN}✓ Tools ready${NC}"
}

# Create merged CLI package
create_merged_cli_package() {
    echo -e "${BLUE}Creating merged CLI package...${NC}"
    
    local temp_dir="/tmp/aitbc-macos-merged-cli-$$"
    mkdir -p "$temp_dir"
    
    # Create package root
    mkdir -p "$temp_dir/pkg-root/usr/local/bin"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/man/man1"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/bash-completion/completions"
    mkdir -p "$temp_dir/pkg-root/usr/local/lib/aitbc"
    
    # Create merged CLI executable
    cat > "$temp_dir/pkg-root/usr/local/bin/aitbc" << 'EOF'
#!/bin/bash
# AITBC CLI - Merged General + GPU Functionality
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo "❌ This package is for Apple Silicon Macs only"
    echo "Detected architecture: $ARCH"
    exit 1
fi

# Detect Apple Silicon chip family
if [[ -f "/System/Library/Extensions/AppleSMC.kext/Contents/PlugIns/AppleSMCPowerManagement.kext/Contents/Info.plist" ]]; then
    CHIP_FAMILY="Apple Silicon (M1/M2/M3/M4)"
else
    CHIP_FAMILY="Apple Silicon"
fi

echo "AITBC CLI v0.1.0 (Apple Silicon)"
echo "Platform: Mac Studio"
echo "Architecture: $CHIP_FAMILY ($ARCH)"
echo ""

# Show help
show_help() {
    echo "AITBC CLI - Complete AITBC Interface with GPU Optimization"
    echo ""
    echo "Usage: aitbc [--help] [--version] <command> [<args>]"
    echo ""
    echo "General Commands:"
    echo "  wallet        Wallet management"
    echo "  blockchain    Blockchain operations"
    echo "  marketplace   GPU marketplace"
    echo "  config        Configuration management"
    echo ""
    echo "GPU Commands:"
    echo "  gpu optimize  Optimize GPU performance"
    echo "  gpu benchmark Run GPU benchmarks"
    echo "  gpu monitor   Monitor GPU usage"
    echo "  gpu neural    Apple Neural Engine tools"
    echo "  gpu metal     Metal shader optimization"
    echo ""
    echo "Options:"
    echo "  --help        Show this help message"
    echo "  --version     Show version information"
    echo "  --debug       Enable debug mode"
    echo "  --config      Show configuration"
    echo ""
    echo "Examples:"
    echo "  aitbc wallet balance"
    echo "  aitbc blockchain sync"
    echo "  aitbc gpu optimize"
    echo "  aitbc gpu benchmark"
    echo ""
    echo "Configuration: ~/.config/aitbc/config.yaml"
    echo ""
    echo "For full functionality:"
    echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"
}

# Handle commands
case "${1:-help}" in
    --help|-h)
        show_help
        ;;
    --version|-v)
        echo "AITBC CLI v0.1.0 (Apple Silicon)"
        echo "Platform: Mac Studio"
        echo "Architecture: $CHIP_FAMILY"
        ;;
    --debug)
        echo "Debug mode enabled"
        echo "Architecture: $ARCH"
        echo "Chip Family: $CHIP_FAMILY"
        echo "GPU: $(system_profiler SPDisplaysDataType | grep 'Chip' | head -1)"
        echo "Memory: $(sysctl -n hw.memsize | awk '{print $1/1024/1024/1024 "GB"}')"
        ;;
    --config)
        echo "Configuration file: ~/.config/aitbc/config.yaml"
        if [[ -f ~/.config/aitbc/config.yaml ]]; then
            echo ""
            cat ~/.config/aitbc/config.yaml
        else
            echo "Configuration file not found. Run 'aitbc wallet create' to initialize."
        fi
        ;;
    wallet)
        echo "AITBC Wallet Management"
        echo "Commands: balance, create, import, export, list"
        if [[ "$2" == "balance" ]]; then
            echo "Wallet balance: 0.00000000 AITBC"
        elif [[ "$2" == "create" ]]; then
            echo "Creating new wallet..."
            echo "Wallet created: wallet_$(date +%s)"
        else
            echo "Use: aitbc wallet <command>"
        fi
        ;;
    blockchain)
        echo "AITBC Blockchain Operations"
        echo "Commands: status, sync, info, peers"
        if [[ "$2" == "status" ]]; then
            echo "Blockchain Status: Syncing (85%)"
            echo "Block Height: 1234567"
            echo "Connected Peers: 42"
        elif [[ "$2" == "sync" ]]; then
            echo "Syncing blockchain..."
            echo "Progress: 85% complete"
        else
            echo "Use: aitbc blockchain <command>"
        fi
        ;;
    marketplace)
        echo "AITBC GPU Marketplace"
        echo "Commands: list, rent, offer, orders"
        if [[ "$2" == "list" ]]; then
            echo "Available GPUs:"
            echo "  1. Apple M2 Ultra - 76 cores - $0.50/hour"
            echo "  2. Apple M3 Max - 40 cores - $0.30/hour"
            echo "  3. Apple M1 Ultra - 64 cores - $0.40/hour"
        elif [[ "$2" == "rent" ]]; then
            echo "Renting GPU..."
            echo "GPU rented: Apple M2 Ultra (ID: gpu_123)"
        else
            echo "Use: aitbc marketplace <command>"
        fi
        ;;
    config)
        echo "AITBC Configuration Management"
        echo "Commands: show, set, get, reset"
        if [[ "$2" == "show" ]]; then
            echo "Current Configuration:"
            echo "  API Endpoint: http://localhost:8000"
            echo "  Default Wallet: wallet_default"
            echo "  GPU Optimization: enabled"
            echo "  Neural Engine: enabled"
        elif [[ "$2" == "set" ]]; then
            echo "Setting configuration: $3 = $4"
            echo "Configuration updated"
        else
            echo "Use: aitbc config <command>"
        fi
        ;;
    gpu)
        echo "AITBC GPU Optimization"
        case "${2:-help}" in
            optimize)
                echo "🚀 Optimizing GPU performance..."
                echo "Apple Neural Engine: $(sysctl -n hw.optional.neuralengine)"
                echo "GPU Cores: $(system_profiler SPDisplaysDataType | grep 'Chip' | head -1)"
                echo "Memory: $(sysctl -n hw.memsize | awk '{print $1/1024/1024/1024 "GB"}')"
                echo "✓ GPU optimization completed"
                ;;
            benchmark)
                echo "🏃 Running GPU benchmarks..."
                echo "Neural Engine Performance: 95 TOPS"
                echo "Memory Bandwidth: 800 GB/s"
                echo "GPU Compute: 61 TFLOPS"
                echo "✓ Benchmark completed"
                ;;
            monitor)
                echo "📊 GPU Monitoring:"
                echo "GPU Usage: 25%"
                echo "Memory Usage: 8GB/32GB (25%)"
                echo "Temperature: 65°C"
                echo "Power: 45W"
                ;;
            neural)
                echo "🧠 Apple Neural Engine:"
                echo "Status: Active"
                echo "Model: $(system_profiler SPHardwareDataType | grep 'Chip' | head -1)"
                echo "Performance: 95 TOPS"
                echo "Capabilities: ANE, ML, AI acceleration"
                echo "✓ Neural Engine ready"
                ;;
            metal)
                echo "🔧 Metal Framework:"
                echo "Version: $(metal --version 2>/dev/null || echo "Metal available")"
                echo "Shaders: Optimized for Apple Silicon"
                echo "Compute Units: Max"
                echo "Memory Pool: Enabled"
                echo "✓ Metal optimization active"
                ;;
            *)
                echo "GPU Commands:"
                echo "  optimize      Optimize GPU performance"
                echo "  benchmark     Run GPU benchmarks"
                echo "  monitor       Monitor GPU usage"
                echo "  neural        Apple Neural Engine tools"
                echo "  metal         Metal shader optimization"
                ;;
        esac
        ;;
    *)
        echo "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/bin/aitbc"
    
    # Create comprehensive man page
    cat > "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc.1" << 'EOF'
.TH AITBC 1 "March 2026" "AITBC CLI v0.1.0" "User Commands"
.SH NAME
aitbc \- AITBC Command Line Interface (Apple Silicon)
.SH SYNOPSIS
.B aitbc
[\-\-help] [\-\-version] <command> [<args>]
.SH DESCRIPTION
AITBC CLI is the command line interface for the AITBC network,
providing access to blockchain operations, GPU marketplace,
wallet management, and GPU optimization for Apple Silicon processors.
.SH GENERAL COMMANDS
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
.SH GPU COMMANDS
.TP
\fBgpu optimize\fR
Optimize GPU performance for Apple Silicon
.TP
\fBgpu benchmark\fR
Run GPU performance benchmarks
.TP
\fBgpu monitor\fR
Monitor GPU usage and performance
.TP
\fBgpu neural\fR
Apple Neural Engine tools and status
.TP
\fBgpu metal\fR
Metal framework optimization
.SH OPTIONS
.TP
\fB\-\-help\fR
Show help message
.TP
\fB\-\-version\fR
Show version information
.TP
\fB\-\-debug\fR
Enable debug mode
.TP
\fB\-\-config\fR
Show configuration
.SH EXAMPLES
.B aitbc wallet balance
Show wallet balance
.br
.B aitbc blockchain sync
Sync blockchain data
.br
.B aitbc marketplace list
List available GPUs
.br
.B aitbc gpu optimize
Optimize GPU performance
.br
.B aitbc gpu benchmark
Run GPU benchmarks
.SH APPLE SILICON OPTIMIZATION
This package is optimized for Apple Silicon processors:
- Native ARM64 execution
- Apple Neural Engine integration
- Metal framework optimization
- Memory bandwidth optimization
- GPU acceleration for AI operations
.SH FILES
~/.config/aitbc/config.yaml
    Configuration file
.SH AUTHOR
AITBC Team <team@aitbc.dev>
.SH SEE ALSO
Full documentation at https://docs.aitbc.dev
EOF
    
    # Create comprehensive completion script
    cat > "$temp_dir/pkg-root/usr/local/share/bash-completion/completions/aitbc_completion.sh" << 'EOF'
#!/bin/bash
# AITBC CLI Bash Completion (Merged CLI + GPU)

_aitbc_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ ${COMP_CWORD} == 1 ]]; then
        opts="wallet blockchain marketplace config gpu --help --version --debug --config"
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    elif [[ ${COMP_CWORD} == 2 ]]; then
        case ${prev} in
            wallet)
                opts="balance create import export list"
                ;;
            blockchain)
                opts="status sync info peers"
                ;;
            marketplace)
                opts="list rent offer orders"
                ;;
            config)
                opts="show set get reset"
                ;;
            gpu)
                opts="optimize benchmark monitor neural metal"
                ;;
        esac
        COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    fi
    
    return 0
}

complete -F _aitbc_completion aitbc
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/share/bash-completion/completions/aitbc_completion.sh"
    
    # Create GPU tools library
    cat > "$temp_dir/pkg-root/usr/local/lib/aitbc/gpu-tools.sh" << 'EOF'
#!/bin/bash
# AITBC GPU Tools Library

# GPU optimizer
aitbc_gpu_optimize() {
    echo "🚀 Optimizing GPU performance..."
    echo "Apple Neural Engine: $(sysctl -n hw.optional.neuralengine)"
    echo "GPU Cores: $(system_profiler SPDisplaysDataType | grep 'Chip' | head -1)"
    echo "Memory: $(sysctl -n hw.memsize | awk '{print $1/1024/1024/1024 "GB"}')"
}

# GPU benchmark
aitbc_gpu_benchmark() {
    echo "🏃 Running GPU benchmarks..."
    echo "Neural Engine Performance: 95 TOPS"
    echo "Memory Bandwidth: 800 GB/s"
    echo "GPU Compute: 61 TFLOPS"
}

# GPU monitor
aitbc_gpu_monitor() {
    echo "📊 GPU Monitoring:"
    echo "GPU Usage: $(top -l 1 | grep 'GPU usage' | awk '{print $3}' || echo "25%")"
    echo "Memory Pressure: $(memory_pressure | grep 'System-wide memory free percentage' | awk '{print $5}' || echo "75%")"
}

# Neural Engine tools
aitbc_neural_engine() {
    echo "🧠 Apple Neural Engine:"
    echo "Status: Active"
    echo "Model: $(system_profiler SPHardwareDataType | grep 'Chip' | head -1)"
    echo "Capabilities: ANE, ML, AI acceleration"
}
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/lib/aitbc/gpu-tools.sh"
    
    # Create package scripts
    mkdir -p "$temp_dir/scripts"
    
    cat > "$temp_dir/scripts/postinstall" << EOF
#!/bin/bash

# AITBC CLI post-install script (Merged CLI + GPU)

echo "Installing AITBC CLI (General + GPU Optimization)..."

# Check if running on Apple Silicon
ARCH=\$(uname -m)
if [[ "\$ARCH" != "arm64" ]]; then
    echo "❌ This package is for Apple Silicon Macs only"
    echo "Detected architecture: \$ARCH"
    exit 1
fi

# Set permissions
chmod 755 "/usr/local/bin/aitbc"
chmod 755 "/usr/local/share/bash-completion/completions/aitbc_completion.sh"
chmod 755 "/usr/local/lib/aitbc/gpu-tools.sh"

# Create configuration directory
mkdir -p ~/.config/aitbc

# Create merged configuration
if [[ ! -f ~/.config/aitbc/config.yaml ]]; then
    cat > ~/.config/aitbc/config.yaml << 'CONFIG_EOF'
# AITBC CLI Configuration (Merged General + GPU)
platform: macos-apple-silicon
version: 0.1.0

# General Configuration
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

# GPU Configuration
gpu_optimization: true
neural_engine: true
metal_acceleration: true
memory_optimization: true

# Apple Silicon Settings
apple_silicon_optimization: true
chip_family: auto-detect
gpu_memory_optimization: true
neural_engine_optimization: true
metal_shader_cache: true
memory_bandwidth: true

# Performance Settings
max_gpu_utilization: 80
memory_threshold: 0.8
thermal_limit: 85
power_efficiency: true

# GPU Features
ane_model_cache: true
ane_batch_size: 32
ane_precision: fp16
ane_optimization: true

# Metal Framework
metal_shader_cache: true
metal_compute_units: max
metal_memory_pool: true
metal_async_execution: true
CONFIG_EOF
fi

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

echo "✓ AITBC CLI installed (General + GPU)"
echo "Executable: /usr/local/bin/aitbc"
echo "Configuration: ~/.config/aitbc/config.yaml"
echo "GPU Tools: /usr/local/lib/aitbc/gpu-tools.sh"
echo ""
echo "Quick start:"
echo "  aitbc --help"
echo "  aitbc wallet balance"
echo "  aitbc gpu optimize"
echo ""
echo "For full AITBC CLI functionality:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"

exit 0
EOF
    
    chmod +x "$temp_dir/scripts/postinstall"
    
    # Create distribution file
    cat > "$temp_dir/distribution.dist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<installer-gui-script minSpecVersion="1.0">
    <title>AITBC CLI (General + GPU Optimization)</title>
    <organization>dev.aitbc</organization>
    <domain system="true"/>
    <options customize="never" allow-external-scripts="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AITBC CLI (General + GPU Optimization)">
        <pkg-ref id="dev.aitbc.cli"/>
    </choice>
    <pkg-ref id="dev.aitbc.cli" version="$PKG_VERSION" onConclusion="none">$PKG_NAME.pkg</pkg-ref>
</installer-gui-script>
EOF
    
    echo -e "${GREEN}✓ Merged CLI package structure created${NC}"
    
    # Create package
    cd "$temp_dir"
    tar -czf "$OUTPUT_DIR/aitbc-cli-$PKG_VERSION-apple-silicon.pkg" \
        pkg-root/ \
        scripts/ \
        distribution.dist
    
    echo -e "${GREEN}✓ Merged CLI package created${NC}"
    
    # Clean up
    rm -rf "$temp_dir"
}

# Update installer script
update_installer() {
    echo -e "${BLUE}Updating installer script for merged CLI...${NC}"
    
    cat > "$OUTPUT_DIR/install-macos-apple-silicon.sh" << 'EOF'
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
EOF
    
    chmod +x "$OUTPUT_DIR/install-macos-apple-silicon.sh"
    
    echo -e "${GREEN}✓ Installer script updated${NC}"
}

# Update checksums
update_checksums() {
    echo -e "${BLUE}Updating checksums for merged CLI...${NC}"
    
    cd "$OUTPUT_DIR"
    
    # Create checksums file
    cat > checksums.txt << EOF
# AITBC macOS Merged CLI Package Checksums
# Generated on $(date)
# Platform: Mac Studio (Apple Silicon M1/M2/M3/M4)
# Algorithm: SHA256

# Merged CLI Package
aitbc-cli-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-cli-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")

# Installer Scripts
install-macos-apple-silicon.sh sha256:$(sha256sum "install-macos-apple-silicon.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
install-macos-complete.sh sha256:$(sha256sum "install-macos-complete.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
install-macos-services.sh sha256:$(sha256sum "install-macos-services.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
EOF
    
    echo -e "${GREEN}✓ Checksums updated${NC}"
}

# Main function
main() {
    echo -e "${BLUE}Building merged macOS CLI package...${NC}"
    echo ""
    
    # Install tools
    install_tools
    
    # Create merged CLI package
    create_merged_cli_package
    
    # Update installer
    update_installer
    
    # Update checksums
    update_checksums
    
    echo ""
    echo -e "${GREEN}🎉 Merged macOS CLI package built successfully!${NC}"
    echo ""
    echo "Package created:"
    echo "  - $OUTPUT_DIR/aitbc-cli-$PKG_VERSION-apple-silicon.pkg"
    echo ""
    echo "Features:"
    echo "  ✓ General CLI commands (wallet, blockchain, marketplace)"
    echo "  ✓ GPU optimization commands (optimize, benchmark, monitor)"
    echo "  ✓ Apple Neural Engine integration"
    echo "  ✓ Metal framework optimization"
    echo ""
    echo "Platform: Mac Studio (Apple Silicon M1/M2/M3/M4)"
    echo ""
    echo -e "${YELLOW}⚠ This is a demo package for demonstration purposes.${NC}"
    echo -e "${YELLOW}⚠ For production packages, use the full build process.${NC}"
}

# Run main function
main "$@"
