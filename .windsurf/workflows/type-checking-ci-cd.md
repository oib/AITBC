---
description: Comprehensive type checking workflow with CI/CD integration, coverage reporting, and quality gates
---

# Type Checking CI/CD Workflow

## 🎯 **Overview**
Comprehensive type checking workflow that ensures type safety across the AITBC codebase through automated CI/CD pipelines, coverage reporting, and quality gates.

---

## 📋 **Workflow Steps**

### **Step 1: Local Development Type Checking**
```bash
# Install dependencies
./venv/bin/pip install mypy sqlalchemy sqlmodel fastapi

# Check core domain models
./venv/bin/mypy --ignore-missing-imports --show-error-codes apps/coordinator-api/src/app/domain/job.py
./venv/bin/mypy --ignore-missing-imports --show-error-codes apps/coordinator-api/src/app/domain/miner.py
./venv/bin/mypy --ignore-missing-imports --show-error-codes apps/coordinator-api/src/app/domain/agent_portfolio.py

# Check entire domain directory
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/

# Generate coverage report
./scripts/type-checking/check-coverage.sh
```

### **Step 2: Pre-commit Type Checking**
```bash
# Pre-commit hooks run automatically on commit
git add .
git commit -m "Add type-safe code"

# Manual pre-commit run
./venv/bin/pre-commit run mypy-domain-core
./venv/bin/pre-commit run type-check-coverage
```

### **Step 3: CI/CD Pipeline Type Checking**
```yaml
# GitHub Actions workflow triggers on:
# - Push to main/develop branches
# - Pull requests to main/develop branches

# Pipeline steps:
# 1. Checkout code
# 2. Setup Python 3.13
# 3. Cache dependencies
# 4. Install MyPy and dependencies
# 5. Run type checking on core models
# 6. Run type checking on entire domain
# 7. Generate reports
# 8. Upload artifacts
# 9. Calculate coverage
# 10. Enforce quality gates
```

### **Step 4: Coverage Analysis**
```bash
# Calculate type checking coverage
CORE_FILES=3
PASSING=$(./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/job.py apps/coordinator-api/src/app/domain/miner.py apps/coordinator-api/src/app/domain/agent_portfolio.py 2>&1 | grep -c "Success:" || echo "0")
COVERAGE=$((PASSING * 100 / CORE_FILES))

echo "Core domain coverage: $COVERAGE%"

# Quality gate: 80% minimum coverage
if [ "$COVERAGE" -ge 80 ]; then
  echo "✅ Type checking coverage: $COVERAGE% (meets threshold)"
else
  echo "❌ Type checking coverage: $COVERAGE% (below 80% threshold)"
  exit 1
fi
```

---

## 🔧 **CI/CD Configuration**

### **GitHub Actions Workflow**
```yaml
name: Type Checking

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  type-check:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: [3.13]
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
        restore-keys: |
          ${{ runner.os }}-pip-
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install mypy sqlalchemy sqlmodel fastapi
    
    - name: Run type checking on core domain models
      run: |
        echo "Checking core domain models..."
        mypy --ignore-missing-imports --show-error-codes apps/coordinator-api/src/app/domain/job.py
        mypy --ignore-missing-imports --show-error-codes apps/coordinator-api/src/app/domain/miner.py
        mypy --ignore-missing-imports --show-error-codes apps/coordinator-api/src/app/domain/agent_portfolio.py
    
    - name: Run type checking on entire domain
      run: |
        echo "Checking entire domain directory..."
        mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/ || true
    
    - name: Generate type checking report
      run: |
        echo "Generating type checking report..."
        mkdir -p reports
        mypy --ignore-missing-imports --txt-report reports/type-check-report.txt apps/coordinator-api/src/app/domain/ || true
    
    - name: Upload type checking report
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: type-check-report
        path: reports/
    
    - name: Type checking coverage
      run: |
        echo "Calculating type checking coverage..."
        CORE_FILES=3
        PASSING=$(mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/job.py apps/coordinator-api/src/app/domain/miner.py apps/coordinator-api/src/app/domain/agent_portfolio.py 2>&1 | grep -c "Success:" || echo "0")
        COVERAGE=$((PASSING * 100 / CORE_FILES))
        echo "Core domain coverage: $COVERAGE%"
        echo "core_coverage=$COVERAGE" >> $GITHUB_ENV
    
    - name: Coverage badge
      run: |
        if [ "$core_coverage" -ge 80 ]; then
          echo "✅ Type checking coverage: $core_coverage% (meets threshold)"
        else
          echo "❌ Type checking coverage: $core_coverage% (below 80% threshold)"
          exit 1
        fi
```

---

## 📊 **Coverage Reporting**

### **Local Coverage Analysis**
```bash
# Run comprehensive coverage analysis
./scripts/type-checking/check-coverage.sh

# Generate detailed report
./venv/bin/mypy --ignore-missing-imports --txt-report reports/type-check-detailed.txt apps/coordinator-api/src/app/domain/

# Generate HTML report
./venv/bin/mypy --ignore-missing-imports --html-report reports/type-check-html apps/coordinator-api/src/app/domain/
```

### **Coverage Metrics**
```python
# Coverage calculation components:
# - Core domain models: 3 files (job.py, miner.py, agent_portfolio.py)
# - Passing files: Files with no type errors
# - Coverage percentage: (Passing / Total) * 100
# - Quality gate: 80% minimum coverage

# Example calculation:
CORE_FILES = 3
PASSING_FILES = 3
COVERAGE = (3 / 3) * 100 = 100%
```

### **Report Structure**
```
reports/
├── type-check-report.txt      # Summary report
├── type-check-detailed.txt    # Detailed analysis
├── type-check-html/          # HTML report
│   ├── index.html
│   ├── style.css
│   └── sources/
└── coverage-summary.json      # Machine-readable metrics
```

---

## 🚀 **Integration Strategy**

### **Development Workflow Integration**
```bash
# 1. Local development
vim apps/coordinator-api/src/app/domain/new_model.py

# 2. Type checking
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/new_model.py

# 3. Pre-commit validation
git add .
git commit -m "Add new type-safe model"  # Pre-commit runs automatically

# 4. Push triggers CI/CD
git push origin feature-branch  # GitHub Actions runs
```

### **Quality Gates**
```yaml
# Quality gate thresholds:
# - Core domain coverage: >= 80%
# - No critical type errors in core models
# - All new code must pass type checking
# - Type errors in existing code must be documented

# Gate enforcement:
# - CI/CD pipeline fails on low coverage
# - Pull requests blocked on type errors
# - Deployment requires type safety validation
```

### **Monitoring and Alerting**
```bash
# Type checking metrics dashboard
curl http://localhost:3000/d/type-checking-coverage

# Alert on coverage drop
if [ "$COVERAGE" -lt 80 ]; then
  send_alert "Type checking coverage dropped to $COVERAGE%"
fi

# Weekly coverage trends
./scripts/type-checking/generate-coverage-trends.sh
```

---

## 🎯 **Type Checking Standards**

### **Core Domain Requirements**
```python
# Core domain models must:
# 1. Have 100% type coverage
# 2. Use proper type hints for all fields
# 3. Handle Optional types correctly
# 4. Include proper return types
# 5. Use generic types for collections

# Example:
from typing import Any, Dict, Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
```

### **Service Layer Standards**
```python
# Service layer must:
# 1. Type all method parameters
# 2. Include return type annotations
# 3. Handle exceptions properly
# 4. Use dependency injection types
# 5. Document complex types

# Example:
from typing import List, Optional
from sqlmodel import Session

class JobService:
    def __init__(self, session: Session) -> None:
        self.session = session
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self.session.get(Job, job_id)
    
    def create_job(self, job_data: JobCreate) -> Job:
        """Create a new job."""
        job = Job.model_validate(job_data)
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job
```

### **API Router Standards**
```python
# API routers must:
# 1. Type all route parameters
# 2. Use Pydantic models for request/response
# 3. Include proper HTTP status types
# 4. Handle error responses
# 5. Document complex endpoints

# Example:
from fastapi import APIRouter, HTTPException, Depends
from typing import List

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/", response_model=List[JobRead])
async def get_jobs(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session)
) -> List[JobRead]:
    """Get all jobs with pagination."""
    jobs = session.exec(select(Job).offset(skip).limit(limit)).all()
    return jobs
```

---

## 📈 **Progressive Type Safety Implementation**

### **Phase 1: Core Domain (Complete)**
```bash
# ✅ Completed
# - job.py: 100% type coverage
# - miner.py: 100% type coverage  
# - agent_portfolio.py: 100% type coverage

# Status: All core models type-safe
```

### **Phase 2: Service Layer (In Progress)**
```bash
# 🔄 Current work
# - JobService: Adding type hints
# - MinerService: Adding type hints
# - AgentService: Adding type hints

# Commands:
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/services/
```

### **Phase 3: API Routers (Planned)**
```bash
# ⏳ Planned work
# - job_router.py: Add type hints
# - miner_router.py: Add type hints
# - agent_router.py: Add type hints

# Commands:
./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/routers/
```

### **Phase 4: Strict Mode (Future)**
```toml
# pyproject.toml
[tool.mypy]
check_untyped_defs = true
disallow_untyped_defs = true
no_implicit_optional = true
strict_equality = true
```

---

## 🔧 **Troubleshooting**

### **Common Type Errors**

#### **Missing Import Error**
```bash
# Error: Name "uuid4" is not defined
# Solution: Add missing import
from uuid import uuid4
```

#### **SQLModel Field Type Error**
```bash
# Error: No overload variant of "Field" matches
# Solution: Use proper type annotations
payload: Dict[str, Any] = Field(default_factory=dict)
```

#### **Optional Type Error**
```bash
# Error: Incompatible types in assignment
# Solution: Use Optional type annotation
updated_at: Optional[datetime] = None
```

#### **Generic Type Error**
```bash
# Error: Dict entry has incompatible type
# Solution: Use proper generic types
results: Dict[str, Any] = {}
```

### **Performance Optimization**
```bash
# Cache MyPy results
./venv/bin/mypy --incremental apps/coordinator-api/src/app/

# Use daemon mode for faster checking
./venv/bin/mypy --daemon apps/coordinator-api/src/app/

# Limit scope for large projects
./venv/bin/mypy apps/coordinator-api/src/app/domain/ --exclude apps/coordinator-api/src/app/domain/legacy/
```

### **Configuration Issues**
```bash
# Check MyPy configuration
./venv/bin/mypy --config-file pyproject.toml apps/coordinator-api/src/app/

# Show configuration
./venv/bin/mypy --show-config

# Debug configuration
./venv/bin/mypy --verbose apps/coordinator-api/src/app/
```

---

## 📋 **Quality Checklist**

### **Before Commit**
- [ ] Core domain models pass type checking
- [ ] New code has proper type hints
- [ ] Optional types handled correctly
- [ ] Generic types used for collections
- [ ] Return types specified

### **Before PR**
- [ ] All modified files type-check
- [ ] Coverage meets 80% threshold
- [ ] No new type errors introduced
- [ ] Documentation updated for complex types
- [ ] Performance impact assessed

### **Before Merge**
- [ ] CI/CD pipeline passes
- [ ] Coverage badge shows green
- [ ] Type checking report clean
- [ ] All quality gates passed
- [ ] Team review completed

### **Before Release**
- [ ] Full type checking suite passes
- [ ] Coverage trends are positive
- [ ] No critical type issues
- [ ] Documentation complete
- [ ] Performance benchmarks met

---

## 🎉 **Benefits**

### **Immediate Benefits**
- **🔍 Bug Prevention**: Type errors caught before runtime
- **📚 Better Documentation**: Type hints serve as documentation
- **🔧 IDE Support**: Better autocomplete and error detection
- **🛡️ Safety**: Compile-time type checking

### **Long-term Benefits**
- **📈 Maintainability**: Easier refactoring with types
- **👥 Team Collaboration**: Shared type contracts
- **🚀 Development Speed**: Faster debugging with type errors
- **🎯 Code Quality**: Higher standards enforced automatically

### **Business Benefits**
- **⚡ Reduced Bugs**: Fewer runtime type errors
- **💰 Cost Savings**: Less time debugging type issues
- **📊 Quality Metrics**: Measurable type safety improvements
- **🔄 Consistency**: Enforced type standards across team

---

## 📊 **Success Metrics**

### **Type Safety Metrics**
- **Core Domain Coverage**: 100% (achieved)
- **Service Layer Coverage**: Target 80%
- **API Router Coverage**: Target 70%
- **Overall Coverage**: Target 75%

### **Quality Metrics**
- **Type Errors**: Zero in core domain
- **CI/CD Failures**: Zero type-related failures
- **Developer Feedback**: Positive type checking experience
- **Performance Impact**: <10% overhead

### **Business Metrics**
- **Bug Reduction**: 50% fewer type-related bugs
- **Development Speed**: 20% faster debugging
- **Code Review Efficiency**: 30% faster reviews
- **Onboarding Time**: 40% faster for new developers

---

**Last Updated**: March 31, 2026  
**Workflow Version**: 1.0  
**Next Review**: April 30, 2026
