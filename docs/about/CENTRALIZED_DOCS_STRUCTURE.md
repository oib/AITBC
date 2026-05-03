# Centralized Documentation Structure

**Created**: 2026-03-26  
**Status**: All documentation folders centralized via symlinks  

## 📁 Centralized Documentation Structure

All documentation is now accessible from the central `/docs` directory through symlinks:

```
/opt/aitbc/docs/
├── README.md                           # Main documentation index
├── blockchain/                         # Blockchain documentation
│   ├── README.md                      # Blockchain docs overview
│   └── node -> /opt/aitbc/apps/blockchain-node/docs/  # Symlink to app docs
├── cli/                              # CLI documentation
├── cli/                              # CLI documentation
├── contracts -> /opt/aitbc/contracts/docs/  # Symlink to contracts docs
├── testing -> /opt/aitbc/tests/docs/   # Symlink to test documentation
├── website -> /opt/aitbc/website/docs/  # Symlink to website docs
└── [other existing docs directories...] # Existing docs structure
```

## 🔗 Symlink Details

### **Blockchain Node Documentation**
- **Source**: `/opt/aitbc/apps/blockchain-node/docs/`
- **Symlink**: `/opt/aitbc/docs/blockchain/node`
- **Content**: `SCHEMA.md` - Blockchain node schema documentation

### **CLI Beginner Documentation**  
- **Location**: `/opt/aitbc/docs/cli/`
- **Content**: 
  - `README.md` - Comprehensive CLI guide for beginners
  - `permission-setup.md` - CLI permission setup
  - `testing.md` - CLI testing guide

### **CLI Technical Documentation**  
- **Source**: `/opt/aitbc/cli/docs/`
- **Symlink**: `/opt/aitbc/docs/cli`
- **Content**: 
  - `README.md` - CLI technical documentation
  - `DISABLED_COMMANDS_CLEANUP.md` - Cleanup analysis
  - `FILE_ORGANIZATION_SUMMARY.md` - Organization summary

### **Contracts Documentation**
- **Source**: `/opt/aitbc/contracts/docs/`
- **Symlink**: `/opt/aitbc/docs/contracts`  
- **Content**: `ZK-VERIFICATION.md` - Zero-knowledge verification docs

### **Testing Documentation**
- **Source**: `/opt/aitbc/tests/docs/`
- **Symlink**: `/opt/aitbc/docs/testing`
- **Content**:
  - `README.md` - Testing overview
  - `TEST_REFACTORING_COMPLETED.md` - Refactoring completion
  - `USAGE_GUIDE.md` - Test usage guide
  - `cli-test-updates-completed.md` - CLI test updates
  - `test-integration-completed.md` - Integration test status

### **Website Documentation**
- **Source**: `/opt/aitbc/website/docs/`
- **Symlink**: `/opt/aitbc/docs/website`
- **Content**: HTML documentation files for web interface

## ✅ Benefits

### **🎯 Centralized Access**
- **Single entry point**: All docs accessible from `/docs`
- **Logical organization**: Docs grouped by category
- **Easy navigation**: Clear structure for finding documentation

### **🔄 Live Updates**
- **Symlinks**: Changes in source locations immediately reflected
- **No duplication**: Single source of truth for each documentation set
- **Automatic sync**: No manual copying required

### **📁 Clean Structure**
- **Maintained organization**: Original docs stay in their logical locations
- **Central access point**: `/docs` serves as documentation hub
- **Preserved context**: Docs remain with their respective components

## 🚀 Usage

### **Access Documentation:**
```bash
# Blockchain node docs
ls /opt/aitbc/docs/blockchain/node/

# CLI docs
ls /opt/aitbc/docs/cli/

# Contracts docs
ls /opt/aitbc/docs/contracts/

# Testing docs
ls /opt/aitbc/docs/testing/

# Website docs
ls /opt/aitbc/docs/website/
```

### **Update Documentation:**
- Edit files in their original locations
- Changes automatically appear through symlinks
- No need to update multiple copies

## 🎯 Verification

All symlinks have been tested and confirmed working:
- ✅ `/docs/blockchain/node` → `/apps/blockchain-node/docs`
- ✅ `/docs/cli/` - CLI documentation (merged from cli-technical)
- ✅ `/docs/contracts` → `/contracts/docs`
- ✅ `/docs/testing` → `/tests/docs`
- ✅ `/docs/website` → `/website/docs`

---

*Last updated: 2026-03-26*  
*Status: Successfully centralized all documentation*
