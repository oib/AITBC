# AITBC Architecture Documentation

This directory contains comprehensive architecture documentation for the AITBC platform, covering system components, data flows, and technical implementation details.

## 📚 **Document Structure**

### **Core Architecture Documents**

1. **[1_system-flow.md](./1_system-flow.md)** - System flow diagrams and data flow architecture
2. **[2_components-overview.md](./2_components-overview.md)** - High-level component overview and interactions
3. **[3_coordinator-api.md](./3_coordinator-api.md)** - Coordinator API architecture and endpoints
4. **[4_blockchain-node.md](./4_blockchain-node.md)** - Blockchain node architecture and consensus
5. **[5_marketplace-web.md](./5_marketplace-web.md)** - Marketplace web application architecture
6. **[6_trade-exchange.md](./6_trade-exchange.md)** - Trade exchange and matching engine
7. **[7_wallet.md](./7_wallet.md)** - Wallet architecture and key management
8. **[8_codebase-structure.md](./8_codebase-structure.md)** - Codebase organization and module structure
9. **[9_full-technical-reference.md](./9_full-technical-reference.md)** - Complete technical reference

### **Specialized Architecture**

- **[edge_gpu_setup.md](./edge_gpu_setup.md)** - Edge computing and GPU setup architecture
- **[EXPLORER_MERGE_SUMMARY.md](./EXPLORER_MERGE_SUMMARY.md)** - Historical decision record: merging TypeScript explorer into Python blockchain-explorer

## 🎯 **Quick Start**

### **For New Developers**
Start with these documents in order:
1. [2_components-overview.md](./2_components-overview.md) - Understand the big picture
2. [1_system-flow.md](./1_system-flow.md) - Learn how data flows through the system
3. [8_codebase-structure.md](./8_codebase-structure.md) - Navigate the codebase

### **For System Architects**
Focus on these documents:
1. [3_coordinator-api.md](./3_coordinator-api.md) - API architecture
2. [4_blockchain-node.md](./4_blockchain-node.md) - Blockchain architecture
3. [9_full-technical-reference.md](./9_full-technical-reference.md) - Complete technical details

### **For Infrastructure Engineers**
Review these documents:
1. [edge_gpu_setup.md](./edge_gpu_setup.md) - Edge computing setup
2. [6_trade-exchange.md](./6_trade-exchange.md) - Exchange infrastructure
3. [7_wallet.md](./7_wallet.md) - Wallet infrastructure

## 🔗 **Related Documentation**

- **[../README.md](../README.md)** - Main documentation index
- **[../MASTER_INDEX.md](../MASTER_INDEX.md)** - Master documentation index
- **[../blockchain/](../blockchain/)** - Blockchain-specific documentation
- **[../contracts/](../contracts/)** - Smart contract documentation
- **[../deployment/](../deployment/)** - Deployment and infrastructure

## 📊 **Architecture Overview**

### **System Components**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Coordinator    │    │  Blockchain     │    │  Marketplace    │
│  API (8203)     │◄──►│  Node (8202)    │◄──►│  Web (8001)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                      │                      │
        └──────────────────────┴──────────────────────┘
                               │
                    ┌───────────┴───────────┐
                    │                       │
              ┌─────┴─────┐         ┌─────┴─────┐
              │  Wallet   │         │  Exchange │
              │  Service  │         │  Service  │
              └───────────┘         └───────────┘
```

### **Key Technologies**

- **Blockchain**: Custom AITBC blockchain with Proof-of-Stake consensus
- **API**: FastAPI-based coordinator API
- **Frontend**: React-based marketplace web application
- **Wallet**: Python-based wallet service with cryptography
- **Exchange**: Matching engine for token trading
- **Edge Computing**: GPU resource management for AI workloads

### **Unit System**

The AITBC blockchain uses a compute-seconds based unit system:
- **1 AIT = 3600 seconds** (1 hour of compute)
- All on-chain values are stored as integer seconds
- User interfaces convert seconds → AIT for display
- This enables precise second-level billing for AI compute

See [4_blockchain-node.md](./4_blockchain-node.md) for implementation details.

## 🚀 **Development Workflow**

### **Adding New Architecture Documents**

1. Create new markdown file in this directory
2. Follow naming convention: `number_title.md`
3. Update this README to include the new document
4. Add cross-references to related documents
5. Commit and push changes

### **Updating Architecture Documents**

1. Make changes to the relevant document
2. Update cross-references if needed
3. Update version number and date
4. Commit with descriptive message
5. Sync changes across all nodes

## 📝 **Documentation Standards**

- **Format**: Markdown with proper heading hierarchy
- **Diagrams**: Use ASCII art or mermaid for diagrams
- **Code Examples**: Include working code snippets
- **Cross-References**: Link to related documents
- **Version Control**: Track document versions and dates
- **Language**: English, clear and concise

## 🔍 **Search and Navigation**

### **Finding Specific Information**

- Use the [MASTER_INDEX](../MASTER_INDEX.md) for comprehensive navigation
- Search within this directory for specific topics
- Follow cross-references between documents
- Check the table of contents in each document

### **Document Categories**

- **System Architecture**: Overall system design and components
- **Component Architecture**: Individual component details
- **Infrastructure**: Deployment and infrastructure setup
- **Integration**: Component integration and communication
- **Reference**: Complete technical reference material

## 📞 **Support and Contributions**

### **Getting Help**

- Check the [main documentation README](../README.md)
- Review the [MASTER_INDEX](../MASTER_INDEX.md)
- Search existing issues in the repository
- Contact the development team

### **Contributing**

1. Fork the repository
2. Create a feature branch
3. Make your documentation changes
4. Test links and cross-references
5. Submit a pull request

---

**Last Updated**: 2026-05-08
**Version**: 1.0
**Status**: Active documentation
