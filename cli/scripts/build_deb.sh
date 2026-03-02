#!/bin/bash

# AITBC CLI Debian Package Build Script

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Building AITBC CLI Debian packages...${NC}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEBIAN_DIR="$SCRIPT_DIR/debian"
DIST_DIR="$SCRIPT_DIR/dist"
DEB_OUTPUT_DIR="$SCRIPT_DIR/../packages/deb"

# Create output directory
mkdir -p "$DEB_OUTPUT_DIR"

# Create directories
mkdir -p "$DEBIAN_DIR/usr/share/aitbc/dist"
mkdir -p "$DEBIAN_DIR/usr/share/aitbc/man"
mkdir -p "$DEBIAN_DIR/usr/share/aitbc/completion"
mkdir -p "$DEBIAN_DIR/usr/share/man/man1"
mkdir -p "$DEBIAN_DIR/etc/bash_completion.d"
mkdir -p "$DEBIAN_DIR/etc/aitbc"

# Copy files to package structure
echo -e "${BLUE}Copying files to package structure...${NC}"

# Copy wheel file
if [ -f "$DIST_DIR/aitbc_cli-0.1.0-py3-none-any.whl" ]; then
    cp "$DIST_DIR/aitbc_cli-0.1.0-py3-none-any.whl" "$DEBIAN_DIR/usr/share/aitbc/dist/"
    echo -e "${GREEN}✓ Copied wheel file${NC}"
else
    echo -e "${RED}❌ Wheel file not found! Please build it first.${NC}"
    exit 1
fi

# Copy man page
if [ -f "$SCRIPT_DIR/man/aitbc.1" ]; then
    cp "$SCRIPT_DIR/man/aitbc.1" "$DEBIAN_DIR/usr/share/aitbc/man/"
    cp "$SCRIPT_DIR/man/aitbc.1" "$DEBIAN_DIR/usr/share/man/man1/"
    echo -e "${GREEN}✓ Copied man page${NC}"
else
    echo -e "${RED}❌ Man page not found!${NC}"
    exit 1
fi

# Copy completion script
if [ -f "$SCRIPT_DIR/aitbc_completion.sh" ]; then
    cp "$SCRIPT_DIR/aitbc_completion.sh" "$DEBIAN_DIR/usr/share/aitbc/completion/"
    chmod +x "$DEBIAN_DIR/usr/share/aitbc/completion/aitbc_completion.sh"
    echo -e "${GREEN}✓ Copied completion script${NC}"
else
    echo -e "${RED}❌ Completion script not found!${NC}"
    exit 1
fi

# Calculate package size
echo -e "${BLUE}Calculating package size...${NC}"
PACKAGE_SIZE=$(du -sm "$DEBIAN_DIR" | cut -f1)

# Update control file with size
sed -i "s/Installed-Size:.*/Installed-Size: $PACKAGE_SIZE/" "$DEBIAN_DIR/DEBIAN/control" 2>/dev/null || echo "Installed-Size: $PACKAGE_SIZE" >> "$DEBIAN_DIR/DEBIAN/control"

# Generate md5sums
echo -e "${BLUE}Generating md5sums...${NC}"
cd "$DEBIAN_DIR"
find . -type f ! -path './DEBIAN/*' -exec md5sum {} + | sed 's/\.\///' > DEBIAN/md5sums
cd - > /dev/null

# Build the packages
echo -e "${BLUE}Building Debian packages...${NC}"

# Build aitbc-cli package
echo -e "${BLUE}Building aitbc-cli package...${NC}"
dpkg-deb --build "$DEBIAN_DIR" "$DEB_OUTPUT_DIR/aitbc-cli_0.1.0_all.deb"

# Create dev package (just control file differences)
echo -e "${BLUE}Building aitbc-cli-dev package...${NC}"
cp -r "$DEBIAN_DIR" "${DEBIAN_DIR}_dev"

# Update dev package control
cp "$DEBIAN_DIR/DEBIAN/control_dev" "${DEBIAN_DIR}_dev/DEBIAN/control"

# Build dev package
dpkg-deb --build "${DEBIAN_DIR}_dev" "$DEB_OUTPUT_DIR/aitbc-cli-dev_0.1.0_all.deb"

# Clean up temporary directories
rm -rf "${DEBIAN_DIR}_dev"

# Verify packages
echo -e "${BLUE}Verifying packages...${NC}"
if [ -f "$DEB_OUTPUT_DIR/aitbc-cli_0.1.0_all.deb" ]; then
    echo -e "${GREEN}✓ aitbc-cli package created: $DEB_OUTPUT_DIR/aitbc-cli_0.1.0_all.deb"
    dpkg-deb --info "$DEB_OUTPUT_DIR/aitbc-cli_0.1.0_all.deb" | head -10
else
    echo -e "${RED}❌ aitbc-cli package creation failed${NC}"
    exit 1
fi

if [ -f "$DEB_OUTPUT_DIR/aitbc-cli-dev_0.1.0_all.deb" ]; then
    echo -e "${GREEN}✓ aitbc-cli-dev package created: $DEB_OUTPUT_DIR/aitbc-cli-dev_0.1.0_all.deb"
    dpkg-deb --info "$DEB_OUTPUT_DIR/aitbc-cli-dev_0.1.0_all.deb" | head -10
else
    echo -e "${RED}❌ aitbc-cli-dev package creation failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 Debian packages built successfully!${NC}"
echo ""
echo "Packages created:"
echo "  - $DEB_OUTPUT_DIR/aitbc-cli_0.1.0_all.deb"
echo "  - $DEB_OUTPUT_DIR/aitbc-cli-dev_0.1.0_all.deb"
echo ""
echo "To install on Debian 13 Trixie:"
echo "  sudo dpkg -i $DEB_OUTPUT_DIR/aitbc-cli_0.1.0_all.deb"
echo "  sudo apt-get install -f  # Fix dependencies if needed"
echo ""
echo "Package contents:"
echo "  - CLI installed in /opt/aitbc/venv/bin/aitbc"
echo "  - Symlink at /usr/local/bin/aitbc"
echo "  - Man page: man aitbc"
echo "  - Bash completion: /etc/bash_completion.d/aitbc"
echo "  - Config file: /etc/aitbc/config.yaml"
