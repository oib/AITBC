#!/bin/bash
# AITBC Permission Fix — scoped to source files only.
#
# The old version chmod 664'd EVERY file under /opt/aitbc and added +x only to
# *.sh/*.py: venv/bin tools and .git/hooks lost their execute bit and every
# mode-600 secret (.env files, keystores, credentials) became world-readable.
# This version only touches tracked source files and explicitly prunes
# venv/, .git/, node_modules/, data/, credentials, .env* and key material.

set -euo pipefail

TARGET_DIR="${AITBC_PERM_TARGET:-/opt/aitbc}"

echo "Fixing AITBC source permissions under $TARGET_DIR ..."

# Prune everything that is not source: virtualenvs, VCS internals, vendored
# trees, runtime data, and anything that can hold secrets.
PRUNE=( '(' \
    -name venv -o -name .venv -o -name .git -o -name node_modules \
    -o -name data -o -name credentials -o -name keystore \
    -o -name '.env*' -o -name '*.key' -o -name '*.pem' -o -name '*.secret' \
    ')' -prune )

# Directories: group-writable + setgid so new files inherit the group.
sudo find "$TARGET_DIR" "${PRUNE[@]}" -o -type d -exec chmod 2775 {} +

# Source files only: regular permissions on known text types. Executable
# scripts keep/regain their exec bit; nothing else is touched.
sudo find "$TARGET_DIR" "${PRUNE[@]}" -o -type f \
    '(' -name '*.sh' -o -name '*.bash' ')' -exec chmod 775 {} +
sudo find "$TARGET_DIR" "${PRUNE[@]}" -o -type f \
    '(' -name '*.py' -o -name '*.pyi' -o -name '*.md' -o -name '*.txt' \
       -o -name '*.toml' -o -name '*.cfg' -o -name '*.ini' -o -name '*.yaml' \
       -o -name '*.yml' -o -name '*.json' -o -name '*.sol' -o -name '*.rs' \
       -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \
       -o -name '*.html' -o -name '*.css' ')' -exec chmod 664 {} +

echo "Permissions fixed (source files only)."
