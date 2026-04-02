# AITBC1 Server Test Commands

## 🚀 **Sync and Test Instructions**

Run these commands on the **aitbc1 server** to test the workflow migration:

### **Step 1: Sync from Gitea**
```bash
# Navigate to AITBC directory
cd /opt/aitbc

# Pull latest changes from localhost aitbc (Gitea)
git pull origin main
```

### **Step 2: Run Comprehensive Test**
```bash
# Execute the automated test script
./scripts/testing/aitbc1_sync_test.sh
```

### **Step 3: Manual Verification (Optional)**
```bash
# Check that pre-commit config is gone
ls -la .pre-commit-config.yaml
# Should show: No such file or directory

# Check workflow files exist
ls -la .windsurf/workflows/
# Should show: code-quality.md, type-checking-ci-cd.md, etc.

# Test git operations (no warnings)
echo "test" > test_file.txt
git add test_file.txt
git commit -m "test: verify no pre-commit warnings"
git reset --hard HEAD~1
rm test_file.txt

# Test type checking
./scripts/type-checking/check-coverage.sh

# Test MyPy
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/job.py
```

## 📋 **Expected Results**

### ✅ **Successful Sync**
- Git pull completes without errors
- Latest workflow files are available
- No pre-commit configuration file

### ✅ **No Pre-commit Warnings**
- Git add/commit operations work silently
- No "No .pre-commit-config.yaml file was found" messages
- Clean git operations

### ✅ **Workflow System Working**
- Type checking script executes
- MyPy runs on domain models
- Workflow documentation accessible

### ✅ **File Organization**
- `.windsurf/workflows/` contains workflow files
- `scripts/type-checking/` contains type checking tools
- `config/quality/` contains quality configurations

## 🔧 **Debugging**

### **If Git Pull Fails**
```bash
# Check remote configuration
git remote -v

# Force pull if needed
git fetch origin main
git reset --hard origin/main
```

### **If Type Checking Fails**
```bash
# Check dependencies
./venv/bin/pip install mypy sqlalchemy sqlmodel fastapi

# Check script permissions
chmod +x scripts/type-checking/check-coverage.sh

# Run manually
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/
```

### **If Pre-commit Warnings Appear**
```bash
# Check if pre-commit is still installed
./venv/bin/pre-commit --version

# Uninstall if needed
./venv/bin/pre-commit uninstall

# Check git config
git config --get pre-commit.allowMissingConfig
# Should return: true
```

## 📊 **Test Checklist**

- [ ] Git pull from Gitea successful
- [ ] No pre-commit warnings on git operations
- [ ] Workflow files present in `.windsurf/workflows/`
- [ ] Type checking script executable
- [ ] MyPy runs without errors
- [ ] Documentation accessible
- [ ] No `.pre-commit-config.yaml` file
- [ ] All tests in script pass

## 🎯 **Success Indicators**

### **Green Lights**
```
[SUCCESS] Successfully pulled from Gitea
[SUCCESS] Pre-commit config successfully removed
[SUCCESS] Type checking test passed
[SUCCESS] MyPy test on job.py passed
[SUCCESS] Git commit successful (no pre-commit warnings)
[SUCCESS] AITBC1 server sync and test completed successfully!
```

### **File Structure**
```
/opt/aitbc/
├── .windsurf/workflows/
│   ├── code-quality.md
│   ├── type-checking-ci-cd.md
│   └── MULTI_NODE_MASTER_INDEX.md
├── scripts/type-checking/
│   └── check-coverage.sh
├── config/quality/
│   └── requirements-consolidated.txt
└── (no .pre-commit-config.yaml file)
```

---

**Run these commands on aitbc1 server to verify the workflow migration is working correctly!**
