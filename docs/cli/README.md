# AITBC CLI Documentation

**Updated**: 2026-03-26  
**Status**: Active Development - CLI Design Principles Applied  
**Structure**: Consolidated and Organized  

## 📁 Documentation Structure

### 🚀 [Main CLI Guide](README.md)
- Installation and setup
- Quick start guide
- Command reference
- Configuration

### 📚 [Implementation Documentation](implementation/)
- [Agent Communication Implementation](implementation/AGENT_COMMUNICATION_IMPLEMENTATION_SUMMARY.md)
- [Analytics Implementation](implementation/ANALYTICS_IMPLEMENTATION_SUMMARY.md)  
- [Deployment Implementation](implementation/DEPLOYMENT_IMPLEMENTATION_SUMMARY.md)
- [Marketplace Implementation](implementation/MARKETPLACE_IMPLEMENTATION_SUMMARY.md)
- [Multi-Chain Implementation](implementation/MULTICHAIN_IMPLEMENTATION_SUMMARY.md)

### 📊 [Analysis & Reports](analysis/)
- [CLI Wallet Daemon Integration](analysis/CLI_WALLET_DAEMON_INTEGRATION_SUMMARY.md)
- [Implementation Complete Summary](analysis/IMPLEMENTATION_COMPLETE_SUMMARY.md)
- [Localhost Only Enforcement](analysis/LOCALHOST_ONLY_ENFORCEMENT_SUMMARY.md)
- [Node Integration](analysis/NODE_INTEGRATION_SUMMARY.md)
- [Wallet Chain Connection](analysis/WALLET_CHAIN_CONNECTION_SUMMARY.md)

### 🛠️ [Installation & Setup Guides](guides/)
- [Quick Install Guide](guides/QUICK_INSTALL_GUIDE.md)
- [Local Package README](guides/LOCAL_PACKAGE_README.md)
- [CLI Test Results](guides/CLI_TEST_RESULTS.md)

### 🗃️ [Legacy Documentation](legacy/)
Historical documentation from previous development phases. Retained for reference but may contain outdated information.

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/aitbc/aitbc.git
cd aitbc/cli

# Install in development mode (flat structure)
pip install -e .

# Or use the virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### Basic Usage

```bash
# Check CLI is working
aitbc --help

# Set up API key
export AITBC_API_KEY=your_api_key_here
aitbc config set api_key your_api_key_here

# Check wallet balance
aitbc wallet balance

# Submit a job
aitbc client submit --prompt "Generate an image" --model llama2

# Check miner status
aitbc miner status
```

---

## 🎯 Recent Changes (2026-03-26)

### ✅ CLI Design Principles Applied
- **Removed embedded servers** - CLI now controls services instead of hosting them
- **Flattened directory structure** - Eliminated "box in a box" nesting
- **Simplified HTTP clients** - Replaced async pools with basic calls
- **Removed blocking loops** - Single status checks instead of infinite monitoring
- **No auto-opening browsers** - Provides URLs for user control
- **Removed system calls** - CLI provides instructions instead of executing

### 📁 Documentation Consolidation
- **Merged** `/cli/docs` into `/docs/cli` for single source of truth
- **Organized** into implementation, analysis, guides, and legacy sections
- **Updated** installation instructions for flat structure
- **Purged** duplicate and outdated documentation

---

## 🔗 Related Documentation

- [Main AITBC Documentation](../README.md)
- [Project File Structure](../1_project/1_files.md)
- [Development Roadmap](../1_project/2_roadmap.md)

---

*Last updated: 2026-03-26*  
*CLI Version: 0.2.0*  
*Python: 3.13.5+*
