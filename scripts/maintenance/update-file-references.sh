#!/bin/bash

# Update file references after project reorganization
# This script updates all references to moved files

set -e

echo "=== Updating File References ==="

# Update requirements.txt references
echo "Updating requirements.txt references..."
find /opt/aitbc/scripts -name "*.sh" -type f -exec sed -i 's|/opt/aitbc/requirements\.txt|/opt/aitbc/requirements.txt|g' {} \;
find /opt/aitbc/scripts -name "*.py" -type f -exec sed -i 's|/opt/aitbc/requirements\.txt|/opt/aitbc/requirements.txt|g' {} \;

# Update pyproject.toml references (excluding project-config directory)
echo "Updating pyproject.toml references..."
find /opt/aitbc/scripts -name "*.sh" -type f -exec sed -i 's|/opt/aitbc/pyproject\.toml|/opt/aitbc/pyproject.toml|g' {} \;
find /opt/aitbc/scripts -name "*.py" -type f -exec sed -i 's|/opt/aitbc/pyproject\.toml|/opt/aitbc/pyproject.toml|g' {} \;

# Update README.md references
echo "Updating README.md references..."
find /opt/aitbc/scripts -name "*.sh" -type f -exec sed -i 's|/opt/aitbc/README\.md|/opt/aitbc/docs/README.md|g' {} \;
find /opt/aitbc/scripts -name "*.py" -type f -exec sed -i 's|/opt/aitbc/README\.md|/opt/aitbc/docs/README.md|g' {} \;

# Update .gitignore references
echo "Updating .gitignore references..."
find /opt/aitbc/scripts -name "*.sh" -type f -exec sed -i 's|/opt/aitbc/\.gitignore|/opt/aitbc/project-config/.gitignore|g' {} \;
find /opt/aitbc/scripts -name "*.py" -type f -exec sed -i 's|/opt/aitbc/\.gitignore|/opt/aitbc/project-config/.gitignore|g' {} \;

echo "=== File Reference Updates Complete ==="
