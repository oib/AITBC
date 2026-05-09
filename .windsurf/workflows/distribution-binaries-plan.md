---
description: Distribution & Binaries Workflow for Cross-Platform Miner
---

# Distribution & Binaries Workflow

This workflow covers the creation and distribution of cross-platform miner binaries.

## Prerequisites

- Build machines for each target platform (Linux, Windows, macOS)
- PyInstaller or similar packaging tool
- GitHub Releases configured
- Code signing certificates (for production)
- vLLM integration requirements

## Steps

### 1. Cross-Platform Miner Binaries (Linux, Windows, macOS)

1. **Set up build environment for each platform**

   **Linux:**
   - Ubuntu 20.04+ build machine
   - Python 3.13+ with PyInstaller
   - CUDA Toolkit (for GPU support)
   - System dependencies: build-essential, python3-dev

   **Windows:**
   - Windows 10/11 build machine
   - Python 3.13+ with PyInstaller
   - CUDA Toolkit (for GPU support)
   - Visual Studio Build Tools

   **macOS:**
   - macOS 11+ build machine
   - Python 3.13+ with PyInstaller
   - Xcode Command Line Tools
   - Metal support (for Apple Silicon GPU)

2. **Create PyInstaller spec files**
   - File: `scripts/gpu/miner.spec`
   - Define entry point: `scripts/gpu/gpu_miner_host.py`
   - Include all dependencies
   - Configure hidden imports
   - Set icon and metadata

3. **Build binaries for each platform**
   ```bash
   # Linux
   pyinstaller --onefile --name aitbc-miner-linux scripts/gpu/miner.spec

   # Windows
   pyinstaller --onefile --name aitbc-miner-windows.exe scripts/gpu/miner.spec

   # macOS
   pyinstaller --onefile --name aitbc-miner-macos scripts/gpu/miner.spec
   ```

4. **Test binaries**
   - Run each binary on respective platform
   - Verify GPU detection works
   - Test job submission and processing
   - Verify logging and error handling

5. **Package binaries with dependencies**
   - Create installation scripts for each platform
   - Include README with platform-specific instructions
   - Bundle configuration templates
   - Add verification checksums

### 2. vLLM Integration for Optimized LLM Inference

1. **Research vLLM integration**
   - Review vLLM documentation
   - Analyze compatibility with existing Ollama integration
   - Evaluate performance benefits
   - Check hardware requirements

2. **Implement vLLM integration**
   - Add vLLM dependency to requirements
   - Create vLLM service wrapper
   - Implement model loading with vLLM
   - Add vLLM-specific configuration options

3. **Test vLLM integration**
   - Benchmark performance vs Ollama
   - Test with various LLM models
   - Verify GPU utilization
   - Check memory usage

4. **Create fallback mechanism**
   - Implement Ollama as fallback
   - Add automatic model selection
   - Configure graceful degradation
   - Document vLLM vs Ollama trade-offs

### 3. Binary Distribution via GitHub Releases

1. **Create GitHub Actions workflow**
   - File: `.github/workflows/build-binaries.yml`
   - Trigger on version tags (e.g., `v*.*.*`)
   - Build for all platforms in parallel
   - Upload artifacts to workflow

2. **Configure automatic release creation**
   - Use GitHub Actions to create release on tag
   - Attach binaries as release assets
   - Generate release notes from CHANGELOG
   - Sign binaries (if code signing available)

3. **Create release process**
   ```bash
   # Tag release
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin v0.1.0

   # GitHub Actions will:
   # 1. Build binaries for all platforms
   # 2. Create GitHub Release
   # 3. Attach binaries as assets
   ```

4. **Test release process**
   - Create test release tag
   - Verify automatic build works
   - Check release creation
   - Verify asset attachments
   - Test download and installation

### 4. Automatic Binary Building in CI/CD

1. **Enhance existing CI/CD pipeline**
   - Add binary build step to existing workflows
   - Configure matrix builds for platforms
   - Cache build dependencies
   - Optimize build times

2. **Set up build agents**
   - Configure GitHub Actions runners
   - Use self-hosted runners for specific platforms
   - Set up macOS runner for Apple Silicon builds
   - Configure Windows runner for Windows builds

3. **Add build notifications**
   - Notify on build failures
   - Send build status to Slack/Email
   - Track build metrics
   - Monitor build queue times

4. **Implement build artifacts**
   - Store build artifacts for debugging
   - Keep last N builds
   - Configure artifact retention policy
   - Enable artifact download for testing

### 5. Installation Guides and Verification Instructions

1. **Create platform-specific installation guides**
   - Linux: `docs/installation/linux-miner.md`
   - Windows: `docs/installation/windows-miner.md`
   - macOS: `docs/installation/macos-miner.md`

2. **Installation guide sections**
   - System requirements
   - Prerequisites (GPU drivers, CUDA)
   - Download instructions
   - Installation steps
   - Configuration
   - Verification
   - Troubleshooting

3. **Create verification script**
   - Script: `scripts/installation/verify-install.sh`
   - Check binary integrity with checksums
   - Verify GPU detection
   - Test basic functionality
   - Output verification report

4. **Add checksums to releases**
   - Generate SHA256 checksums for each binary
   - Include checksums in release notes
   - Provide verification instructions
   - Automate checksum generation

### 6. Binary Signature Verification

1. **Set up code signing**
   - Obtain code signing certificates
   - Configure signing tools
   - Set up certificate storage (GitHub Secrets)
   - Test signing process

2. **Sign binaries**
   - Sign Linux binaries with GPG
   - Sign Windows binaries with Authenticode
   - Sign macOS binaries with Apple Developer ID
   - Add signatures to release assets

3. **Create verification instructions**
   - Document signature verification process
   - Provide GPG public key
   - Include verification commands
   - Add to installation guides

4. **Automate signing in CI/CD**
   - Add signing step to build workflow
   - Configure certificate access
   - Test signed binary distribution
   - Verify signature verification works

## Verification

- [ ] Binaries build successfully for all platforms
- [ ] Binaries run correctly on respective platforms
- [ ] vLLM integration tested and documented
- [ ] GitHub Actions workflow builds binaries automatically
- [ ] Releases created automatically on tags
- [ ] Installation guides complete for all platforms
- [ ] Verification scripts work correctly
- [ ] Code signing configured and tested
- [ ] Signature verification documented

## Troubleshooting

- **Build fails on specific platform**: Check platform-specific dependencies, verify Python version, test build locally
- **Binary doesn't run**: Check PyInstaller spec file, verify dependencies, test on clean system
- **vLLM integration fails**: Check vLLM version compatibility, verify GPU drivers, test with simple model
- **Release creation fails**: Check GitHub token permissions, verify workflow configuration, test with manual release
- **Signature verification fails**: Check certificate validity, verify signing process, test verification commands

## Related Files

- `scripts/gpu/miner.spec`
- `scripts/gpu/gpu_miner_host.py`
- `.github/workflows/build-binaries.yml`
- `docs/installation/linux-miner.md`
- `docs/installation/windows-miner.md`
- `docs/installation/macos-miner.md`
- `scripts/installation/verify-install.sh`
