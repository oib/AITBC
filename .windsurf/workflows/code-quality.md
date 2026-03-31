---
description: Comprehensive code quality workflow with pre-commit hooks, formatting, linting, type checking, and security scanning
---

# Code Quality Workflow

## 🎯 **Overview**
Comprehensive code quality assurance workflow that ensures high standards across the AITBC codebase through automated pre-commit hooks, formatting, linting, type checking, and security scanning.

---

## 📋 **Workflow Steps**

### **Step 1: Setup Pre-commit Environment**
```bash
# Install pre-commit hooks
./venv/bin/pre-commit install

# Verify installation
./venv/bin/pre-commit --version
```

### **Step 2: Run All Quality Checks**
```bash
# Run all hooks on all files
./venv/bin/pre-commit run --all-files

# Run on staged files (git commit)
./venv/bin/pre-commit run
```

### **Step 3: Individual Quality Categories**

#### **🧹 Code Formatting**
```bash
# Black code formatting
./venv/bin/black --line-length=127 --check .

# Auto-fix formatting issues
./venv/bin/black --line-length=127 .

# Import sorting with isort
./venv/bin/isort --profile=black --line-length=127 .
```

#### **🔍 Linting & Code Analysis**
```bash
# Flake8 linting
./venv/bin/flake8 --max-line-length=127 --extend-ignore=E203,W503 .

# Pydocstyle documentation checking
./venv/bin/pydocstyle --convention=google .

# Python version upgrade checking
./venv/bin/pyupgrade --py311-plus .
```

#### **🔍 Type Checking**
```bash
# Core domain models type checking
./venv/bin/mypy --ignore-missing-imports --show-error-codes apps/coordinator-api/src/app/domain/job.py apps/coordinator-api/src/app/domain/miner.py apps/coordinator-api/src/app/domain/agent_portfolio.py

# Type checking coverage analysis
./scripts/type-checking/check-coverage.sh

# Full mypy checking
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/
```

#### **🛡️ Security Scanning**
```bash
# Bandit security scanning
./venv/bin/bandit -r . -f json -o bandit-report.json

# Safety dependency vulnerability check
./venv/bin/safety check --json --output safety-report.json

# Safety dependency check for requirements files
./venv/bin/safety check requirements.txt
```

#### **🧪 Testing**
```bash
# Unit tests
pytest tests/unit/ --tb=short -q

# Security tests
pytest tests/security/ --tb=short -q

# Performance tests
pytest tests/performance/test_performance_lightweight.py::TestPerformance::test_cli_performance --tb=short -q
```

---

## 🔧 **Pre-commit Configuration**

### **Repository Structure**
```yaml
repos:
  # Basic file checks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-json
      - id: check-merge-conflict
      - id: debug-statements
      - id: check-docstring-first
      - id: check-executables-have-shebangs
      - id: check-toml
      - id: check-xml
      - id: check-case-conflict
      - id: check-ast

  # Code formatting
  - repo: https://github.com/psf/black
    rev: 26.3.1
    hooks:
      - id: black
        language_version: python3
        args: [--line-length=127]

  # Import sorting
  - repo: https://github.com/pycqa/isort
    rev: 8.0.1
    hooks:
      - id: isort
        args: [--profile=black, --line-length=127]

  # Linting
  - repo: https://github.com/pycqa/flake8
    rev: 7.3.0
    hooks:
      - id: flake8
        args: [--max-line-length=127, --extend-ignore=E203,W503]

  # Type checking
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.19.1
    hooks:
      - id: mypy
        additional_dependencies: [types-requests, types-python-dateutil]
        args: [--ignore-missing-imports]

  # Security scanning
  - repo: https://github.com/PyCQA/bandit
    rev: 1.9.4
    hooks:
      - id: bandit
        args: [-r, ., -f, json, -o, bandit-report.json]
        pass_filenames: false

  # Documentation checking
  - repo: https://github.com/pycqa/pydocstyle
    rev: 6.3.0
    hooks:
      - id: pydocstyle
        args: [--convention=google]

  # Python version upgrade
  - repo: https://github.com/asottile/pyupgrade
    rev: v3.21.2
    hooks:
      - id: pyupgrade
        args: [--py311-plus]

  # Dependency security
  - repo: https://github.com/Lucas-C/pre-commit-hooks-safety
    rev: v1.4.2
    hooks:
      - id: python-safety-dependencies-check
        files: requirements.*\.txt$

  - repo: https://github.com/Lucas-C/pre-commit-hooks-safety
    rev: v1.3.2
    hooks:
      - id: python-safety-check
        args: [--json, --output, safety-report.json]

  # Local hooks
  - repo: local
    hooks:
      - id: pytest-check
        name: pytest-check
        entry: pytest
        language: system
        args: [tests/unit/, --tb=short, -q]
        pass_filenames: false
        always_run: true

      - id: security-check
        name: security-check
        entry: pytest
        language: system
        args: [tests/security/, --tb=short, -q]
        pass_filenames: false
        always_run: true

      - id: performance-check
        name: performance-check
        entry: pytest
        language: system
        args: [tests/performance/test_performance_lightweight.py::TestPerformance::test_cli_performance, --tb=short, -q]
        pass_filenames: false
        always_run: true

      - id: mypy-domain-core
        name: mypy-domain-core
        entry: ./venv/bin/mypy
        language: system
        args: [--ignore-missing-imports, --show-error-codes]
        files: ^apps/coordinator-api/src/app/domain/(job|miner|agent_portfolio)\.py$
        pass_filenames: false

      - id: type-check-coverage
        name: type-check-coverage
        entry: ./scripts/type-checking/check-coverage.sh
        language: script
        files: ^apps/coordinator-api/src/app/
        pass_filenames: false
```

---

## 📊 **Quality Metrics & Reporting**

### **Coverage Reports**
```bash
# Type checking coverage
./scripts/type-checking/check-coverage.sh

# Security scan reports
cat bandit-report.json | jq '.results | length'
cat safety-report.json | jq '.vulnerabilities | length'

# Test coverage
pytest --cov=apps --cov-report=html tests/
```

### **Quality Score Calculation**
```python
# Quality score components:
# - Code formatting: 20%
# - Linting compliance: 20%
# - Type coverage: 25%
# - Test coverage: 20%
# - Security compliance: 15%

# Overall quality score >= 80% required
```

### **Automated Reporting**
```bash
# Generate comprehensive quality report
./scripts/quality/generate-quality-report.sh

# Quality dashboard metrics
curl http://localhost:8000/metrics/quality
```

---

## 🚀 **Integration with Development Workflow**

### **Before Commit**
```bash
# 1. Stage your changes
git add .

# 2. Pre-commit hooks run automatically
git commit -m "Your commit message"

# 3. If any hook fails, fix the issues and try again
```

### **Manual Quality Checks**
```bash
# Run all quality checks manually
./venv/bin/pre-commit run --all-files

# Check specific category
./venv/bin/black --check .
./venv/bin/flake8 .
./venv/bin/mypy apps/coordinator-api/src/app/
```

### **CI/CD Integration**
```yaml
# GitHub Actions workflow
name: Code Quality
on: [push, pull_request]
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run pre-commit
        run: ./venv/bin/pre-commit run --all-files
```

---

## 🎯 **Quality Standards**

### **Code Formatting Standards**
- **Black**: Line length 127 characters
- **isort**: Black profile compatibility
- **Python 3.13+**: Modern Python syntax

### **Linting Standards**
- **Flake8**: Line length 127, ignore E203, W503
- **Pydocstyle**: Google convention
- **No debug statements**: Production code only

### **Type Safety Standards**
- **MyPy**: Strict mode for new code
- **Coverage**: 90% minimum for core domain
- **Error handling**: Proper exception types

### **Security Standards**
- **Bandit**: Zero high-severity issues
- **Safety**: No known vulnerabilities
- **Dependencies**: Regular security updates

### **Testing Standards**
- **Coverage**: 80% minimum test coverage
- **Unit tests**: All business logic tested
- **Security tests**: Authentication and authorization
- **Performance tests**: Critical paths validated

---

## 📈 **Quality Improvement Workflow**

### **1. Initial Setup**
```bash
# Install pre-commit hooks
./venv/bin/pre-commit install

# Run initial quality check
./venv/bin/pre-commit run --all-files

# Fix any issues found
./venv/bin/black .
./venv/bin/isort .
# Fix other issues manually
```

### **2. Daily Development**
```bash
# Make changes
vim your_file.py

# Stage and commit (pre-commit runs automatically)
git add your_file.py
git commit -m "Add new feature"

# If pre-commit fails, fix issues and retry
git commit -m "Add new feature"
```

### **3. Quality Monitoring**
```bash
# Check quality metrics
./scripts/quality/check-quality-metrics.sh

# Generate quality report
./scripts/quality/generate-quality-report.sh

# Review quality trends
./scripts/quality/quality-trends.sh
```

---

## 🔧 **Troubleshooting**

### **Common Issues**

#### **Black Formatting Issues**
```bash
# Check formatting issues
./venv/bin/black --check .

# Auto-fix formatting
./venv/bin/black .

# Specific file
./venv/bin/black --check path/to/file.py
```

#### **Import Sorting Issues**
```bash
# Check import sorting
./venv/bin/isort --check-only .

# Auto-fix imports
./venv/bin/isort .

# Specific file
./venv/bin/isort path/to/file.py
```

#### **Type Checking Issues**
```bash
# Check type errors
./venv/bin/mypy apps/coordinator-api/src/app/

# Ignore specific errors
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/

# Show error codes
./venv/bin/mypy --show-error-codes apps/coordinator-api/src/app/
```

#### **Security Issues**
```bash
# Check security issues
./venv/bin/bandit -r .

# Generate security report
./venv/bin/bandit -r . -f json -o security-report.json

# Check dependencies
./venv/bin/safety check
```

### **Performance Optimization**

#### **Pre-commit Performance**
```bash
# Run hooks in parallel
./venv/bin/pre-commit run --all-files --parallel

# Skip slow hooks during development
./venv/bin/pre-commit run --all-files --hook-stage manual

# Cache dependencies
./venv/bin/pre-commit run --all-files --cache
```

#### **Selective Hook Running**
```bash
# Run specific hooks
./venv/bin/pre-commit run black flake8 mypy

# Run on specific files
./venv/bin/pre-commit run --files apps/coordinator-api/src/app/

# Skip hooks
./venv/bin/pre-commit run --all-files --skip mypy
```

---

## 📋 **Quality Checklist**

### **Before Commit**
- [ ] Code formatted with Black
- [ ] Imports sorted with isort
- [ ] Linting passes with Flake8
- [ ] Type checking passes with MyPy
- [ ] Documentation follows Pydocstyle
- [ ] No security vulnerabilities
- [ ] All tests pass
- [ ] Performance tests pass

### **Before Merge**
- [ ] Code review completed
- [ ] Quality score >= 80%
- [ ] Test coverage >= 80%
- [ ] Type coverage >= 90% (core domain)
- [ ] Security scan clean
- [ ] Documentation updated
- [ ] Performance benchmarks met

### **Before Release**
- [ ] Full quality suite passes
- [ ] Integration tests pass
- [ ] Security audit complete
- [ ] Performance validation
- [ ] Documentation complete
- [ ] Release notes prepared

---

## 🎉 **Benefits**

### **Immediate Benefits**
- **Consistent Code**: Uniform formatting and style
- **Bug Prevention**: Type checking and linting catch issues early
- **Security**: Automated vulnerability scanning
- **Quality Assurance**: Comprehensive test coverage

### **Long-term Benefits**
- **Maintainability**: Clean, well-documented code
- **Developer Experience**: Automated quality gates
- **Team Consistency**: Shared quality standards
- **Production Readiness**: Enterprise-grade code quality

---

**Last Updated**: March 31, 2026  
**Workflow Version**: 1.0  
**Next Review**: April 30, 2026
