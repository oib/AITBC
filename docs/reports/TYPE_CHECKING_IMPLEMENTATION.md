# AITBC Type Checking Implementation Plan

## 🎯 **Objective**
Implement gradual type checking for the AITBC codebase to improve code quality and catch bugs early.

## 📊 **Current Status**
- **mypy version**: 1.20.0 installed
- **Configuration**: Updated to pragmatic settings
- **Errors found**: 685 errors across 57 files (initial scan)
- **Strategy**: Gradual implementation starting with critical files

## 🚀 **Implementation Strategy**

### **Phase 1: Foundation** ✅ COMPLETE
- [x] Install mypy with consolidated dependencies
- [x] Update pyproject.toml with pragmatic mypy configuration
- [x] Configure ignore patterns for external libraries
- [x] Set up gradual implementation approach

### **Phase 2: Critical Files** (In Progress)
Focus on the most important files first:

#### **Priority 1: Core Domain Models**
- `apps/coordinator-api/src/app/domain/*.py`
- `apps/coordinator-api/src/app/storage/db.py`
- `apps/coordinator-api/src/app/storage/models.py`

#### **Priority 2: Main API Routers**
- `apps/coordinator-api/src/app/routers/agent_performance.py`
- `apps/coordinator-api/src/app/routers/jobs.py`
- `apps/coordinator-api/src/app/routers/miners.py`

#### **Priority 3: Core Services**
- `apps/coordinator-api/src/app/services/jobs.py`
- `apps/coordinator-api/src/app/services/miners.py`

### **Phase 3: Incremental Expansion** (Future)
- Add more files gradually
- Increase strictness over time
- Enable more mypy checks progressively

## 🔧 **Current Configuration**

### **Pragmatic Settings**
```toml
[tool.mypy]
python_version = "3.13"
warn_return_any = true
warn_unused_configs = true
# Gradual approach - less strict initially
check_untyped_defs = false
disallow_incomplete_defs = false
no_implicit_optional = false
warn_no_return = true
```

### **Ignore Patterns**
- External libraries: `torch.*`, `cv2.*`, `pandas.*`, etc.
- Current app code: `apps.coordinator-api.src.app.*` (temporarily)

## 📋 **Implementation Steps**

### **Step 1: Fix Domain Models**
Add type hints to core domain models first:
```python
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field

class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)
    client_id: str
    state: str  # Will be converted to enum
    payload: Dict[str, Any]
```

### **Step 2: Fix Database Layer**
Add proper type hints to database functions:
```python
from typing import List, Optional
from sqlalchemy.orm import Session

def get_job_by_id(session: Session, job_id: str) -> Optional[Job]:
    """Get a job by its ID"""
    return session.query(Job).filter(Job.id == job_id).first()
```

### **Step 3: Fix API Endpoints**
Add type hints to FastAPI endpoints:
```python
from typing import List, Dict, Any
from fastapi import Depends

@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    session: Session = Depends(get_session),
    state: Optional[str] = None
) -> List[JobResponse]:
    """List jobs with optional state filter"""
    pass
```

## 🎯 **Success Metrics**

### **Short-term Goals**
- [ ] 0 type errors in domain models
- [ ] 0 type errors in database layer
- [ ] <50 type errors in main routers
- [ ] Basic mypy passing on critical files

### **Long-term Goals**
- [ ] Full strict type checking on new code
- [ ] <100 type errors in entire codebase
- [ ] Type checking in CI/CD pipeline
- [ ] Type coverage >80%

## 🛠️ **Tools and Commands**

### **Type Checking Commands**
```bash
# Check specific file
./venv/bin/mypy apps/coordinator-api/src/app/domain/job.py

# Check with error codes
./venv/bin/mypy --show-error-codes apps/coordinator-api/src/app/routers/

# Incremental checking
./venv/bin/mypy --incremental apps/coordinator-api/src/app/

# Generate type coverage report
./venv/bin/mypy --txt-report report.txt apps/coordinator-api/src/app/
```

### **Common Error Types and Fixes**

#### **no-untyped-def**
```python
# Before
def get_job(job_id: str):
    pass

# After  
def get_job(job_id: str) -> Optional[Job]:
    pass
```

#### **arg-type**
```python
# Before
def process_job(session, job_id: str):
    pass

# After
def process_job(session: Session, job_id: str) -> bool:
    pass
```

#### **assignment**
```python
# Before
job.state = "pending"  # str vs JobState enum

# After
job.state = JobState.PENDING
```

## 📈 **Progress Tracking**

### **Current Status**
- **Total files**: 57 files with type errors
- **Critical files**: 15 files prioritized
- **Type errors**: 685 (initial scan)
- **Configuration**: Pragmatic mode enabled

### **Next Actions**
1. Fix domain models (highest priority)
2. Fix database layer
3. Fix main API routers
4. Gradually expand to other files
5. Increase strictness over time

## 🔄 **Integration with CI/CD**

### **Pre-commit Hook**
Add to `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: mypy
      name: mypy
      entry: ./venv/bin/mypy
      language: system
      args: [--ignore-missing-imports]
      files: ^apps/coordinator-api/src/app/domain/
```

### **GitHub Actions**
```yaml
- name: Type checking
  run: |
    ./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/domain/
    ./venv/bin/mypy --ignore-missing-imports apps/coordinator-api/src/app/storage/
```

---

**Status**: 🔄 Phase 2 In Progress  
**Next Step**: Fix domain models  
**Timeline**: 2-3 weeks for gradual implementation
