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
