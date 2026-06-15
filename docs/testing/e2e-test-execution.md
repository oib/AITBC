# E2E Test Execution and Maintenance

**Version:** 1.0
**Date:** 2026-05-11
**Status:** Draft
**Purpose:** Define test execution, reporting, and maintenance for E2E testing

## Overview

This document defines test execution procedures, reporting formats, and maintenance requirements for end-to-end testing.

## Test Implementation

### Test Framework

**Recommended Framework:** pytest with pytest-asyncio

**Additional Tools:**
- `httpx` for HTTP client
- `playwright` for browser automation (if UI testing needed)
- Systemd services for service orchestration

### Test Structure

```
tests/e2e/
├── conftest.py                 # E2E fixtures and configuration
├── test_user_registration.py   # User registration E2E tests
├── test_job_lifecycle.py       # Job submission and processing E2E tests
├── test_payment_flow.py        # Payment and receipt E2E tests
├── test_miner_operations.py    # Miner registration and operation E2E tests
├── test_agent_communication.py # Agent communication E2E tests
├── test_blockchain_transactions.py # Blockchain transaction E2E tests
├── test_api_compliance.py      # API contract compliance E2E tests
├── fixtures/                   # Test data fixtures
│   ├── users.py
│   ├── wallets.py
│   ├── jobs.py
│   └── blockchain.py
└── utils/                      # Test utilities
    ├── helpers.py
    └── assertions.py
```

### Sample Test Structure

```python
import pytest
import httpx
from datetime import datetime, timedelta

@pytest.mark.e2e
class TestJobLifecycle:
    """End-to-end test for complete job lifecycle"""

    @pytest.fixture
    async def client(self):
        """HTTP client for API calls"""
        async with httpx.AsyncClient() as client:
            yield client

    async def test_complete_job_execution(self, client):
        """Test complete job from submission to completion"""
        # 1. Submit job
        job_data = {
            "payload": {
                "job_type": "ai_inference",
                "parameters": {
                    "model": "gpt-4",
                    "prompt": "Test prompt",
                    "max_tokens": 100
                }
            },
            "ttl_seconds": 900
        }

        response = await client.post(
            "http://localhost:8203/v1/jobs",
            json=job_data,
            headers={"X-Api-Key": "test-api-key"}
        )
        assert response.status_code == 201
        job = response.json()
        job_id = job["job_id"]

        # 2. Wait for job assignment
        await self._wait_for_job_state(client, job_id, "ASSIGNED", timeout=60)

        # 3. Wait for job completion
        await self._wait_for_job_state(client, job_id, "COMPLETED", timeout=300)

        # 4. Verify result
        response = await client.get(
            f"http://localhost:8203/v1/jobs/{job_id}",
            headers={"X-Api-Key": "test-api-key"}
        )
        assert response.status_code == 200
        job = response.json()
        assert job["state"] == "COMPLETED"
        assert "result" in job

        # 5. Verify payment
        response = await client.get(
            f"http://localhost:8203/v1/jobs/{job_id}/payment",
            headers={"X-Api-Key": "test-api-key"}
        )
        assert response.status_code == 200
        payment = response.json()
        assert payment["status"] == "completed"

    async def _wait_for_job_state(self, client, job_id, expected_state, timeout):
        """Wait for job to reach expected state"""
        start = datetime.now()
        while (datetime.now() - start).total_seconds() < timeout:
            response = await client.get(
                f"http://localhost:8203/v1/jobs/{job_id}",
                headers={"X-Api-Key": "test-api-key"}
            )
            job = response.json()
            if job["state"] == expected_state:
                return
            await asyncio.sleep(1)

        pytest.fail(f"Job did not reach state {expected_state} within {timeout}s")
```

## Test Execution

### Manual Execution

```bash
# Run all E2E tests
pytest tests/e2e/ -v --tb=short

# Run specific test suite
pytest tests/e2e/test_job_lifecycle.py -v

# Run with timeout
pytest tests/e2e/ --timeout=600 -v
```

### Automated Execution

**CI/CD Integration:**
- Run E2E tests nightly
- Run E2E tests on release candidates
- Run E2E tests after major changes

**GitHub Actions Example:**
```yaml
name: E2E Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio httpx
      - name: Start services
        run: docker-compose -f docker-compose.test.yml up -d
      - name: Wait for services
        run: ./scripts/wait-for-services.sh
      - name: Run E2E tests
        run: pytest tests/e2e/ -v --tb=short
      - name: Stop services
        if: always()
        run: docker-compose -f docker-compose.test.yml down
```

## Reporting

### Test Report Format

```markdown
# E2E Test Report

**Date:** [Date]
**Environment:** [Environment]
**Test Suite:** [Suite Name]

## Summary
- Total Tests: [Count]
- Passed: [Count]
- Failed: [Count]
- Skipped: [Count]
- Duration: [Time]

## Results by Scenario
| Scenario | Tests | Passed | Failed | Duration |
|----------|-------|--------|--------|----------|
| [Scenario 1] | [Count] | [Count] | [Count] | [Time] |
| [Scenario 2] | [Count] | [Count] | [Count] | [Time] |

## Failed Tests
### [Test Name]
- **Error:** [Error message]
- **Stack Trace:** [Trace]
- **Logs:** [Relevant logs]

## Recommendations
- [Recommendation 1]
- [Recommendation 2]
```

### Metrics to Track

- Test execution time
- Test success rate
- Test flakiness
- Resource utilization during tests
- Service restart count

## Maintenance

### Regular Updates

- **Weekly:** Review test failures and flakiness
- **Monthly:** Update test data and fixtures
- **Quarterly:** Review and update test scenarios
- **Annually:** Full test suite review and refactoring

### Test Maintenance Checklist

- [ ] Tests are up to date with API changes
- [ ] Test data is relevant and current
- [ ] Test environment matches production
- [ ] Test execution time is acceptable
- [ ] Test coverage is adequate
- [ ] Test documentation is current

## Success Criteria

### Before Production Deployment

- [ ] All critical E2E test scenarios implemented
- [ ] Test success rate >95%
- [ ] Test execution time <30 minutes
- [ ] Test environment matches production configuration
- [ ] Test data is comprehensive and current
- [ ] Tests integrated into CI/CD pipeline
- [ ] Test documentation is complete and current

### Ongoing

- [ ] Tests run at least daily
- [ ] Test failures are investigated and resolved
- [ ] Test suite is reviewed and updated quarterly
- [ ] Test metrics are tracked and reported

## Next Steps

### Immediate (1-2 weeks)
1. Set up E2E test environment
2. Implement service orchestration (docker-compose)
3. Create test fixtures
4. Implement critical test scenarios (job lifecycle, payment flow)

### Short-term (1 month)
1. Implement remaining test scenarios
2. Integrate tests into CI/CD
3. Set up test reporting
4. Document test procedures

### Long-term (3 months)
1. Optimize test execution time
2. Implement parallel test execution
3. Add UI testing (if applicable)
4. Implement test data management system

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Lead | | | |
| Engineering Lead | | | |
| DevOps Lead | | | |

## See Also

- [E2E Test Scenarios](e2e-test-scenarios.md) - Test scenarios and scope
- [E2E Test Environment](e2e-test-environment.md) - Environment setup and data management
