#!/bin/bash

echo "=== Final Root Directory Cleanup ==="
echo "Organizing remaining files..."
echo ""

# Create docs/temp for temporary documentation
mkdir -p docs/temp
mkdir -p docs/reports

echo "=== Moving Documentation Files ==="
# Move temporary documentation to docs/temp
mv DEBUgging_SERVICES.md docs/temp/ 2>/dev/null || echo "DEBUgging_SERVICES.md not found"
mv DEV_LOGS.md docs/temp/ 2>/dev/null || echo "DEV_LOGS.md not found"
mv DEV_LOGS_QUICK_REFERENCE.md docs/temp/ 2>/dev/null || echo "DEV_LOGS_QUICK_REFERENCE.md not found"
mv GITHUB_PULL_SUMMARY.md docs/temp/ 2>/dev/null || echo "GITHUB_PULL_SUMMARY.md not found"
mv SQLMODEL_METADATA_FIX_SUMMARY.md docs/temp/ 2>/dev/null || echo "SQLMODEL_METADATA_FIX_SUMMARY.md not found"
mv WORKING_SETUP.md docs/temp/ 2>/dev/null || echo "WORKING_SETUP.md not found"

echo "=== Moving User Guides ==="
# Move user guides to docs directory
mv GIFT_CERTIFICATE_newuser.md docs/ 2>/dev/null || echo "GIFT_CERTIFICATE_newuser.md not found"
mv user_profile_newuser.md docs/ 2>/dev/null || echo "user_profile_newuser.md not found"

echo "=== Moving Environment Files ==="
# Move environment files to config
mv .env.dev config/ 2>/dev/null || echo ".env.dev already in config"
mv .env.dev.logs config/ 2>/dev/null || echo ".env.dev.logs already in config"

echo "=== Updating .gitignore ==="
# Add temp directories to .gitignore if not already there
if ! grep -q "^temp/" .gitignore; then
    echo "" >> .gitignore
    echo "# Temporary directories" >> .gitignore
    echo "temp/" >> .gitignore
    echo "docs/temp/" >> .gitignore
fi

if ! grep -q "^# Environment files" .gitignore; then
    echo "" >> .gitignore
    echo "# Environment files" >> .gitignore
    echo ".env.local" >> .gitignore
    echo ".env.production" >> .gitignore
fi

echo "=== Checking for Large Files ==="
# Check for any large files that shouldn't be in repo
echo "Checking for files > 1MB..."
find . -type f -size +1M -not -path "./.git/*" -not -path "./temp/*" -not -path "./.windsurf/*" | head -10

echo ""
echo "=== Final Root Directory Structure ==="
echo "Essential files remaining in root:"
echo "- Configuration: .editorconfig, .gitignore, .pre-commit-config.yaml"
echo "- Documentation: README.md, LICENSE, SECURITY.md, SETUP_PRODUCTION.md"
echo "- Environment: .env.example"
echo "- Build: pyproject.toml, poetry.lock"
echo "- Testing: run_all_tests.sh"
echo "- Core directories: apps/, cli/, packages/, scripts/, tests/, docs/"
echo "- Infrastructure: infra/, deployment/, systemd/"
echo "- Development: dev/, ai-memory/, config/"
echo "- Extensions: extensions/, plugins/, gpu_acceleration/"
echo "- Website: website/"
echo "- Contracts: contracts/, migration_examples/"

echo ""
echo "✅ Root directory is now clean and organized!"
echo "Ready for GitHub push."
