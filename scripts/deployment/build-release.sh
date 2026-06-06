#!/bin/bash
# AITBC v0.2 Release Build Script
# Builds CLI binaries for multiple platforms

set -e

VERSION="0.2.0"
PROJECT_NAME="aitbc-cli"
BUILD_DIR="dist/release"

echo "🚀 Building AITBC CLI v${VERSION} for release..."

# Clean previous builds
rm -rf ${BUILD_DIR}
mkdir -p ${BUILD_DIR}

# Build using PyInstaller for multiple platforms
echo "📦 Building binaries..."

# Install PyInstaller if not available
pip install pyinstaller

# Build for current platform
pyinstaller --onefile \
    --name aitbc \
    --add-data "cli/aitbc_cli:aitbc_cli" \
    --hidden-import aitbc_cli \
    --hidden-import aitbc_cli.commands \
    --hidden-import aitbc_cli.utils \
    --distpath ${BUILD_DIR}/$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m) \
    cli/aitbc_cli/main.py

# Create release package
echo "📋 Creating release package..."

# Create platform-specific packages
cd ${BUILD_DIR}

# Linux package
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    mkdir -p linux-x86_64
    cp ../linux-x86_64/aitbc linux-x86_64/
    tar -czf aitbc-v${VERSION}-linux-x86_64.tar.gz linux-x86_64/
fi

# macOS package  
if [[ "$OSTYPE" == "darwin"* ]]; then
    mkdir -p darwin-x86_64
    cp ../darwin-x86_64/aitbc darwin-x86_64/
    tar -czf aitbc-v${VERSION}-darwin-x86_64.tar.gz darwin-x86_64/
fi

# Windows package (if on Windows with WSL)
if command -v cmd.exe &> /dev/null; then
    mkdir -p windows-x86_64
    cp ../windows-x86_64/aitbc.exe windows-x86_64/
    zip -r aitbc-v${VERSION}-windows-x86_64.zip windows-x86_64/
fi

echo "✅ Build complete!"
echo "📁 Release files in: ${BUILD_DIR}"
ls -la ${BUILD_DIR}/*.tar.gz ${BUILD_DIR}/*.zip 2>/dev/null || true

# Generate checksums
echo "🔐 Generating checksums..."
cd ${BUILD_DIR}
sha256sum *.tar.gz *.zip 2>/dev/null > checksums.txt || true
cat checksums.txt

echo "🎉 AITBC CLI v${VERSION} release ready!"
