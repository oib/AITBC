# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Python Version Baseline**: Updated minimum supported Python version from 3.8 to 3.11
  - Root CLI package now requires Python >=3.11
  - Added Python 3.12 support to CI and package classifiers
  - Updated documentation to reflect 3.11+ minimum requirement
  - Services and shared libraries already required Python 3.11+

### CI/CD
- Added Python 3.12 to CLI test matrix alongside 3.11
- Updated CI workflows to test on newer Python versions

### Documentation
- Updated infrastructure documentation to consistently state Python 3.11+ minimum
- Aligned all Python version references across docs

## [0.1.0] - 2024-XX-XX

Initial release with core AITBC functionality including:
- CLI tools for blockchain operations
- Coordinator API for job submission and management
- Blockchain node implementation
- GPU mining client support
- SDK packages for integration
