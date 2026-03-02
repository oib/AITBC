#!/bin/bash

# AITBC CLI & Services Universal Installer
# Supports Linux, macOS, and Windows (WSL2)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script information
SCRIPT_VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGES_DIR="$SCRIPT_DIR/packages"
CONFIGS_DIR="$SCRIPT_DIR/configs"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

# Default options
INSTALL_CLI=true
INSTALL_SERVICES=false
COMPLETE_INSTALL=false
UNINSTALL=false
UPDATE=false
HEALTH_CHECK=false
PLATFORM="linux"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --cli-only)
            INSTALL_CLI=true
            INSTALL_SERVICES=false
            shift
            ;;
        --services-only)
            INSTALL_CLI=false
            INSTALL_SERVICES=true
            shift
            ;;
        --complete)
            INSTALL_CLI=true
            INSTALL_SERVICES=true
            COMPLETE_INSTALL=true
            shift
            ;;
        --packages)
            IFS=',' read -ra PACKAGES <<< "$2"
            INSTALL_CLI=false
            INSTALL_SERVICES=false
            CUSTOM_PACKAGES=true
            shift 2
            ;;
        --macos)
            PLATFORM="macos"
            shift
            ;;
        --windows)
            PLATFORM="windows"
            shift
            ;;
        --uninstall-all)
            UNINSTALL=true
            shift
            ;;
        --uninstall-cli)
            UNINSTALL=true
            UNINSTALL_CLI_ONLY=true
            shift
            ;;
        --uninstall-services)
            UNINSTALL=true
            UNINSTALL_SERVICES_ONLY=true
            shift
            ;;
        --update-cli)
            UPDATE=true
            UPDATE_CLI=true
            shift
            ;;
        --update-services)
            UPDATE=true
            UPDATE_SERVICES=true
            shift
            ;;
        --update-all)
            UPDATE=true
            UPDATE_ALL=true
            shift
            ;;
        --health-check)
            HEALTH_CHECK=true
            shift
            ;;
        --diagnose)
            DIAGNOSE=true
            shift
            ;;
        --logs)
            SHOW_LOGS=true
            shift
            ;;
        --reset)
            RESET=true
            shift
            ;;
        --dev)
            DEV_MODE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--version)
            echo "AITBC Universal Installer v$SCRIPT_VERSION"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Show help
show_help() {
    echo -e "${BLUE}AITBC CLI & Services Universal Installer${NC}"
    echo "==============================================="
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Installation Options:"
    echo "  --cli-only          Install CLI only (default)"
    echo "  --services-only     Install services only"
    echo "  --complete          Install CLI and all services"
    echo "  --packages LIST     Install specific packages (comma-separated)"
    echo ""
    echo "Platform Options:"
    echo "  --macos             Force macOS installation"
    echo "  --windows           Force Windows/WSL2 installation"
    echo ""
    echo "Update Options:"
    echo "  --update-cli        Update CLI package"
    echo "  --update-services   Update service packages"
    echo "  --update-all        Update all packages"
    echo ""
    echo "Uninstall Options:"
    echo "  --uninstall-all     Uninstall CLI and all services"
    echo "  --uninstall-cli     Uninstall CLI only"
    echo "  --uninstall-services Uninstall services only"
    echo ""
    echo "Utility Options:"
    echo "  --health-check      Run health check"
    echo "  --diagnose          Run system diagnostics"
    echo "  --logs              Show installation logs"
    echo "  --reset             Reset installation"
    echo "  --dev               Development mode"
    echo ""
    echo "Help Options:"
    echo "  -h, --help          Show this help"
    echo "  -v, --version       Show version"
    echo ""
    echo "Examples:"
    echo "  $0 --cli-only                    # Install CLI only"
    echo "  $0 --complete                    # Install everything"
    echo "  $0 --packages aitbc-cli,aitbc-node-service  # Custom packages"
    echo "  $0 --health-check                # Check system health"
    echo "  $0 --uninstall-all               # Remove everything"
}

# Print banner
print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                    AITBC Universal Installer                ║"
    echo "║                      CLI & Services v$SCRIPT_VERSION                 ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Detect platform
detect_platform() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        PLATFORM="macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        PLATFORM="linux"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        PLATFORM="windows"
    fi
    
    echo -e "${BLUE}Detected platform: $PLATFORM${NC}"
}

# Check system requirements
check_requirements() {
    echo -e "${BLUE}Checking system requirements...${NC}"
    
    case $PLATFORM in
        "linux")
            check_linux_requirements
            ;;
        "macos")
            check_macos_requirements
            ;;
        "windows")
            check_windows_requirements
            ;;
    esac
}

# Check Linux requirements
check_linux_requirements() {
    # Check if running as root for service installation
    if [[ $INSTALL_SERVICES == true ]] && [[ $EUID -ne 0 ]]; then
        echo -e "${YELLOW}Service installation requires root privileges. You may be asked for your password.${NC}"
    fi
    
    # Check package manager
    if command -v apt-get >/dev/null 2>&1; then
        PKG_MANAGER="apt"
    elif command -v yum >/dev/null 2>&1; then
        PKG_MANAGER="yum"
    elif command -v dnf >/dev/null 2>&1; then
        PKG_MANAGER="dnf"
    else
        echo -e "${RED}❌ No supported package manager found${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Package manager: $PKG_MANAGER${NC}"
    
    # Check Python
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if [[ $(echo "$PYTHON_VERSION >= 3.13" | bc -l) -eq 1 ]]; then
            echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"
        else
            echo -e "${YELLOW}⚠ Python $PYTHON_VERSION found, installing 3.13+${NC}"
            install_python
        fi
    else
        echo -e "${YELLOW}⚠ Python not found, installing 3.13+${NC}"
        install_python
    fi
}

# Check macOS requirements
check_macos_requirements() {
    # Check if Homebrew is installed
    if command -v brew >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Homebrew found${NC}"
    else
        echo -e "${YELLOW}⚠ Homebrew not found, installing...${NC}"
        install_homebrew
    fi
    
    # Check Python
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if [[ $(echo "$PYTHON_VERSION >= 3.13" | bc -l) -eq 1 ]]; then
            echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"
        else
            echo -e "${YELLOW}⚠ Python $PYTHON_VERSION found, installing 3.13+${NC}"
            install_python_macos
        fi
    else
        echo -e "${YELLOW}⚠ Python not found, installing 3.13+${NC}"
        install_python_macos
    fi
}

# Check Windows requirements
check_windows_requirements() {
    # Check if WSL is available
    if command -v wsl >/dev/null 2>&1; then
        echo -e "${GREEN}✓ WSL found${NC}"
    else
        echo -e "${RED}❌ WSL not found. Please install WSL2 first.${NC}"
        echo "Visit: https://learn.microsoft.com/en-us/windows/wsl/install"
        exit 1
    fi
    
    # Check Debian in WSL
    if wsl --list --verbose | grep -q "Debian"; then
        echo -e "${GREEN}✓ Debian found in WSL${NC}"
    else
        echo -e "${YELLOW}⚠ Debian not found in WSL, installing...${NC}"
        wsl --install -d Debian
    fi
}

# Install Python on Linux
install_python() {
    case $PKG_MANAGER in
        "apt")
            sudo apt-get update
            sudo apt-get install -y python3.13 python3.13-venv python3-pip
            ;;
        "yum"|"dnf")
            sudo $PKG_MANAGER install -y python3.13 python3.13-pip
            ;;
    esac
}

# Install Homebrew on macOS
install_homebrew() {
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
}

# Install Python on macOS
install_python_macos() {
    brew install python@3.13
}

# Install CLI package
install_cli() {
    echo -e "${BLUE}Installing AITBC CLI...${NC}"
    
    local cli_package="$PACKAGES_DIR/aitbc-cli_0.1.0_all.deb"
    
    if [[ ! -f "$cli_package" ]]; then
        echo -e "${RED}❌ CLI package not found: $cli_package${NC}"
        return 1
    fi
    
    case $PLATFORM in
        "linux")
            install_deb_package "$cli_package"
            ;;
        "macos")
            install_cli_macos
            ;;
        "windows")
            install_cli_windows
            ;;
    esac
}

# Install CLI on macOS
install_cli_macos() {
    # Create virtual environment
    local venv_dir="/usr/local/aitbc"
    sudo mkdir -p "$venv_dir"
    sudo python3.13 -m venv "$venv_dir/venv"
    
    # Install CLI in virtual environment
    sudo "$venv_dir/venv/bin/pip" install --upgrade pip
    
    # Install from source (since deb packages don't work on macOS)
    if [[ -f "$SCRIPT_DIR/../../cli/dist/aitbc_cli-0.1.0-py3-none-any.whl" ]]; then
        sudo "$venv_dir/venv/bin/pip" install "$SCRIPT_DIR/../../cli/dist/aitbc_cli-0.1.0-py3-none-any.whl"
    else
        sudo "$venv_dir/venv/bin/pip" install git+https://github.com/aitbc/aitbc.git#subdirectory=cli
    fi
    
    # Create symlink
    sudo ln -sf "$venv_dir/venv/bin/aitbc" /usr/local/bin/aitbc
    
    echo -e "${GREEN}✓ AITBC CLI installed on macOS${NC}"
}

# Install CLI on Windows
install_cli_windows() {
    echo -e "${BLUE}Installing AITBC CLI in WSL...${NC}"
    
    # Run installation in WSL
    wsl -e bash -c "
        cd /mnt/c/Users/\$USER/aitbc/packages/github
        ./install.sh --cli-only
    "
}

# Install service packages
install_services() {
    echo -e "${BLUE}Installing AITBC Services...${NC}"
    
    if [[ $PLATFORM != "linux" ]]; then
        echo -e "${YELLOW}⚠ Services are only supported on Linux${NC}"
        return 1
    fi
    
    local service_packages=(
        "aitbc-node-service"
        "aitbc-coordinator-service"
        "aitbc-miner-service"
        "aitbc-marketplace-service"
        "aitbc-explorer-service"
        "aitbc-wallet-service"
        "aitbc-multimodal-service"
    )
    
    if [[ $COMPLETE_INSTALL == true ]]; then
        service_packages+=("aitbc-all-services")
    fi
    
    for package in "${service_packages[@]}"; do
        local package_file="$PACKAGES_DIR/${package}_0.1.0_all.deb"
        if [[ -f "$package_file" ]]; then
            install_deb_package "$package_file"
        else
            echo -e "${YELLOW}⚠ Service package not found: $package_file${NC}"
        fi
    done
}

# Install Debian package
install_deb_package() {
    local package_file="$1"
    
    if [[ $EUID -ne 0 ]]; then
        echo -e "${YELLOW}Installing package: $(basename "$package_file")${NC}"
        sudo dpkg -i "$package_file"
    else
        echo -e "${BLUE}Installing package: $(basename "$package_file")${NC}"
        dpkg -i "$package_file"
    fi
    
    # Fix dependencies if needed
    if [[ $? -ne 0 ]]; then
        echo -e "${YELLOW}Fixing dependencies...${NC}"
        if [[ $EUID -ne 0 ]]; then
            sudo apt-get install -f
        else
            apt-get install -f
        fi
    fi
}

# Health check
health_check() {
    echo -e "${BLUE}Running health check...${NC}"
    
    # Check CLI
    if command -v aitbc >/dev/null 2>&1; then
        echo -e "${GREEN}✓ AITBC CLI available${NC}"
        if aitbc --version >/dev/null 2>&1; then
            echo -e "${GREEN}✓ AITBC CLI working${NC}"
        else
            echo -e "${RED}❌ AITBC CLI not working${NC}"
        fi
    else
        echo -e "${RED}❌ AITBC CLI not found${NC}"
    fi
    
    # Check services (Linux only)
    if [[ $PLATFORM == "linux" ]]; then
        local services=(
            "aitbc-node.service"
            "aitbc-coordinator-api.service"
            "aitbc-gpu-miner.service"
        )
        
        for service in "${services[@]}"; do
            if systemctl is-active --quiet "$service"; then
                echo -e "${GREEN}✓ $service running${NC}"
            elif systemctl list-unit-files | grep -q "$service"; then
                echo -e "${YELLOW}⚠ $service installed but not running${NC}"
            else
                echo -e "${RED}❌ $service not found${NC}"
            fi
        done
    fi
}

# Main installation function
main() {
    print_banner
    
    if [[ $HEALTH_CHECK == true ]]; then
        detect_platform
        health_check
        exit 0
    fi
    
    if [[ $UNINSTALL == true ]]; then
        uninstall_packages
        exit 0
    fi
    
    if [[ $UPDATE == true ]]; then
        update_packages
        exit 0
    fi
    
    detect_platform
    check_requirements
    
    if [[ $INSTALL_CLI == true ]]; then
        install_cli
    fi
    
    if [[ $INSTALL_SERVICES == true ]]; then
        install_services
    fi
    
    health_check
    
    echo ""
    echo -e "${GREEN}🎉 Installation completed successfully!${NC}"
    echo ""
    echo "Quick start:"
    echo "  aitbc --help"
    echo "  aitbc wallet balance"
    echo ""
    if [[ $PLATFORM == "linux" ]] && [[ $INSTALL_SERVICES == true ]]; then
        echo "Service management:"
        echo "  sudo systemctl start aitbc-node.service"
        echo "  sudo systemctl status aitbc-node.service"
        echo ""
    fi
}

# Run main function
main "$@"
