# 🔄 GitHub Sync Guide for AITBC Dual Environments

## 📋 **Overview**

Maintain consistency between:
- **Localhost at1**: Development environment (`/home/oib/windsurf/aitbc`)
- **AITBC Server**: Production environment (`/opt/aitbc`)
- **GitHub**: Central repository (`oib/AITBC`)

---

## 🎯 **Recommended Workflow**

### **Development Flow:**
```
Localhost at1 → GitHub → AITBC Server
```

### **Step 1: Develop on Localhost**
```bash
# On localhost at1
cd /home/oib/windsurf/aitbc
# ... make your changes ...

# Test locally
./scripts/test_gpu_release_direct.py
aitbc --test-mode marketplace gpu list
```

### **Step 2: Push to GitHub**
```bash
# Use sync script (recommended)
./scripts/sync.sh push

# Or manual commands
git add .
git commit -m "feat: your descriptive message"
git push github main
```

### **Step 3: Deploy to Server**
```bash
# On aitbc server
ssh aitbc
cd /opt/aitbc
./scripts/sync.sh deploy

# Or manual commands
git pull github main
systemctl restart aitbc-coordinator
```

---

## 🛠️ **Sync Script Usage**

### **On Localhost at1:**
```bash
./scripts/sync.sh status    # Show current status
./scripts/sync.sh push      # Push changes to GitHub
./scripts/sync.sh pull      # Pull changes from GitHub
```

### **On AITBC Server:**
```bash
./scripts/sync.sh status    # Show current status
./scripts/sync.sh pull      # Pull changes from GitHub
./scripts/sync.sh deploy    # Pull + restart services
```

---

## 🚨 **Important Rules**

### **❌ NEVER:**
- Push directly from production server to GitHub
- Make production changes without GitHub commit
- Skip testing on localhost before deployment

### **✅ ALWAYS:**
- Use GitHub as single source of truth
- Test changes on localhost first
- Commit with descriptive messages
- Use sync script for consistency

---

## 🔄 **Sync Scenarios**

### **Scenario 1: New Feature Development**
```bash
# Localhost
git checkout -b feature/new-feature
# ... develop feature ...
git push github feature/new-feature
# Create PR, merge to main

# Server
./scripts/sync.sh deploy
```

### **Scenario 2: Bug Fix**
```bash
# Localhost
# ... fix bug ...
./scripts/sync.sh push

# Server  
./scripts/sync.sh deploy
```

### **Scenario 3: Server Configuration Fix**
```bash
# Server (emergency only)
# ... fix configuration ...
git add .
git commit -m "hotfix: server configuration"
git push github main

# Localhost
./scripts/sync.sh pull
```

---

## 📁 **File Locations**

### **Localhost at1:**
- **Working Directory**: `/home/oib/windsurf/aitbc`
- **Sync Script**: `/home/oib/windsurf/aitbc/scripts/sync.sh`
- **Database**: `./data/coordinator.db`

### **AITBC Server:**
- **Working Directory**: `/opt/aitbc`
- **Sync Script**: `/opt/aitbc/scripts/sync.sh`
- **Database**: `/opt/aitbc/apps/coordinator-api/data/coordinator.db`
- **Service**: `systemctl status aitbc-coordinator`

---

## 🔍 **Verification Commands**

### **After Deployment:**
```bash
# Check service status
systemctl status aitbc-coordinator

# Test API endpoints
curl -s "http://localhost:8000/v1/marketplace/gpu/list"
curl -s -X POST "http://localhost:8000/v1/marketplace/gpu/{id}/release"

# Check logs
journalctl -u aitbc-coordinator --since "5 minutes ago"
```

---

## 🚀 **Quick Start Commands**

### **First Time Setup:**
```bash
# On localhost
git remote add github https://github.com/oib/AITBC.git
./scripts/sync.sh status

# On server
git remote add github https://github.com/oib/AITBC.git
./scripts/sync.sh status
```

### **Daily Workflow:**
```bash
# Localhost development
./scripts/sync.sh pull  # Get latest
# ... make changes ...
./scripts/sync.sh push  # Share changes

# Server deployment
./scripts/sync.sh deploy  # Deploy and restart
```

---

## 🎊 **Benefits**

### **Consistency:**
- Both environments always in sync
- Single source of truth (GitHub)
- Version control for all changes

### **Safety:**
- Changes tested before deployment
- Rollback capability via git
- Clear commit history

### **Efficiency:**
- Automated sync script
- Quick deployment commands
- Status monitoring

---

## 📞 **Troubleshooting**

### **Common Issues:**

#### **"Don't push from production server!"**
```bash
# Solution: Make changes on localhost, not server
# Or use emergency hotfix procedure
```

#### **Merge conflicts:**
```bash
# Solution: Resolve conflicts, then commit
git pull github main
# ... resolve conflicts ...
git add .
git commit -m "resolve: merge conflicts"
git push github main
```

#### **Service won't restart:**
```bash
# Check logs
journalctl -u aitbc-coordinator --since "1 minute ago"
# Fix configuration issue
systemctl restart aitbc-coordinator
```

---

**🎉 With this workflow, both environments stay perfectly synchronized!**
