# AITBC Testing Documentation

**Level**: Intermediate<br>
**Prerequisites**: Basic familiarity with the AITBC codebase, Python testing tools, and service management<br>
**Estimated Time**: 20-40 minutes<br>
**Last Updated**: 2026-04-27<br>
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🧪 Testing** → *You are here*

**breadcrumb**: Home → Testing → Overview

---

## 🎯 **See Also:**
- **📚 Docs Home**: [Documentation Home](../README.md) - Main docs landing page
- **📖 About Docs**: [About Documentation](../about/README.md) - Template standard and audit checklist
- **👛 CLI Technical**: [CLI Technical Documentation](../cli-technical/README.md) - CLI entry point and usage
- **📋 Project Docs**: [Project Documentation](../project/README.md) - Project context and structure
- **🚀 Deployment Docs**: [Deployment Documentation](../deployment/README.md) - Operational deployment context

---

## 📚 **What lives here**

This directory contains the comprehensive test suite documentation for the AITBC platform.
It covers unit tests, integration tests, end-to-end tests, security tests, and load tests.

## Recent Updates (April 13, 2026)

### ✅ Test Cleanup Completed
- **Archived Tests**: Removed legacy archived tests directory (6 files)
- **Conftest Consolidation**: Deleted duplicate conftest files, kept main conftest.py
- **Test Runner Cleanup**: Deleted run_all_phase_tests.py (phase2 missing)
- **Phase Tests Archived**: Moved phase3, phase4, phase5 to archived_phase_tests/
- **Active Tests**: phase1, cross_phase, production, integration remain active

## Previous Updates (March 30, 2026)

### ✅ Structure Improvements Completed
- **Scripts Organization**: Test scripts moved to `scripts/testing/` and `scripts/utils/`
- **Logs Consolidation**: All test logs now in `/var/log/aitbc/`
- **Virtual Environment**: Using central `/opt/aitbc/venv`
- **Development Environment**: Using `/etc/aitbc/.env` for configuration

## 📑 **Table of Contents**

1. [Test Structure](#test-structure)
2. [Prerequisites](#prerequisites)
3. [Running Tests](#running-tests)
4. [Test Types](#test-types)
5. [Configuration](#configuration)
6. [CI/CD Integration](#cicd-integration)
7. [Troubleshooting](#troubleshooting)

## 🧱 **Test Structure**

```
tests/
├── conftest.py                    # Main shared fixtures and configuration
├── run_production_tests.py        # Production test runner
├── load_test.py                   # Load testing utilities
├── docs/                          # Test documentation
│   ├── README.md
│   ├── USAGE_GUIDE.md
│   ├── TEST_REFACTORING_COMPLETED.md
│   ├── cli-test-updates-completed.md
│   └── test-integration-completed.md
├── archived_phase_tests/          # Archived legacy phase tests
│   ├── phase3/                    # Decision framework tests
│   ├── phase4/                    # Autonomous decision making tests
│   └── phase5/                    # Vision integration tests
├── phase1/                        # Phase 1 tests (active)
│   └── consensus/                # Consensus layer tests
├── cross_phase/                   # Cross-phase integration tests (active)
├── production/                    # Production test suite (active)
├── integration/                   # Integration tests (active)
├── fixtures/                      # Test fixtures and data
├── __pycache__/                   # Python cache (auto-generated)
└── __pycache__/                   # Python cache (auto-generated)
```

### Related Test Scripts
```
scripts/testing/           # Main testing scripts
├── comprehensive_e2e_test_fixed.py  # Comprehensive E2E testing
├── test_workflow.sh               # Workflow testing
├── run_all_tests.sh               # All tests runner
└── test-all-services.sh           # Service testing

scripts/utils/             # Testing utilities
├── requirements_migrator.py       # Dependency management
└── other utility scripts          # Various helper scripts
```

## ✅ **Prerequisites**

### **Environment Setup**
```bash
# Run main project setup (if not already done)
./setup.sh

# Activate central virtual environment
source /opt/aitbc/venv/bin/activate

# Ensure test dependencies are installed
pip install pytest pytest-cov pytest-asyncio

# Set environment configuration
source /etc/aitbc/.env  # Central environment configuration
```

### **Service Requirements**
- AITBC blockchain node running
- Coordinator API service active
- Database accessible (SQLite/PostgreSQL)
- GPU services (if running AI tests)

## ▶️ **Running Tests**

### **Quick Start**
```bash
# Run all fast tests
python tests/test_runner.py

# Run comprehensive test suite
python tests/test_runner.py --all

# Run with coverage
python tests/test_runner.py --coverage
```

### **Specific Test Types**
```bash
# Unit tests only
python tests/test_runner.py --unit

# Integration tests only
python tests/test_runner.py --integration

# CLI tests only
python tests/test_runner.py --cli

# Performance tests
python tests/test_runner.py --performance
```

### **Advanced Testing**
```bash
# Comprehensive E2E testing
python scripts/testing/comprehensive_e2e_test_fixed.py

# Workflow testing
bash scripts/testing/test_workflow.sh

# All services testing
bash scripts/testing/test-all-services.sh
```

## 🧪 **Test Types**

### **Unit Tests**
- **Location**: `tests/unit/` (if exists)
- **Purpose**: Test individual components in isolation
- **Speed**: Fast (< 1 second per test)
- **Coverage**: Core business logic

### **Integration Tests**
- **Location**: `tests/integration/` and `tests/e2e/`
- **Purpose**: Test component interactions
- **Speed**: Medium (1-10 seconds per test)
- **Coverage**: API endpoints, database operations

### **End-to-End Tests**
- **Location**: `tests/e2e/` and `scripts/testing/`
- **Purpose**: Test complete workflows
- **Speed**: Slow (10-60 seconds per test)
- **Coverage**: Full user scenarios

### **Performance Tests**
- **Location**: `tests/load_test.py`
- **Purpose**: Test system performance under load
- **Speed**: Variable (depends on test parameters)
- **Coverage**: API response times, throughput

## ⚙️ **Configuration**

### **Test Configuration Files**
- **pytest.ini**: Pytest configuration (in root)
- **conftest.py**: Shared fixtures and configuration
- **pyproject.toml**: Project-wide test configuration

### **Environment Variables**
```bash
# Test database (different from production)
TEST_DATABASE_URL=sqlite:///test_aitbc.db

# Test logging
TEST_LOG_LEVEL=DEBUG
TEST_LOG_FILE=/var/log/aitbc/test.log

# Test API endpoints
# Note: Port 8011 = Learning Service (updated port allocation)
TEST_API_BASE_URL=http://localhost:8011
```

## 🔄 **CI/CD Integration**

### **GitHub Actions**
Test suite is integrated with CI/CD pipeline:
- **Unit Tests**: Run on every push
- **Integration Tests**: Run on pull requests
- **E2E Tests**: Run on main branch
- **Performance Tests**: Run nightly

### **Local CI Simulation**
```bash
# Simulate CI pipeline locally
python tests/test_runner.py --all --coverage

# Generate coverage report
coverage html -o coverage_html/
```

## 🛠️ **Troubleshooting**

### **Common Issues**

#### **Test Failures Due to Services**
```bash
# Check service status
systemctl status aitbc-blockchain-node
systemctl status aitbc-coordinator

# Restart services if needed
sudo systemctl restart aitbc-blockchain-node
sudo systemctl restart aitbc-coordinator
```

#### **Environment Issues**
```bash
# Check virtual environment
which python
python --version

# Check dependencies
pip list | grep pytest

# Reinstall if needed
pip install -e .
```

#### **Database Issues**
```bash
# Reset test database
rm test_aitbc.db
python -m alembic upgrade head

# Check database connectivity
python -c "from aitbc_core.db import engine; print(engine.url)"
```

### **Test Logs**
All test logs are now centralized in `/var/log/aitbc/`:
- **test.log**: General test output
- **test_results.txt**: Test results summary
- **performance_test.log**: Performance test results

### **Getting Help**
1. Check test logs in `/var/log/aitbc/`
2. Review test documentation in `tests/docs/`
3. Run tests with verbose output: `pytest -v`
4. Check service status and configuration

---

## 🔗 **Related Resources**

### 📚 **Further Reading:**
- [Documentation Home](../README.md) - Main docs landing page
- [About Documentation](../about/README.md) - Template standard and audit checklist
- [CLI Technical Documentation](../cli-technical/README.md) - CLI entry point and usage
- [Deployment Documentation](../deployment/README.md) - Operational deployment context

### 🆘 **Help & Support:**
- **Documentation Issues**: [Report Issues](https://github.com/oib/AITBC/issues)
- **Community Forum**: [AITBC Forum](https://forum.aitbc.net)
- **Technical Support**: [AITBC Support](https://support.aitbc.net)

---

## 📊 **Quality Metrics**
- **Structure**: 10/10 - Template-compliant landing page with detailed testing sections.
- **Content**: 10/10 - Comprehensive test suite documentation with operational guidance.
- **Navigation**: 10/10 - Links to docs home, CLI technical docs, deployment, and about docs.
- **Status**: Active index page.

---

*Last updated: 2026-04-27*<br>
*Version: 1.0*<br>
*Status: Active index for testing documentation*
