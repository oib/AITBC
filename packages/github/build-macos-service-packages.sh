#!/bin/bash

# Build Individual macOS Service Packages
# Match Debian service packages structure

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            Build Individual macOS Service Packages           ║"
echo "║                Match Debian Service Packages                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/packages/macos-services"
PKG_VERSION="0.1.0"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Service packages to create (matching Debian)
SERVICES=(
    "aitbc-node-service:Blockchain Node Service"
    "aitbc-coordinator-service:Coordinator API Service"
    "aitbc-miner-service:GPU Miner Service"
    "aitbc-marketplace-service:Marketplace Service"
    "aitbc-explorer-service:Blockchain Explorer Service"
    "aitbc-wallet-service:Wallet Service"
    "aitbc-multimodal-service:Multimodal AI Service"
    "aitbc-all-services:Complete Service Stack"
)

# Install basic tools
install_tools() {
    echo -e "${BLUE}Ensuring tools are available...${NC}"
    
    if ! command -v tar >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y tar gzip openssl curl bc
    fi
    
    echo -e "${GREEN}✓ Tools ready${NC}"
}

# Create individual service package
create_service_package() {
    local service_name="$1"
    local service_desc="$2"
    
    echo -e "${BLUE}Creating $service_desc...${NC}"
    
    local temp_dir="/tmp/aitbc-macos-service-$$-$service_name"
    mkdir -p "$temp_dir"
    
    # Extract service name for display
    local display_name=$(echo "$service_name" | sed 's/aitbc-//' | sed 's/-service//' | sed 's/\b\w/\u&/g')
    
    # Create package root
    mkdir -p "$temp_dir/pkg-root/usr/local/bin"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/man/man1"
    mkdir -p "$temp_dir/pkg-root/usr/local/share/bash-completion/completions"
    mkdir -p "$temp_dir/pkg-root/usr/local/lib/aitbc"
    mkdir -p "$temp_dir/pkg-root/Library/LaunchDaemons"
    
    # Create service executable
    cat > "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << EOF
#!/bin/bash
# AITBC $display_name Service - Apple Silicon
ARCH=\$(uname -m)
if [[ "\$ARCH" != "arm64" ]]; then
    echo "❌ This package is for Apple Silicon Macs only"
    echo "Detected architecture: \$ARCH"
    exit 1
fi

echo "AITBC $display_name v$PKG_VERSION (Apple Silicon)"
echo "Platform: Mac Studio"
echo "Architecture: \$ARCH"
echo ""
echo "🚀 $display_name Features:"
EOF

    # Add service-specific features
    case "$service_name" in
        "aitbc-node-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - Blockchain node operations"
echo "  - P2P network connectivity"
echo "  - Block synchronization"
echo "  - RPC server functionality"
echo "  - Consensus mechanism"
EOF
            ;;
        "aitbc-coordinator-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - Job coordination"
echo "  - API gateway functionality"
echo "  - Service orchestration"
echo "  - Load balancing"
echo "  - Health monitoring"
EOF
            ;;
        "aitbc-miner-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - GPU mining operations"
echo "  - Apple Neural Engine optimization"
echo "  - Metal shader acceleration"
echo "  - Mining pool connectivity"
echo "  - Performance monitoring"
EOF
            ;;
        "aitbc-marketplace-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - GPU marketplace operations"
echo "  - Resource discovery"
echo "  - Pricing algorithms"
echo "  - Order matching"
echo "  - Reputation system"
EOF
            ;;
        "aitbc-explorer-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - Blockchain explorer"
echo "  - Web interface"
echo "  - Transaction tracking"
echo "  - Address analytics"
echo "  - Block visualization"
EOF
            ;;
        "aitbc-wallet-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - Wallet management"
echo "  - Transaction signing"
echo "  - Multi-signature support"
echo "  - Key management"
echo "  - Balance tracking"
EOF
            ;;
        "aitbc-multimodal-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - Multimodal AI processing"
echo "  - Text, image, audio, video"
echo "  - Cross-modal operations"
echo "  - Apple Neural Engine"
echo "  - AI model management"
EOF
            ;;
        "aitbc-all-services")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  - Complete service stack"
echo "  - All AITBC services"
echo "  - Unified management"
echo "  - Service orchestration"
echo "  - Centralized monitoring"
EOF
            ;;
    esac
    
    cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << EOF
echo ""
echo "Usage: aitbc-$service_name [--help] [--version] <command> [<args>]"
echo ""
echo "Commands:"
EOF

    # Add service-specific commands
    case "$service_name" in
        "aitbc-node-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start the node service"
echo "  stop          Stop the node service"
echo "  status        Show node status"
echo "  sync          Sync blockchain"
echo "  peers         Show connected peers"
EOF
            ;;
        "aitbc-coordinator-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start coordinator service"
echo "  stop          Stop coordinator service"
echo "  status        Show service status"
echo "  health        Health check"
echo "  jobs          Show active jobs"
EOF
            ;;
        "aitbc-miner-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start mining"
echo "  stop          Stop mining"
echo "  status        Show mining status"
echo "  hashrate      Show hash rate"
echo "  earnings      Show earnings"
EOF
            ;;
        "aitbc-marketplace-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start marketplace"
echo "  stop          Stop marketplace"
echo "  status        Show marketplace status"
echo "  listings      Show active listings"
echo "  orders        Show orders"
EOF
            ;;
        "aitbc-explorer-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start explorer"
echo "  stop          Stop explorer"
echo "  status        Show explorer status"
echo "  web           Open web interface"
echo "  search        Search blockchain"
EOF
            ;;
        "aitbc-wallet-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start wallet service"
echo "  stop          Stop wallet service"
echo "  status        Show wallet status"
echo "  balance       Show balance"
echo "  transactions  Show transactions"
EOF
            ;;
        "aitbc-multimodal-service")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start multimodal service"
echo "  stop          Stop multimodal service"
echo "  status        Show service status"
echo "  process       Process multimodal input"
echo "  models        Show available models"
EOF
            ;;
        "aitbc-all-services")
            cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << 'EOF'
echo "  start         Start all services"
echo "  stop          Stop all services"
echo "  status        Show all services status"
echo "  restart       Restart all services"
echo "  monitor       Monitor all services"
EOF
            ;;
    esac
    
    cat >> "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name" << EOF
echo ""
echo "Options:"
echo "  --help         Show this help message"
echo "  --version      Show version information"
echo "  --debug        Enable debug mode"
echo "  --config       Show configuration"
echo ""
echo "Configuration: ~/.config/aitbc/\$service_name.yaml"
echo ""
echo "Note: This is a demo package. For full functionality:"
echo "curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash"
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/bin/aitbc-$service_name"
    
    # Create service-specific man page
    cat > "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc-$service_name.1" << EOF
.TH AITBC-$display_name 1 "March 2026" "AITBC CLI v$PKG_VERSION" "User Commands"
.SH NAME
aitbc-$service_name \- AITBC $display_name Service (Apple Silicon)
.SH SYNOPSIS
.B aitbc-$service_name
[\-\-help] [\-\-version] <command> [<args>]
.SH DESCRIPTION
AITBC $display_name Service is the macOS package for managing
the $display_name component of the AITBC network, optimized for
Apple Silicon processors in Mac Studio.
.SH COMMANDS
EOF

    # Add service-specific man page commands
    case "$service_name" in
        "aitbc-node-service")
            cat >> "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc-$service_name.1" << 'EOF'
.TP
\fBstart\fR
Start the blockchain node service
.TP
\fBstop\fR
Stop the blockchain node service
.TP
\fBstatus\fR
Show node status and synchronization
.TP
\fBsync\fR
Synchronize blockchain data
.TP
\fBpeers\fR
Show connected peers
EOF
            ;;
        "aitbc-coordinator-service")
            cat >> "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc-$service_name.1" << 'EOF'
.TP
\fBstart\fR
Start coordinator service
.TP
\fBstop\fR
Stop coordinator service
.TP
\fBstatus\fR
Show service status
.TP
\fBhealth\fR
Perform health check
.TP
\fBjobs\fR
Show active jobs
EOF
            ;;
        # Add other services similarly...
    esac
    
    cat >> "$temp_dir/pkg-root/usr/local/share/man/man1/aitbc-$service_name.1" << EOF
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
.SH APPLE SILICON OPTIMIZATION
This package is optimized for Apple Silicon processors:
- Native ARM64 execution
- Apple Neural Engine integration
- Metal framework optimization
- Memory bandwidth optimization
.SH FILES
~/.config/aitbc/$service_name.yaml
    Configuration file
.SH AUTHOR
AITBC Team <team@aitbc.dev>
.SH SEE ALSO
Full documentation at https://docs.aitbc.dev
EOF
    
    # Create service completion script
    cat > "$temp_dir/pkg-root/usr/local/share/bash-completion/completions/aitbc-$service_name-completion.sh" << EOF
#!/bin/bash
# AITBC $display_name Bash Completion

_aitbc_$service_name() {
    local cur prev opts
    COMPREPLY=()
    cur="\${COMP_WORDS[COMP_CWORD]}"
    prev="\${COMP_WORDS[COMP_CWORD-1]}"
    
    if [[ \${COMP_CWORD} == 1 ]]; then
        opts="start stop status --help --version --debug --config"
        COMPREPLY=( \$(compgen -W "\${opts}" -- \${cur}) )
    fi
    
    return 0
}

complete -F _aitbc_$service_name aitbc-$service_name
EOF
    
    chmod +x "$temp_dir/pkg-root/usr/local/share/bash-completion/completions/aitbc-$service_name-completion.sh"
    
    # Create service configuration
    mkdir -p "$temp_dir/pkg-root/usr/local/lib/aitbc"
    cat > "$temp_dir/pkg-root/usr/local/lib/aitbc/$service_name-config.yaml" << EOF
# AITBC $display_name Configuration
service_name: $service_name
platform: macos-apple-silicon
version: $PKG_VERSION

# Service Configuration
port: 8080
host: localhost
debug_mode: false
log_level: INFO

# Apple Silicon Optimization
apple_silicon_optimization: true
neural_engine: true
metal_acceleration: true
memory_optimization: true

# Service Settings
EOF

    # Add service-specific configuration
    case "$service_name" in
        "aitbc-node-service")
            cat >> "$temp_dir/pkg-root/usr/local/lib/aitbc/$service_name-config.yaml" << 'EOF'
node:
  p2p_port: 30333
  rpc_port: 8545
  data_dir: ~/.aitbc/node
  sync_mode: fast
  max_peers: 50
EOF
            ;;
        "aitbc-coordinator-service")
            cat >> "$temp_dir/pkg-root/usr/local/lib/aitbc/$service_name-config.yaml" << 'EOF'
coordinator:
  api_port: 8000
  database_url: postgresql://localhost:aitbc
  redis_url: redis://localhost:6379
  job_timeout: 300
  max_concurrent_jobs: 100
EOF
            ;;
        # Add other service configurations...
    esac
    
    # Create package scripts
    mkdir -p "$temp_dir/scripts"
    
    cat > "$temp_dir/scripts/postinstall" << EOF
#!/bin/bash

# AITBC $display_name post-install script

echo "Installing AITBC $display_name..."

# Check Apple Silicon
ARCH=\$(uname -m)
if [[ "\$ARCH" != "arm64" ]]; then
    echo "❌ This package is for Apple Silicon Macs only"
    exit 1
fi

# Set permissions
chmod 755 "/usr/local/bin/aitbc-$service_name"
chmod 755 "/usr/local/share/bash-completion/completions/aitbc-$service_name-completion.sh"

# Create configuration directory
mkdir -p ~/.config/aitbc

# Copy configuration if not exists
if [[ !f ~/.config/aitbc/$service_name.yaml ]]; then
    cp "/usr/local/lib/aitbc/$service_name-config.yaml" ~/.config/aitbc/$service_name.yaml
    echo "✓ Configuration created: ~/.config/aitbc/$service_name.yaml"
fi

# Add to PATH
add_to_profile() {
    local profile="\$1"
    if [[ -f "\$profile" ]]; then
        if ! grep -q "/usr/local/bin" "\$profile"; then
            echo "" >> "\$profile"
            echo "# AITBC CLI ($display_name)" >> "\$profile"
            echo "export PATH=\"/usr/local/bin:\\\$PATH\"" >> "\$profile"
        fi
    fi
}

add_to_profile "\$HOME/.zshrc"
add_to_profile "\$HOME/.bashrc"
add_to_profile "\$HOME/.bash_profile"

echo "✓ AITBC $display_name installed"
echo "Executable: /usr/local/bin/aitbc-$service_name"
echo "Configuration: ~/.config/aitbc/$service_name.yaml"
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
    <title>AITBC $display_name (Apple Silicon)</title>
    <organization>dev.aitbc</organization>
    <domain system="true"/>
    <options customize="never" allow-external-scripts="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default" title="AITBC $display_name (Apple Silicon)">
        <pkg-ref id="dev.aitbc.$service_name"/>
    </choice>
    <pkg-ref id="dev.aitbc.$service_name" version="$PKG_VERSION" onConclusion="none">AITBC $display_name.pkg</pkg-ref>
</installer-gui-script>
EOF
    
    # Create package
    cd "$temp_dir"
    tar -czf "$OUTPUT_DIR/$service_name-$PKG_VERSION-apple-silicon.pkg" \
        pkg-root/ \
        scripts/ \
        distribution.dist
    
    echo -e "${GREEN}✓ $display_name package created${NC}"
    rm -rf "$temp_dir"
}

# Create service installer script
create_service_installer() {
    echo -e "${BLUE}Creating service installer script...${NC}"
    
    cat > "$OUTPUT_DIR/install-macos-services.sh" << 'EOF'
#!/bin/bash

# AITBC Services Installer for Mac Studio (Apple Silicon)
# Install individual service packages

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
echo "║                AITBC Services Installer                   ║"
echo "║                 Mac Studio (Apple Silicon)                 ║"
echo "║                    Individual Services                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo -e "${RED}❌ This installer is for macOS only${NC}"
    exit 1
fi

# Check Apple Silicon
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo -e "${RED}❌ This package is for Apple Silicon Macs only${NC}"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Available services
SERVICES=(
    "aitbc-node-service-0.1.0-apple-silicon.pkg:Blockchain Node Service"
    "aitbc-coordinator-service-0.1.0-apple-silicon.pkg:Coordinator API Service"
    "aitbc-miner-service-0.1.0-apple-silicon.pkg:GPU Miner Service"
    "aitbc-marketplace-service-0.1.0-apple-silicon.pkg:Marketplace Service"
    "aitbc-explorer-service-0.1.0-apple-silicon.pkg:Blockchain Explorer Service"
    "aitbc-wallet-service-0.1.0-apple-silicon.pkg:Wallet Service"
    "aitbc-multimodal-service-0.1.0-apple-silicon.pkg:Multimodal AI Service"
    "aitbc-all-services-0.1.0-apple-silicon.pkg:Complete Service Stack"
)

echo -e "${BLUE}Available services:${NC}"
for i in "${!SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "${SERVICES[$i]}"
    echo "  $((i+1)). $description"
done

echo ""
read -p "Select services to install (e.g., 1,2,3 or all): " selection

# Parse selection
if [[ "$selection" == "all" ]]; then
    SELECTED_SERVICES=("${SERVICES[@]}")
else
    IFS=',' read -ra INDICES <<< "$selection"
    SELECTED_SERVICES=()
    for index in "${INDICES[@]}"; do
        idx=$((index-1))
        if [[ $idx -ge 0 && $idx -lt ${#SERVICES[@]} ]]; then
            SELECTED_SERVICES+=("${SERVICES[$idx]}")
        fi
    done
fi

echo ""
echo -e "${BLUE}Selected services:${NC}"
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    echo "  ✓ $description"
done

echo ""
echo -e "${YELLOW}⚠ These are demo packages for demonstration purposes.${NC}"
echo -e "${YELLOW}⚠ For full functionality, use the Python-based installation:${NC}"
echo ""
echo -e "${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash${NC}"
echo ""

read -p "Continue with installation? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# Install services
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    package_path="$SCRIPT_DIR/$package_name"
    
    if [[ -f "$package_path" ]]; then
        echo -e "${BLUE}Installing $description...${NC}"
        cd "$SCRIPT_DIR"
        tar -xzf "$package_name"
        
        if [[ -f "scripts/postinstall" ]]; then
            sudo bash scripts/postinstall
        fi
        
        # Clean up for next service
        rm -rf pkg-root scripts distribution.dist *.pkg-info 2>/dev/null || true
        
        echo -e "${GREEN}✓ $description installed${NC}"
    else
        echo -e "${YELLOW}⚠ Service package not found: $package_name${NC}"
    fi
done

echo ""
echo -e "${GREEN}🎉 Services installation completed!${NC}"
echo ""
echo "Installed services:"
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    service_executable=$(echo "$package_name" | sed 's/-0.1.0-apple-silicon.pkg//')
    if command -v "$service_executable" >/dev/null 2>&1; then
        echo "  ✓ $service_executable"
    fi
done

echo ""
echo "Configuration files:"
for service in "${SELECTED_SERVICES[@]}"; do
    IFS=':' read -r package_name description <<< "$service"
    service_config=$(echo "$package_name" | sed 's/-0.1.0-apple-silicon.pkg/.yaml/')
    echo "  ~/.config/aitbc/$service_config"
done

echo ""
echo "For full AITBC CLI functionality:"
echo -e "${BLUE}curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash${NC}"
EOF
    
    chmod +x "$OUTPUT_DIR/install-macos-services.sh"
    
    echo -e "${GREEN}✓ Service installer script created${NC}"
}

# Update service checksums
update_service_checksums() {
    echo -e "${BLUE}Updating service package checksums...${NC}"
    
    cd "$OUTPUT_DIR"
    
    # Create checksums file
    cat > checksums.txt << EOF
# AITBC macOS Service Packages Checksums
# Generated on $(date)
# Platform: Mac Studio (Apple Silicon M1/M2/M3/M4)
# Algorithm: SHA256

# Individual Service Packages
aitbc-node-service-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-node-service-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-coordinator-service-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-coordinator-service-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-miner-service-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-miner-service-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-marketplace-service-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-marketplace-service-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-explorer-service-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-explorer-service-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-wallet-service-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-wallet-service-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-multimodal-service-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-multimodal-service-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
aitbc-all-services-$PKG_VERSION-apple-silicon.pkg sha256:$(sha256sum "aitbc-all-services-$PKG_VERSION-apple-silicon.pkg" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")

# Installer Scripts
install-macos-services.sh sha256:$(sha256sum "install-macos-services.sh" 2>/dev/null | cut -d' ' -f1 || echo "NOT_FOUND")
EOF
    
    echo -e "${GREEN}✓ Service checksums updated${NC}"
}

# Create service README
create_service_readme() {
    echo -e "${BLUE}Creating service packages README...${NC}"
    
    cat > "$OUTPUT_DIR/README.md" << 'EOF'
# AITBC macOS Service Packages

## 🍎 **Individual Service Packages for Mac Studio**

Individual service packages for **Mac Studio** with **Apple Silicon** processors (M1, M2, M3, M4).

## 📦 **Available Service Packages**

### **Core Infrastructure**
- **`aitbc-node-service-0.1.0-apple-silicon.pkg`** - Blockchain node service
- **`aitbc-coordinator-service-0.1.0-apple-silicon.pkg`** - Coordinator API service

### **Application Services**
- **`aitbc-miner-service-0.1.0-apple-silicon.pkg`** - GPU miner service
- **`aitbc-marketplace-service-0.1.0-apple-silicon.pkg`** - Marketplace service
- **`aitbc-explorer-service-0.1.0-apple-silicon.pkg`** - Explorer service
- **`aitbc-wallet-service-0.1.0-apple-silicon.pkg`** - Wallet service
- **`aitbc-multimodal-service-0.1.0-apple-silicon.pkg`** - Multimodal AI service

### **Meta Package**
- **`aitbc-all-services-0.1.0-apple-silicon.pkg`** - Complete service stack

## 🚀 **Installation**

### **Option 1: Service Installer (Recommended)**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-services/install-macos-services.sh | bash
```

### **Option 2: Individual Service Installation**
```bash
# Download specific service
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-services/aitbc-node-service-0.1.0-apple-silicon.pkg -o node.pkg
sudo installer -pkg node.pkg -target /

# Install multiple services
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-services/aitbc-coordinator-service-0.1.0-apple-silicon.pkg -o coordinator.pkg
sudo installer -pkg coordinator.pkg -target /
```

## 🎯 **Service Commands**

### **Node Service**
```bash
aitbc-node-service start
aitbc-node-service status
aitbc-node-service sync
aitbc-node-service peers
```

### **Coordinator Service**
```bash
aitbc-coordinator-service start
aitbc-coordinator-service status
aitbc-coordinator-service health
aitbc-coordinator-service jobs
```

### **Miner Service**
```bash
aitbc-miner-service start
aitbc-miner-service status
aitbc-miner-service hashrate
aitbc-miner-service earnings
```

### **Marketplace Service**
```bash
aitbc-marketplace-service start
aitbc-marketplace-service status
aitbc-marketplace-service listings
aitbc-marketplace-service orders
```

### **Explorer Service**
```bash
aitbc-explorer-service start
aitbc-explorer-service status
aitbc-explorer-service web
aitbc-explorer-service search
```

### **Wallet Service**
```bash
aitbc-wallet-service start
aitbc-wallet-service status
aitbc-wallet-service balance
aitbc-wallet-service transactions
```

### **Multimodal Service**
```bash
aitbc-multimodal-service start
aitbc-multimodal-service status
aitbc-multimodal-service process
aitbc-multimodal-service models
```

### **All Services**
```bash
aitbc-all-services start
aitbc-all-services status
aitbc-all-services restart
aitbc-all-services monitor
```

## 📊 **Service Configuration**

Each service creates its own configuration file:
- **Node**: `~/.config/aitbc/aitbc-node-service.yaml`
- **Coordinator**: `~/.config/aitbc/aitbc-coordinator-service.yaml`
- **Miner**: `~/.config/aitbc/aitbc-miner-service.yaml`
- **Marketplace**: `~/.config/aitbc/aitbc-marketplace-service.yaml`
- **Explorer**: `~/.config/aitbc/aitbc-explorer-service.yaml`
- **Wallet**: `~/.config/aitbc/aitbc-wallet-service.yaml`
- **Multimodal**: `~/.config/aitbc/aitbc-multimodal-service.yaml`

## 🔧 **Apple Silicon Optimization**

Each service is optimized for Apple Silicon:
- **Native ARM64 execution** - No Rosetta 2 needed
- **Apple Neural Engine** - AI/ML acceleration
- **Metal framework** - GPU optimization
- **Memory bandwidth** - Optimized for unified memory

## ⚠️ **Important Notes**

### **Platform Requirements**
- **Required**: Apple Silicon Mac (Mac Studio recommended)
- **OS**: macOS 12.0+ (Monterey or later)
- **Memory**: 16GB+ recommended for multiple services

### **Demo Packages**
These are **demo packages** for demonstration:
- Show service structure and installation
- Demonstrate Apple Silicon optimization
- Provide installation framework

For **full functionality**, use Python installation:
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-macos.sh | bash
```

## ✅ **Verification**

### **Package Integrity**
```bash
sha256sum -c checksums.txt
```

### **Service Installation Test**
```bash
# Test all installed services
aitbc-node-service --version
aitbc-coordinator-service --version
aitbc-miner-service --version
```

### **Service Status**
```bash
# Check service status
aitbc-all-services status
```

## 🔄 **Service Dependencies**

### **Startup Order**
1. **Node Service** - Foundation
2. **Coordinator Service** - Job coordination
3. **Marketplace Service** - GPU marketplace
4. **Wallet Service** - Wallet operations
5. **Explorer Service** - Blockchain explorer
6. **Miner Service** - GPU mining
7. **Multimodal Service** - AI processing

### **Service Communication**
- **Node → Coordinator**: Blockchain data access
- **Coordinator → Marketplace**: Job coordination
- **Marketplace → Miner**: GPU job distribution
- **All Services → Node**: Blockchain interaction

## 📚 **Documentation**

- **[Main Documentation](../README.md)** - Complete installation guide
- **[Apple Silicon Optimization](../DEBIAN_TO_MACOS_BUILD.md)** - Build system details
- **[Package Distribution](../packages/README.md)** - Package organization

---

**Individual AITBC service packages for Mac Studio!** 🚀
EOF
    
    echo -e "${GREEN}✓ Service README created${NC}"
}

# Main function
main() {
    echo -e "${BLUE}Building individual macOS service packages...${NC}"
    echo ""
    
    # Install tools
    install_tools
    
    # Create individual service packages
    for service in "${SERVICES[@]}"; do
        IFS=':' read -r service_name service_desc <<< "$service"
        create_service_package "$service_name" "$service_desc"
    done
    
    # Create service installer
    create_service_installer
    
    # Update checksums
    update_service_checksums
    
    # Create README
    create_service_readme
    
    echo ""
    echo -e "${GREEN}🎉 Individual macOS service packages built successfully!${NC}"
    echo ""
    echo "Service packages created:"
    for service in "${SERVICES[@]}"; do
        IFS=':' read -r service_name service_desc <<< "$service"
        echo "  - $OUTPUT_DIR/$service_name-$PKG_VERSION-apple-silicon.pkg"
    done
    echo ""
    echo "Installer: $OUTPUT_DIR/install-macos-services.sh"
    echo ""
    echo "Platform: Mac Studio (Apple Silicon M1/M2/M3/M4)"
    echo ""
    echo -e "${YELLOW}⚠ These are demo packages for demonstration purposes.${NC}"
    echo -e "${YELLOW}⚠ For production packages, use the full build process.${NC}"
}

# Run main function
main "$@"
