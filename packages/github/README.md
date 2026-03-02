# AITBC CLI & Services - GitHub Ready Packages

![AITBC](https://img.shields.io/badge/AITBC-CLI%20%26%20Services-blue)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
![Native macOS](https://img.shields.io/badge/macOS-Native%20Packages-green)
![License](https://img.shields.io/badge/License-MIT-green)

## 🚀 **Quick Start for GitHub Cloners**

### **One-Command Installation**

```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install.sh | bash
```

### **Manual Installation**

```bash
git clone https://github.com/aitbc/aitbc.git
cd aitbc/packages/github
./install.sh
```

## 📦 **Available Packages**

### **CLI Packages**
- `aitbc-cli_0.1.0_all.deb` - Main CLI package (132KB)

### **Service Packages**
- `aitbc-node-service_0.1.0_all.deb` - Blockchain node (8.4KB)
- `aitbc-coordinator-service_0.1.0_all.deb` - Coordinator API (8.4KB)
- `aitbc-miner-service_0.1.0_all.deb` - GPU miner (8.4KB)
- `aitbc-marketplace-service_0.1.0_all.deb` - Marketplace (8.4KB)
- `aitbc-explorer-service_0.1.0_all.deb` - Explorer (8.4KB)
- `aitbc-wallet-service_0.1.0_all.deb` - Wallet service (8.4KB)
- `aitbc-multimodal-service_0.1.0_all.deb` - Multimodal AI (8.4KB)
- `aitbc-all-services_0.1.0_all.deb` - Complete stack (8.4KB)

## 🎯 **Installation Options**

### **Option 1: CLI Only**
```bash
./install.sh --cli-only
```

### **Option 2: Services Only**
```bash
./install.sh --services-only
```

### **Option 3: Complete Installation**
```bash
./install.sh --complete
```

### **Option 4: Custom Selection**
```bash
./install.sh --packages aitbc-cli,aitbc-node-service,aitbc-miner-service
```

## 🖥️ **Platform Support**

### **Linux (Debian/Ubuntu)**
```bash
# Debian 13 Trixie, Ubuntu 24.04+
sudo apt-get update
sudo apt-get install -y python3.13 python3.13-venv python3-pip
./install.sh
```

### **macOS (Mac Studio - Apple Silicon)**
```bash
# Apple Silicon (M1/M2/M3/M4) - Mac Studio optimized
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/install-macos-complete.sh | bash

# Alternative: Homebrew (when available)
brew install aitbc-cli
```

### **Windows (WSL2)**
```bash
# Windows 10/11 with WSL2
wsl --install -d Debian
./install.sh
```

## 🔧 **System Requirements**

### **Minimum Requirements**
- **OS:** Debian 13, Ubuntu 24.04+, or compatible
- **Python:** 3.13+ (auto-installed on Linux)
- **Memory:** 2GB RAM minimum
- **Storage:** 1GB free space
- **Network:** Internet connection for dependencies

### **Recommended Requirements**
- **OS:** Debian 13 Trixie
- **Python:** 3.13+
- **Memory:** 8GB RAM
- **Storage:** 10GB free space
- **GPU:** NVIDIA CUDA (for mining services)

## 🛠️ **Installation Script Features**

### **Automatic Detection**
- OS detection and compatibility check
- Python version verification
- Dependency installation
- Service user creation
- Permission setup

### **Package Management**
- Dependency resolution
- Conflict detection
- Rollback capability
- Version verification

### **Post-Installation**
- Service configuration
- Log rotation setup
- Health checks
- System integration

## 📁 **Repository Structure**

```
aitbc/
├── packages/github/
│   ├── install.sh              # Main installer
│   ├── install-macos.sh        # macOS installer
│   ├── install-windows.sh      # Windows/WSL installer
│   ├── packages/               # Package distribution
│   │   ├── debian-packages/    # Linux/Debian packages
│   │   └── macos-packages/     # macOS packages (CLI + Services)
│   ├── README.md               # Main documentation
│   └── docs/                   # Additional documentation
├── cli/                        # CLI source
├── systemd/                    # Service definitions
└── docs/                       # Full documentation
```

## **Update Management**

### **Update CLI**
```bash
./install.sh --update-cli
```

### **Update Services**
```bash
./install.sh --update-services
```

### **Complete Update**
```bash
./install.sh --update-all
```

## 🗑️ **Uninstallation**

### **Complete Removal**
```bash
./install.sh --uninstall-all
```

### **CLI Only**
```bash
./install.sh --uninstall-cli
```

### **Services Only**
```bash
./install.sh --uninstall-services
```

## 🧪 **Testing Installation**

### **CLI Test**
```bash
aitbc --version
aitbc --help
aitbc wallet balance
```

### **Services Test**
```bash
sudo systemctl status aitbc-node.service
sudo journalctl -u aitbc-node.service -f
```

### **Health Check**
```bash
./install.sh --health-check
```

## 🌐 **Network Configuration**

### **Default Ports**
- **Node:** 30333 (P2P), 8545 (RPC)
- **Coordinator:** 8000 (API)
- **Marketplace:** 8001 (API)
- **Explorer:** 3000 (Web), 3001 (API)
- **Wallet:** 8002 (API)
- **Multimodal:** 8003 (API)

### **Firewall Setup**
```bash
# Open required ports
sudo ufw allow 30333
sudo ufw allow 8000:8003/tcp
sudo ufw allow 3000:3001/tcp
```

## 🔒 **Security Considerations**

### **Package Verification**
```bash
# Verify package checksums
sha256sum -c checksums.txt
```

### **Security Setup**
```bash
# Create dedicated user
sudo useradd -r -s /usr/sbin/nologin aitbc

# Set proper permissions
sudo chown -R aitbc:aitbc /var/lib/aitbc
sudo chmod 755 /var/lib/aitbc
```

## 📊 **Performance Tuning**

### **CLI Optimization**
```bash
# Enable shell completion
echo 'source /usr/share/aitbc/completion/aitbc_completion.sh' >> ~/.bashrc

# Set up aliases
echo 'alias aitbc="source /opt/aitbc/venv/bin/activate && aitbc"' >> ~/.bashrc
```

### **Service Optimization**
```bash
# Optimize systemd services
sudo systemctl edit aitbc-node.service
# Add:
# [Service]
# LimitNOFILE=65536
# LimitNPROC=4096
```

## 🐛 **Troubleshooting**

### **Common Issues**
1. **Python Version Issues**
   ```bash
   python3 --version  # Should be 3.13+
   ```

2. **Permission Issues**
   ```bash
   sudo chown -R aitbc:aitbc /var/lib/aitbc
   ```

3. **Service Failures**
   ```bash
   sudo journalctl -u aitbc-node.service -f
   ```

4. **Network Issues**
   ```bash
   sudo netstat -tlnp | grep :8000
   ```

### **Get Help**
```bash
# Check logs
./install.sh --logs

# Run diagnostics
./install.sh --diagnose

# Reset installation
./install.sh --reset
```

## 📚 **Documentation**

- **[Full Documentation](https://docs.aitbc.dev)**
- **[Package Distribution](packages/README.md)** - Package structure and installation
- **[macOS Packages](packages/macos-packages/README.md)** - macOS CLI and Services
- **[API Reference](https://api.aitbc.dev)**
- **[Community Forum](https://community.aitbc.dev)**
- **[GitHub Issues](https://github.com/aitbc/aitbc/issues)**

## 🤝 **Contributing**

### **Development Setup**
```bash
git clone https://github.com/aitbc/aitbc.git
cd aitbc
./packages/github/install.sh --dev
```

### **Building Packages**
```bash
./packages/github/build-all.sh
```

### **Testing**
```bash
./packages/github/test.sh
```

## 📄 **License**

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- Debian packaging community
- Python packaging tools
- Systemd service standards
- Open source contributors

---

**🚀 Ready to deploy AITBC CLI and Services on any system!**
