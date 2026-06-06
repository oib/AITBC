# AITBC Packages Distribution

## 📦 **Package Structure**

```
packages/
├── debian-packages/          # Linux/Debian packages
│   ├── aitbc-cli_0.1.0_all.deb
│   ├── aitbc-node-service_0.1.0_all.deb
│   ├── aitbc-coordinator-service_0.1.0_all.deb
│   ├── aitbc-miner-service_0.1.0_all.deb
│   ├── aitbc-marketplace-service_0.1.0_all.deb
│   ├── aitbc-explorer-service_0.1.0_all.deb
│   ├── aitbc-wallet-service_0.1.0_all.deb
│   ├── aitbc-multimodal-service_0.1.0_all.deb
│   ├── aitbc-all-services_0.1.0_all.deb
│   └── checksums.txt
│
└── macos-packages/           # macOS packages (CLI + Services)
    ├── CLI Package:
    │   └── aitbc-cli-0.1.0-apple-silicon.pkg (General + GPU)
    ├── Service Packages:
    │   ├── aitbc-node-service-0.1.0-apple-silicon.pkg
    │   ├── aitbc-coordinator-service-0.1.0-apple-silicon.pkg
    │   ├── aitbc-miner-service-0.1.0-apple-silicon.pkg
    │   ├── aitbc-marketplace-service-0.1.0-apple-silicon.pkg
    │   ├── aitbc-explorer-service-0.1.0-apple-silicon.pkg
    │   ├── aitbc-wallet-service-0.1.0-apple-silicon.pkg
    │   ├── aitbc-multimodal-service-0.1.0-apple-silicon.pkg
    │   └── aitbc-all-services-0.1.0-apple-silicon.pkg
    ├── Installers:
    │   ├── install-macos-complete.sh
    │   ├── install-macos-apple-silicon.sh
    │   └── install-macos-services.sh
    └── checksums.txt
```

## 🚀 **Quick Installation**

### **Linux (Debian/Ubuntu)**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install.sh | bash
```

### **macOS (Apple Silicon)**
```bash
# Complete macOS installation (CLI + Services)
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/install-macos-complete.sh | bash

# CLI only
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/install-macos-apple-silicon.sh | bash

# Services only
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/install-macos-services.sh | bash
```

### **Windows (WSL2)**
```bash
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install-windows.sh | bash
```

## 📋 **Package Information**

### **Debian Packages**
- **Platform**: Linux (Debian/Ubuntu)
- **Format**: .deb
- **Size**: 132KB (CLI), 8KB (services)
- **Dependencies**: Python 3.13+, systemd (services)

### **macOS Packages**
- **Platform**: macOS (Intel + Apple Silicon)
- **Format**: .pkg
- **Size**: ~80MB (production), 2KB (demo)
- **Dependencies**: None (native)

## 🔧 **Manual Installation**

### **Debian Packages**
```bash
# Download
wget https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/debian-packages/aitbc-cli_0.1.0_all.deb

# Install
sudo dpkg -i aitbc-cli_0.1.0_all.deb
sudo apt-get install -f  # Fix dependencies
```

### **macOS Packages**
```bash
# Download
wget https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/packages/macos-packages/aitbc-cli-0.1.0-demo.pkg

# Install
sudo installer -pkg aitbc-cli-0.1.0-demo.pkg -target /
```

## ✅ **Verification**

### **Check Package Integrity**
```bash
# Debian packages
cd debian-packages
sha256sum -c checksums.txt

# macOS packages
cd macos-packages
sha256sum -c checksums.txt
```

### **Test Installation**
```bash
# CLI test
aitbc --version
aitbc --help

# Services test (Linux only)
sudo systemctl status aitbc-node.service
```

## 🔄 **Updates**

### **Check for Updates**
```bash
# Check current version
aitbc --version

# Update packages
curl -fsSL https://raw.githubusercontent.com/aitbc/aitbc/main/packages/github/install.sh | bash -s --update-all
```

## 📚 **Documentation**

- **[Main Documentation](../README.md)** - Complete installation guide
- **[macOS Packages](macos-packages/README.md)** - macOS-specific instructions
- **[Migration Guide](../MACOS_MIGRATION_GUIDE.md)** - From .deb to native packages
- **[Build System](../DEBIAN_TO_MACOS_BUILD.md)** - Cross-compilation setup

## 🎯 **Platform Support**

| Platform | Package Type | Installation Method |
|-----------|--------------|-------------------|
| Linux | .deb packages | `install.sh` |
| macOS | .pkg packages | `install-macos-demo.sh` |
| Windows | WSL2 + .deb | `install-windows.sh` |

## 🚀 **Development**

### **Building Packages**
```bash
# Build Debian packages
cd packages/deb
./build_deb.sh
./build_services.sh

# Build macOS packages (demo)
cd packages
./build-macos-simple.sh

# Build macOS packages (production)
cd packages
./build-macos-packages.sh
```

### **Package Structure**
- **Clean separation** by platform
- **Consistent naming** conventions
- **Checksum verification** for security
- **Automated builds** via GitHub Actions

---

**Organized package distribution for all platforms!** 🎉
