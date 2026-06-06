#!/bin/bash
# Check mypy type annotations on changed/new files only
# This implements the gradual type checking approach for the codebase

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

# Track failures
FAILED=0

# Check each file
for file in $ALL_FILES; do
    if [ -f "$file" ]; then
        echo "🔎 Checking: $file"
        # Use --follow-imports=skip to avoid checking dependencies (which have errors)
        if ! venv/bin/python -m mypy "$file" --follow-imports=skip --ignore-missing-imports 2>&1; then
            echo "❌ Type errors in: $file"
            FAILED=1
        else
            echo "✅ $file passed"
        fi
    fi
done

if [ $FAILED -eq 1 ]; then
    echo ""
    echo "❌ Mypy found type errors in changed files."
    echo "Please add type annotations or fix the errors."
    echo "To bypass (not recommended): git commit --no-verify"
    exit 1
else
    echo ""
    echo "✅ All changed files passed type checking!"
    exit 0
fi
