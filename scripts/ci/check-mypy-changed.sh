#!/bin/bash
# Check mypy type annotations on changed/new files only
# This implements the gradual type checking approach for the codebase
# NEW files must pass type checking, EXISTING files generate warnings only

set -e

echo "🔍 Checking type annotations on changed Python files..."

# Get list of changed Python files (staged or modified)
CHANGED_FILES=$(git diff --name-only --diff-filter=ACMRT HEAD 2>/dev/null | grep '\.py$' || true)
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMRT 2>/dev/null | grep '\.py$' || true)

# Combine and deduplicate
ALL_FILES=$(echo -e "$CHANGED_FILES\n$STAGED_FILES" | sort -u | grep -v '^$' || true)

if [ -z "$ALL_FILES" ]; then
    echo "✅ No Python files changed - skipping type check"
    exit 0
fi

echo "📁 Files to check:"
echo "$ALL_FILES"
echo ""

# Track failures and warnings
FAILED=0
WARNINGS=0

# Check each file
for file in $ALL_FILES; do
    if [ -f "$file" ]; then
        echo "🔎 Checking: $file"
        
        # Check if this is a new file (not in git history)
        if ! git rev-parse HEAD:"$file" >/dev/null 2>&1; then
            echo "🆕 NEW FILE - strict type checking required"
            # Use --follow-imports=skip to avoid checking dependencies (which have errors)
            if ! venv/bin/python -m mypy "$file" --follow-imports=skip --ignore-missing-imports 2>&1; then
                echo "❌ Type errors in NEW file: $file"
                echo "   New files must have proper type annotations"
                FAILED=1
            else
                echo "✅ $file passed"
            fi
        else
            echo "📝 EXISTING FILE - warning mode (gradual typing)"
            # For existing files, just warn about type errors
            if ! venv/bin/python -m mypy "$file" --follow-imports=skip --ignore-missing-imports 2>&1; then
                echo "⚠️  Type errors in existing file: $file"
                echo "   Consider adding type annotations when you modify this file"
                WARNINGS=1
            else
                echo "✅ $file passed"
            fi
        fi
    fi
done

if [ $FAILED -eq 1 ]; then
    echo ""
    echo "❌ Mypy found type errors in NEW files."
    echo "New files must have proper type annotations. Please add type annotations or fix the errors."
    echo "To bypass (not recommended): git commit --no-verify"
    exit 1
elif [ $WARNINGS -eq 1 ]; then
    echo ""
    echo "⚠️  Mypy found type errors in existing files."
    echo "This is expected during gradual type migration. Consider adding type annotations when you modify these files."
    echo "✅ Commit allowed (new files are properly typed)"
    exit 0
else
    echo ""
    echo "✅ All changed files passed type checking!"
    exit 0
fi
