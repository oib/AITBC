# Developer File Organization Guidelines

## 📁 Where to Put Files

### Essential Root Files (Keep at Root)
- `.editorconfig` - Editor configuration
- `.env.example` - Environment template
- `.gitignore` - Git ignore rules
- `LICENSE` - Project license
- `README.md` - Project documentation
- `pyproject.toml` - Python project configuration
- `poetry.lock` - Dependency lock file
- `pytest.ini` - Test configuration
- `run_all_tests.sh` - Main test runner

### Development Scripts → `dev/scripts/`
```bash
# Development fixes and patches
dev/scripts/fix_*.py
dev/scripts/fix_*.sh
dev/scripts/patch_*.py
dev/scripts/simple_test.py
```

### Test Files → `dev/tests/`
```bash
# Test scripts and scenarios
dev/tests/test_*.py
dev/tests/test_*.sh
dev/tests/test_scenario_*.sh
dev/tests/run_mc_test.sh
dev/tests/simple_test_results.json
```

### Multi-Chain Testing → `dev/multi-chain/`
```bash
# Multi-chain specific files
dev/multi-chain/MULTI_*.md
dev/multi-chain/test_multi_chain*.py
dev/multi-chain/test_multi_site.py
```

### Configuration Files → `config/`
```bash
# Configuration and environment files
config/.aitbc.yaml
config/.aitbc.yaml.example
config/.env.production
config/.nvmrc
config/.lycheeignore
```

### Development Environment → `dev/env/`
```bash
# Environment directories
dev/env/node_modules/
dev/env/.venv/
dev/env/cli_env/
dev/env/package.json
dev/env/package-lock.json
```

### Cache and Temporary → `dev/cache/`
```bash
# Cache and temporary directories
dev/cache/.pytest_cache/
dev/cache/.ruff_cache/
dev/cache/logs/
dev/cache/.vscode/
```

## 🚀 Quick Start Commands

### Creating New Files
```bash
# Create a new test script
touch dev/tests/test_my_feature.py

# Create a new development script
touch dev/scripts/fix_my_issue.py

# Create a new patch script
touch dev/scripts/patch_component.py
```

### Checking Organization
```bash
# Check current file organization
./scripts/check-file-organization.sh

# Auto-fix organization issues
./scripts/move-to-right-folder.sh --auto
```

### Git Integration
```bash
# Git will automatically check file locations on commit
git add .
git commit -m "My changes"  # Will run pre-commit hooks
```

## ⚠️ Common Mistakes to Avoid

### ❌ Don't create these files at root:
- `test_*.py` or `test_*.sh` → Use `dev/tests/`
- `patch_*.py` or `fix_*.py` → Use `dev/scripts/`
- `MULTI_*.md` → Use `dev/multi-chain/`
- `node_modules/` or `.venv/` → Use `dev/env/`
- `.pytest_cache/` or `.ruff_cache/` → Use `dev/cache/`

### ✅ Do this instead:
```bash
# Right way to create test files
touch dev/tests/test_new_feature.py

# Right way to create patch files
touch dev/scripts/fix_bug.py

# Right way to handle dependencies
npm install  # Will go to dev/env/node_modules/
python -m venv dev/env/.venv
```

## 🔧 IDE Configuration

### VS Code
The project includes `.vscode/settings.json` with:
- Excluded patterns for cache directories
- File watcher exclusions
- Auto-format on save
- Organize imports on save

### Git Hooks
Pre-commit hooks automatically:
- Check file locations
- Suggest correct locations
- Prevent commits with misplaced files

## 📞 Getting Help

If you're unsure where to put a file:
1. Run `./scripts/check-file-organization.sh`
2. Check this guide
3. Ask in team chat
4. When in doubt, use `dev/` subdirectories

## 🔄 Maintenance

- Weekly: Run organization check
- Monthly: Review new file patterns
- As needed: Update guidelines for new file types

## 🛡️ Prevention System

The project includes a comprehensive prevention system:

### 1. Git Pre-commit Hooks
- Automatically check file locations before commits
- Block commits with misplaced files
- Provide helpful suggestions

### 2. Automated Scripts
- `check-file-organization.sh` - Scan for issues
- `move-to-right-folder.sh` - Auto-fix organization

### 3. IDE Configuration
- VS Code settings hide clutter
- File nesting for better organization
- Tasks for easy access to tools

### 4. CI/CD Validation
- Pull request checks for file organization
- Automated comments with suggestions
- Block merges with organization issues

## 🎯 Best Practices

### File Naming
- Use descriptive names
- Follow existing patterns
- Include file type in name (test_, patch_, fix_)

### Directory Structure
- Keep related files together
- Use logical groupings
- Maintain consistency

### Development Workflow
1. Create files in correct location initially
2. Use IDE tasks to check organization
3. Run scripts before commits
4. Fix issues automatically when prompted

## 🔍 Troubleshooting

### Common Issues

#### "Git commit blocked due to file organization"
```bash
# Run the auto-fix script
./scripts/move-to-right-folder.sh --auto

# Then try commit again
git add .
git commit -m "My changes"
```

#### "Can't find my file"
```bash
# Check if it was moved automatically
find . -name "your-file-name"

# Or check organization status
./scripts/check-file-organization.sh
```

#### "VS Code shows too many files"
- The `.vscode/settings.json` excludes cache directories
- Reload VS Code to apply settings
- Check file explorer settings

## 📚 Additional Resources

- [Project Organization Workflow](../.windsurf/workflows/project-organization.md)
- [File Organization Prevention System](../.windsurf/workflows/file-organization-prevention.md)
- [Git Hooks Documentation](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)
- [VS Code Settings](https://code.visualstudio.com/docs/getstarted/settings)

---

*Last updated: March 2, 2026*  
*For questions or suggestions, please open an issue or contact the development team.*
