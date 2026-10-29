#!/bin/bash
set -euo pipefail
# scripts/git-pre-commit-hook.sh

echo "🔍 Checking file locations before commit..."

# Change to project root
cd "$(dirname "$0")/../.."

# Files that should not be at root
ROOT_FORBIDDEN_PATTERNS=(
    "test_*.py"
    "test_*.sh"
    "patch_*.py"
    "fix_*.py"
    "simple_test.py"
    "run_mc_test.sh"
    "MULTI_*.md"
)

# Directories that should not be at root
ROOT_FORBIDDEN_DIRS=(
    "node_modules"
    ".pytest_cache"
    ".ruff_cache"
    ".venv"
    "cli_env"
    ".vscode"
)

# Check for forbidden files at root
for pattern in "${ROOT_FORBIDDEN_PATTERNS[@]}"; do
    if ls $pattern 1> /dev/null 2>&1; then
        echo "❌ ERROR: Found files matching '$pattern' at root level"
        echo "💡 Move it under a proper directory before committing."
        exit 1
    fi
done

# Check for forbidden directories at root
for dir in "${ROOT_FORBIDDEN_DIRS[@]}"; do
    if [[ -d "$dir" && "$dir" != "." && "$dir" != ".." && ! "$dir" =~ ^\.git ]]; then
        echo "❌ ERROR: Found directory '$dir' at root level"
        echo "💡 Remove or ignore it before committing."
        exit 1
    fi
done

# Check new files being committed
NEW_FILES=$(git diff --cached --name-only --diff-filter=A)

for file in $NEW_FILES; do
    dirname=$(dirname "$file")

    # Check if file is at root and shouldn't be
    if [[ "$dirname" == "." ]]; then
        filename=$(basename "$file")

        case "$filename" in
            test_*.py|test_*.sh)
                echo "⚠️  WARNING: Test file '$filename' should live under tests/ or the app's tests/ dir"
                echo "💡 Consider: git reset HEAD $filename && mv $filename tests/ && git add tests/$filename"
                ;;
            patch_*.py|fix_*.py)
                echo "⚠️  WARNING: Patch file '$filename' should be in scripts/dev/"
                echo "💡 Consider: git reset HEAD $filename && mv $filename scripts/dev/ && git add scripts/dev/$filename"
                ;;
            MULTI_*.md)
                echo "⚠️  WARNING: Multi-chain file '$filename' should be in docs/"
                echo "💡 Consider: git reset HEAD $filename && mv $filename docs/ && git add docs/$filename"
                ;;
            .aitbc.yaml|.aitbc.yaml.example|.env.production|.nvmrc|.lycheeignore)
                echo "⚠️  WARNING: Configuration file '$filename' at root"
                echo "💡 Consider: keep it only if the toolchain expects it at root"
                ;;
        esac
    fi
done

echo "✅ File location check passed"
exit 0
