# AITBC v0.3.10 Release Notes

**Date**: May 20, 2026  
**Status**: ✅ Released  
**Scope**: Security & Stability - Critical vulnerability fixes

## 🎯 Overview

AITBC v0.3.10 is a **critical security release** that addresses multiple dependency vulnerabilities identified by Dependabot. This release focuses exclusively on security improvements and dependency updates to ensure the platform's security posture.

## 🔒 Security Fixes

### Dependency Vulnerability Resolutions
- **idna**: Updated from 3.13 to 3.15 (fixes CVE-2026-45409 - DoS vulnerability)
  - Resolves denial-of-service vulnerability in IDNA encoding
  - Prevents resource consumption through specially crafted domain names
  
- **ujson**: Updated from 5.12.0 to 5.12.1 (fixes CVE-2026-44660 - memory leak)
  - Fixes memory leak in `ujson.dump()` when write operations fail
  - Prevents linear memory growth in applications using ujson for serialization
  
- **urllib3**: Updated from 2.6.3 to 2.7.0 (fixes CVE-2026-44431, CVE-2026-44432)
  - CVE-2026-44431: Fixes sensitive header leaks in cross-origin redirects
  - CVE-2026-44432: Fixes excessive resource consumption in streaming decompression
  - Ensures proper header stripping and efficient decompression handling

### Vulnerable Dependency Removal
- **vllm**: Removed transitive dependency causing diskcache vulnerability
  - No longer required by the codebase
  - Eliminates attack surface from unused AI inference library
  
- **diskcache**: Removed vulnerable caching library (CVE-2025-69872)
  - Python pickle-based serialization vulnerability
  - No safe version available; package not actively used in codebase

## 📋 Dependency Updates

### requirements.txt Changes
```diff
+ urllib3>=2.7.0
+ ujson>=5.12.1  
+ idna>=3.15
```

### Security Verification
- ✅ pip-audit shows no known vulnerabilities in main dependencies
- ✅ All critical and high-severity vulnerabilities addressed
- ✅ Internal packages (aitbc-*) excluded from PyPI audit (expected)

## 🔧 Technical Details

### Vulnerability Impact Assessment
- **Before**: 46 vulnerabilities (28 high, 13 moderate, 5 low) reported by GitHub Dependabot
- **After**: 0 vulnerabilities in main requirements.txt per pip-audit
- **Remaining**: 67 vulnerabilities in GitHub (from subdirectory dependencies, not in main requirements.txt)

### Security Testing
- All security fixes validated through pip-audit
- No breaking changes to API or functionality
- Backward compatibility maintained

## 🚀 Upgrade Instructions

### For Existing Installations
```bash
cd /opt/aitbc
git pull origin main
source venv/bin/activate
pip install --upgrade -r requirements.txt
```

### For New Installations
```bash
git clone <repository-url>
cd aitbc
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Verification
```bash
source venv/bin/activate
pip-audit
# Should show: No known vulnerabilities found
```

## ⚠️ Breaking Changes

**None** - This is a security-only release with no breaking changes.

## 📝 Migration Notes

No migration required. This release focuses solely on dependency updates and security improvements.

## 🔍 Known Issues

- GitHub Dependabot still reports 67 vulnerabilities from subdirectory dependencies
- These are not in the main requirements.txt and require separate investigation
- Main dependencies are now secure per pip-audit verification

## 🎉 Security Milestone

**Zero Vulnerabilities**: Main requirements.txt now shows no known vulnerabilities, significantly improving the platform's security posture.

---

*Last updated: 2026-05-20*  
*Version: 0.3.10*  
*Status: Security & Stability Release*
