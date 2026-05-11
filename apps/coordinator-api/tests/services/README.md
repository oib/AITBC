# Service Tests README

## Test Structure

This directory contains tests for the modularized service components:

### Advanced RL Tests (`test_advanced_rl/`)
- `test_agents.py` - Tests for PPO, SAC, and RainbowDQN neural network agents
- `test_engine.py` - Tests for the AdvancedReinforcementLearningEngine

**Requirements:**
- PyTorch (`torch`)
- Full AITBC environment with domain models
- pytest-asyncio for async tests

### Certification Tests (`test_certification/`)
- `test_certification_system.py` - Tests for CertificationSystem
- `test_partnership_manager.py` - Tests for PartnershipManager
- `test_badge_system.py` - Tests for BadgeSystem

**Requirements:**
- Full AITBC environment with domain models
- aitbc package for logging
- pytest-asyncio for async tests

### Multi-Modal Fusion Tests (`test_multi_modal_fusion/`)
- `test_neural_modules.py` - Tests for CrossModalAttention, MultiModalTransformer, AdaptiveModalityWeighting
- `test_fusion_engine.py` - Tests for MultiModalFusionEngine

**Requirements:**
- PyTorch (`torch`)
- NumPy (`numpy`)
- Full AITBC environment with domain models
- pytest-asyncio for async tests

## Running Tests

### Prerequisites
Ensure you have the full AITBC environment set up with all dependencies:
```bash
cd /opt/aitbc
source venv/bin/activate  # or use your preferred environment
```

### Install additional dependencies
```bash
pip install torch pytest-asyncio
```

### Run tests with proper PYTHONPATH
```bash
cd /opt/aitbc/apps/coordinator-api
PYTHONPATH=/opt/aitbc/apps/coordinator-api/src:/opt/aitbc python3 -m pytest tests/services/ -v
```

### Run specific test suites
```bash
# Advanced RL tests (requires torch)
PYTHONPATH=/opt/aitbc/apps/coordinator-api/src:/opt/aitbc python3 -m pytest tests/services/test_advanced_rl/ -v

# Certification tests
PYTHONPATH=/opt/aitbc/apps/coordinator-api/src:/opt/aitbc python3 -m pytest tests/services/test_certification/ -v

# Multi-modal fusion tests (requires torch)
PYTHONPATH=/opt/aitbc/apps/coordinator-api/src:/opt/aitbc python3 -m pytest tests/services/test_multi_modal_fusion/ -v
```

## Test Coverage

These tests were created as part of the service modularization effort (Phase 2-3 of the refactoring plan). They provide:

- Unit tests for neural network components (advanced_rl, multi_modal_fusion)
- Integration tests for certification, partnership, and badge systems
- Coverage of key methods and initialization logic

The tests use mocking where appropriate to isolate components and test individual functionality.

## Current Status

- ✅ Test files created for all modularized components
- ✅ Test structure follows pytest best practices
- ⚠️ Tests require full AITBC environment to run (expected for integration tests)
- ⚠️ PyTorch-dependent tests require torch installation

## Future Improvements

- Add CI/CD integration for automated test running
- Increase test coverage to 100% as per Phase 3 goals
- Add performance benchmarks for neural network components
- Add property-based tests where applicable
