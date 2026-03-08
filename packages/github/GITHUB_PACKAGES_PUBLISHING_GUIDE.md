# GitHub Packages Publishing Guide for Native Packages

## 🚀 Getting Your Native Packages Published

Your AITBC native packages (.deb and .pkg) are built and ready to be published. Since these are native binary packages, they'll be published as **GitHub Releases** (not GitHub Packages registry, which is for Docker/npm/Python packages).

## 📋 What's Been Set Up

I've created a workflow to publish your native packages:

### `publish-native-packages-simple.yml`
- Publishes Debian (.deb) and macOS (.pkg) packages as GitHub Release assets
- Creates comprehensive release notes with installation instructions
- Generates package status documentation
- Includes checksums and verification information

## 🔧 How to Publish Your Packages

### Option 1: Tag-Based Publishing (Recommended)
```bash
# Create and push a version tag
git tag v0.1.0
git push origin v0.1.0
```
This will automatically trigger the workflow and publish all packages as a GitHub Release.

### Option 2: Manual Publishing
1. Go to: https://github.com/oib/AITBC/actions
2. Select "Publish Native Packages" workflow
3. Click "Run workflow"
4. Enter version (e.g., "0.1.0")
5. Click "Run workflow"

## 📦 What Will Be Published

### GitHub Release Assets
When published, your packages will appear as release assets at:
https://github.com/oib/AITBC/releases

#### Linux Packages (.deb)
- `aitbc-cli_0.1.0_all.deb` - Main CLI package (132KB)
- `aitbc-node-service_0.1.0_all.deb` - Blockchain node (8KB)
- `aitbc-coordinator-service_0.1.0_all.deb` - Coordinator API (8KB)
- `aitbc-miner-service_0.1.0_all.deb` - GPU miner (8KB)
- `aitbc-marketplace-service_0.1.0_all.deb` - Marketplace (8KB)
- `aitbc-explorer-service_0.1.0_all.deb` - Explorer (8KB)
- `aitbc-wallet-service_0.1.0_all.deb` - Wallet (8KB)
- `aitbc-multimodal-service_0.1.0_all.deb` - Multimodal AI (8KB)
- `aitbc-all-services_0.1.0_all.deb` - Complete stack (8KB)

#### macOS Packages (.pkg)
- `aitbc-cli-0.1.0-apple-silicon.pkg` - CLI for Apple Silicon (4.6KB)
- `aitbc-node-service-0.1.0-apple-silicon.pkg` - Node service (2.5KB)
- `aitbc-coordinator-service-0.1.0-apple-silicon.pkg` - Coordinator (2.5KB)
- `aitbc-miner-service-0.1.0-apple-silicon.pkg` - Miner (2.4KB)
- `aitbc-marketplace-service-0.1.0-apple-silicon.pkg` - Marketplace (2.4KB)
- `aitbc-explorer-service-0.1.0-apple-silicon.pkg` - Explorer (2.4KB)
- `aitbc-wallet-service-0.1.0-apple-silicon.pkg` - Wallet (2.4KB)
- `aitbc-multimodal-service-0.1.0-apple-silicon.pkg` - Multimodal (2.4KB)
- `aitbc-all-services-0.1.0-apple-silicon.pkg` - Complete stack (2.4KB)

#### Supporting Files
- `checksums.txt` - SHA256 checksums for verification
- `install-macos-complete.sh` - macOS installer script
- `install-macos-services.sh` - macOS services installer

## 🔍 After Publishing

Once published, your packages will appear at:
https://github.com/oib/AITBC/releases

You'll see:
- **Release page** with all package assets
- **Installation instructions** in release notes
- **Download links** for each package
- **Checksum verification** information

## 🚦 Prerequisites

### Required Permissions
The workflow needs:
- `contents: write` - to create releases and upload assets

### Required Secrets
- `GITHUB_TOKEN` - automatically provided by GitHub Actions

## 🛠️ Installation After Publishing

### Linux (Debian/Ubuntu)
```bash
# Method 1: Universal installer
curl -fsSL https://raw.githubusercontent.com/oib/AITBC/main/packages/github/install.sh | bash

# Method 2: Direct download
wget https://github.com/oib/AITBC/releases/download/v0.1.0/aitbc-cli_0.1.0_all.deb
sudo dpkg -i aitbc-cli_0.1.0_all.deb

# Method 3: Complete stack
wget https://github.com/oib/AITBC/releases/download/v0.1.0/aitbc-all-services_0.1.0_all.deb
sudo dpkg -i aitbc-all-services_0.1.0_all.deb
```

### macOS (Apple Silicon)
```bash
# Method 1: Universal installer
curl -fsSL https://raw.githubusercontent.com/oib/AITBC/main/packages/github/install-macos.sh | bash

# Method 2: Direct download
curl -L https://github.com/oib/AITBC/releases/download/v0.1.0/aitbc-cli-0.1.0-apple-silicon.pkg -o aitbc-cli.pkg
sudo installer -pkg aitbc-cli.pkg -target /

# Method 3: Complete stack
curl -L https://github.com/oib/AITBC/releases/download/v0.1.0/install-macos-complete.sh | bash
```

## 🔍 Troubleshooting

### Packages Don't Show Up
1. Check the Actions tab for workflow status
2. Ensure you have the right permissions
3. Verify the tag format (should be `v*` like `v0.1.0`)
4. Check the Releases tab for the new release

### Permission Errors
1. Go to repository Settings > Actions > General
2. Ensure "Read and write permissions" are enabled for Actions
3. Check workflow permissions in the YAML file

### Download Issues
```bash
# Verify checksums
sha256sum -c checksums.txt

# Check file integrity
ls -la *.deb *.pkg
```

## 📊 Package Status

### Current Status: Ready to Publish ✅
- ✅ All packages built and verified
- ✅ Checksums validated
- ✅ Workflow configured and ready
- ✅ Installation scripts tested
- ✅ Documentation prepared

### Next Steps
1. Create version tag: `git tag v0.1.0 && git push origin v0.1.0`
2. Monitor workflow execution
3. Verify release appears in GitHub Releases
4. Test installation from published packages

## 📚 Additional Resources

- [GitHub Releases Documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Release Assets Best Practices](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

---

**Important Note**: Native packages (.deb/.pkg) are published as **GitHub Releases**, not GitHub Packages registry. GitHub Packages is for container images, npm packages, and other package manager formats.

**Ready to publish your native packages! 🚀**
