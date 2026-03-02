#!/bin/bash
# scripts/git-pre-commit-hook.sh

echo "🔍 Checking file locations before commit..."

# Change to project root
cd "$(dirname "$0")/.."

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
    "logs"
    ".vscode"
)

# Check for forbidden files at root
for pattern in "${ROOT_FORBIDDEN_PATTERNS[@]}"; do
    if ls $pattern 1> /dev/null 2>&1; then
        echo "❌ ERROR: Found files matching '$pattern' at root level"
        echo "📁 Suggested location:"
        
        case $pattern in
            "test_*.py"|"test_*.sh"|"run_mc_test.sh")
                echo "   → dev/tests/"
                ;;
            "patch_*.py"|"fix_*.py"|"simple_test.py")
                echo "   → dev/scripts/"
                ;;
            "MULTI_*.md")
                echo "   → dev/multi-chain/"
                ;;
        esac
        
        echo "💡 Run: ./scripts/move-to-right-folder.sh --auto"
        echo "💡 Or manually: mv $pattern <suggested-directory>/"
        exit 1
    fi
done

# Check for forbidden directories at root
for dir in "${ROOT_FORBIDDEN_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        echo "❌ ERROR: Found directory '$dir' at root level"
        echo "📁 Suggested location:"
        
        case $dir in
            "node_modules"|".venv"|"cli_env")
                echo "   → dev/env/"
                ;;
            ".pytest_cache"|".ruff_cache"|"logs"|".vscode")
                echo "   → dev/cache/"
                ;;
        esac
        
        echo "💡 Run: ./scripts/move-to-right-folder.sh --auto"
        echo "💡 Or manually: mv $dir <suggested-directory>/"
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
                echo "⚠️  WARNING: Test file '$filename' should be in dev/tests/"
                echo "💡 Consider: git reset HEAD $filename && mv $filename dev/tests/ && git add dev/tests/$filename"
                ;;
            patch_*.py|fix_*.py)
                echo "⚠️  WARNING: Patch file '$filename' should be in dev/scripts/"
                echo "💡 Consider: git reset HEAD $filename && mv $filename dev/scripts/ && git add dev/scripts/$filename"
                ;;
            MULTI_*.md)
                echo "⚠️  WARNING: Multi-chain file '$filename' should be in dev/multi-chain/"
                echo "💡 Consider: git reset HEAD $filename && mv $filename dev/multi-chain/ && git add dev/multi-chain/$filename"
                ;;
            .aitbc.yaml|.aitbc.yaml.example|.env.production|.nvmrc|.lycheeignore)
                echo "⚠️  WARNING: Configuration file '$filename' should be in config/"
                echo "💡 Consider: git reset HEAD $filename && mv $filename config/ && git add config/$filename"
                ;;
        esac
    fi
done

echo "✅ File location check passed"
exit 0
