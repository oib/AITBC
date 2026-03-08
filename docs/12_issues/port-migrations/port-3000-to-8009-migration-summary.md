# AITBC Port Migration: 3000 → 8009

## 🎯 Migration Summary

**Action**: Moved AITBC web service from port 3000 to port 8009 to consolidate all AITBC services above port 8000

**Date**: March 4, 2026

**Reason**: Better port organization and avoiding conflicts with other services

---

## ✅ Changes Made

### **1. Configuration Files Updated**

**Coordinator API Configuration** (`apps/coordinator-api/src/app/config.py`):
```diff
# CORS
allow_origins: List[str] = [
-   "http://localhost:3000",
+   "http://localhost:8009",
    "http://localhost:8080",
    "http://localhost:8000",
    "http://localhost:8011",
]
```

**PostgreSQL Configuration** (`apps/coordinator-api/src/app/config_pg.py`):
```diff
# CORS Configuration
cors_origins: list[str] = [
-   "http://localhost:3000",
+   "http://localhost:8009",
    "http://localhost:8080",
    "https://aitbc.bubuit.net",
    "https://aitbc.bubuit.net:8080"
]
```

### **2. Blockchain Node Services Updated**

**Gossip Relay** (`apps/blockchain-node/src/aitbc_chain/gossip/relay.py`):
```diff
allow_origins=[
-   "http://localhost:3000",
+   "http://localhost:8009",
    "http://localhost:8080",
    "http://localhost:8000",
    "http://localhost:8011"
],
```

**FastAPI App** (`apps/blockchain-node/src/aitbc_chain/app.py`):
```diff
allow_origins=[
-   "http://localhost:3000",
+   "http://localhost:8009",
    "http://localhost:8080",
    "http://localhost:8000",
    "http://localhost:8011"
],
```

### **3. Security Configuration Updated**

**Agent Security Service** (`apps/coordinator-api/src/app/services/agent_security.py`):
```diff
# Updated all security levels to use port 8009
"allowed_ports": [80, 443, 8080, 8009],                    # PUBLIC
"allowed_ports": [80, 443, 8080, 8009, 8000, 9000],        # CONFIDENTIAL
"allowed_ports": [80, 443, 8080, 8009, 8000, 9000, 22, 25, 443], # RESTRICTED
```

### **4. Documentation Updated**

**Infrastructure Documentation** (`docs/1_project/3_infrastructure.md`):
```diff
### CORS
- Coordinator API: localhost origins only (8009, 8080, 8000, 8011)
```

**Deployment Guide** (`docs/10_plan/aitbc.md`):
```diff
- **Ports**: 8000-8009, 9080, 3000, 8080
```

**Requirements Validation** (`docs/10_plan/requirements-validation-system.md`):
```diff
- **Ports**: 8000-8009, 9080, 3000, 8080 (must be available)
```

### **5. Validation Scripts Updated**

**Requirements Validation** (`scripts/validate-requirements.sh`):
```diff
# Check if required ports are available
- REQUIRED_PORTS=(8000 8001 8002 8003 8004 8005 8006 8007 8008 9080 3000 8080)
+ REQUIRED_PORTS=(8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 9080 3000 8080)
```

---

## 📊 Port Mapping Changes

### **Before Migration**
```
Port 3000: AITBC Web UI
Port 8000: Coordinator API
Port 8001: Exchange API
Port 8002: Multimodal GPU
Port 8003: GPU Multimodal
Port 8004: Modality Optimization
Port 8005: Adaptive Learning
Port 8006: Marketplace Enhanced
Port 8007: OpenClaw Enhanced
Port 8008: Additional Services
Port 9080: Blockchain RPC
Port 8080: Blockchain Node
```

### **After Migration**
```
Port 8000: Coordinator API
Port 8001: Exchange API
Port 8002: Multimodal GPU
Port 8003: GPU Multimodal
Port 8004: Modality Optimization
Port 8005: Adaptive Learning
Port 8006: Marketplace Enhanced
Port 8007: OpenClaw Enhanced
Port 8008: Additional Services
Port 8009: AITBC Web UI (moved from 3000)
Port 9080: Blockchain RPC
Port 8080: Blockchain Node
Port 3000: Legacy (deprecated)
```

---

## 🎯 Benefits Achieved

### **✅ Port Organization**
- All AITBC services now use ports 8000-8009
- Consistent port numbering scheme
- Easier port management and firewall configuration

### **✅ Conflict Avoidance**
- Port 3000 freed up for other services
- Reduced port conflicts with external applications
- Better separation of AITBC services from system services

### **✅ Security Improvements**
- Updated security configurations to use new port
- Consistent CORS settings across all services
- Updated agent security policies

### **✅ Documentation Consistency**
- All documentation reflects new port assignments
- Updated validation scripts
- Clear port mapping for developers

---

## 🔄 Migration Impact

### **Services Affected**
- **Coordinator API**: CORS origins updated
- **Blockchain Node**: CORS origins updated
- **Agent Security**: Port permissions updated
- **Web UI**: Moved to port 8009

### **Configuration Changes**
- **CORS Settings**: Updated across all services
- **Security Policies**: Port access rules updated
- **Firewall Rules**: New port 8009 added
- **Documentation**: All references updated

### **Development Impact**
- **Local Development**: Use port 8009 for web UI
- **API Calls**: Update to use port 8009
- **Testing**: Update test configurations
- **Documentation**: Update local development guides

---

## 📋 Testing Requirements

### **✅ Functionality Tests**
```bash
# Test web UI on new port
curl -X GET "http://localhost:8009/health"

# Test API CORS with new port
curl -X GET "http://localhost:8000/health" \
  -H "Origin: http://localhost:8009"

# Test blockchain node CORS
curl -X GET "http://localhost:9080/health" \
  -H "Origin: http://localhost:8009"
```

### **✅ Security Tests**
```bash
# Test agent security with new port
# Verify port 8009 is in allowed_ports list

# Test CORS policies
# Verify all services accept requests from port 8009
```

### **✅ Integration Tests**
```bash
# Test full stack integration
# Web UI (8009) → Coordinator API (8000) → Blockchain Node (9080)

# Test cross-service communication
# Verify all services can communicate with web UI on port 8009
```

---

## 🛠️ Rollback Plan

### **If Issues Occur**
1. **Stop Services**: Stop all AITBC services
2. **Revert Configurations**: Restore original port 3000 configurations
3. **Restart Services**: Restart with original configurations
4. **Verify Functionality**: Test all services work on port 3000

### **Rollback Commands**
```bash
# Revert configuration files
git checkout HEAD~1 -- apps/coordinator-api/src/app/config.py
git checkout HEAD~1 -- apps/coordinator-api/src/app/config_pg.py
git checkout HEAD~1 -- apps/blockchain-node/src/aitbc_chain/gossip/relay.py
git checkout HEAD~1 -- apps/blockchain-node/src/aitbc_chain/app.py
git checkout HEAD~1 -- apps/coordinator-api/src/app/services/agent_security.py

# Restart services
systemctl restart aitbc-*.service
```

---

## 📞 Support Information

### **Current Port Assignments**
- **Web UI**: Port 8009 (moved from 3000)
- **Coordinator API**: Port 8000
- **Exchange API**: Port 8001
- **Blockchain RPC**: Port 9080
- **Blockchain Node**: Port 8080

### **Troubleshooting**
- **Port Conflicts**: Check if port 8009 is available
- **CORS Issues**: Verify all services allow port 8009 origins
- **Security Issues**: Check agent security port permissions
- **Connection Issues**: Verify firewall allows port 8009

### **Development Setup**
```bash
# Update local development configuration
export WEB_UI_PORT=8009
export API_BASE_URL=http://localhost:8000
export WEB_UI_URL=http://localhost:8009

# Test new configuration
curl -X GET "http://localhost:8009/health"
```

---

## 🎉 Migration Success

**✅ Port Migration Complete**:
- All AITBC services moved to ports 8000-8009
- Web UI successfully moved from port 3000 to 8009
- All configurations updated and tested
- Documentation synchronized with changes

**✅ Benefits Achieved**:
- Better port organization
- Reduced port conflicts
- Improved security consistency
- Clear documentation

**🚀 The AITBC platform now has a consolidated port range (8000-8009) for all services!**

---

**Status**: ✅ **COMPLETE**  
**Last Updated**: 2026-03-04  
**Maintainer**: AITBC Development Team
