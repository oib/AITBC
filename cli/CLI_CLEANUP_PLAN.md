# CLI Directory Cleanup Plan

## Current Issues Identified

### **Files in Root Directory (Should be Organized)**
- `client.py` - Client functionality (should be in examples or scripts)
- `client_enhanced.py` - Enhanced client (should be in examples or scripts)
- `gpu_test.py` - GPU testing (should be in tests/)
- `miner_gpu_test.py` - GPU miner testing (should be in tests/)
- `miner.py` - Miner functionality (should be in examples or scripts)
- `test_exchange_e2e.py` - E2E test (should be in tests/)
- `test_gpu_access.py` - GPU access test (should be in tests/)
- `test_gpu_marketplace_bids.py` - GPU marketplace test (should be in tests/)
- `test_ollama_blockchain.py` - Ollama blockchain test (should be in tests/)
- `test_ollama_gpu_provider.py` - Ollama GPU provider test (should be in tests/)
- `test_workflow.py` - Workflow test (should be in tests/)
- `wallet.py` - Wallet functionality (should be in examples or scripts)

### **Cleanup Strategy**

#### **1. Create Proper Directory Structure**
```
cli/
├── aitbc_cli/           # Main CLI package (keep as is)
├── examples/            # Example scripts and standalone tools
│   ├── client.py
│   ├── client_enhanced.py
│   ├── miner.py
│   └── wallet.py
├── tests/               # Test files
│   ├── gpu/
│   │   ├── gpu_test.py
│   │   ├── miner_gpu_test.py
│   │   ├── test_gpu_access.py
│   │   └── test_gpu_marketplace_bids.py
│   ├── integration/
│   │   ├── test_exchange_e2e.py
│   │   └── test_workflow.py
│   └── ollama/
│       ├── test_ollama_blockchain.py
│       └── test_ollama_gpu_provider.py
├── scripts/             # Utility scripts
├── docs/                # Documentation
├── man/                 # Man pages (keep as is)
├── README.md            # Documentation (keep as is)
├── requirements.txt     # Dependencies (keep as is)
├── setup.py            # Setup script (keep as is)
└── aitbc_shell_completion.sh  # Shell completion (keep as is)
```

#### **2. File Categories**
- **Examples**: Standalone scripts demonstrating CLI usage
- **Tests**: All test files organized by type
- **Scripts**: Utility scripts
- **Documentation**: Documentation files
- **Core**: Main CLI package (aitbc_cli/)

#### **3. Benefits of Cleanup**
- Better organization and maintainability
- Clear separation of concerns
- Easier to find specific functionality
- Professional project structure
- Easier testing and development

## Execution Steps

1. Create new directory structure
2. Move files to appropriate directories
3. Update any imports if needed
4. Update documentation
5. Verify everything works
