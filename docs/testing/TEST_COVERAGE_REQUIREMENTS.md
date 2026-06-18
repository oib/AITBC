# AITBC Microservices Test Coverage Requirements

This document outlines the test coverage requirements for the AITBC microservices architecture.

## Overview

Each microservice should maintain adequate test coverage to ensure reliability and facilitate future development. Test coverage should be measured and tracked as part of the CI/CD pipeline.

## Test Coverage Targets

### Minimum Requirements

- **Unit Tests**: 70% line coverage minimum
- **Integration Tests**: 50% line coverage minimum
- **Overall Coverage**: 60% line coverage minimum per service

### Ideal Targets

- **Unit Tests**: 80% line coverage
- **Integration Tests**: 70% line coverage
- **Overall Coverage**: 75% line coverage per service

## Service-Specific Requirements

### GPU Service

**Unit Test Coverage Requirements:**
- Domain models (GPUArchitecture, GPURegistry, ConsumerGPUProfile, EdgeGPUMetrics, GPUBooking, GPUReview): 80%
- Service layer (EdgeGPUService): 75%
- API endpoints: 70%

**Integration Test Coverage Requirements:**
- Database operations: 70%
- API endpoint integration: 60%
- Service dependencies: 50%

**Critical Path Tests:**
- Consumer GPU profile listing
- Edge GPU metrics creation
- GPU discovery (async)
- Inference optimization (async)

### Marketplace Service

**Unit Test Coverage Requirements:**
- Domain models (MarketplaceOffer, MarketplaceBid, GlobalMarketplaceOffer, GlobalMarketplaceTransaction, etc.): 75%
- Service layer (MarketplaceService): 70%
- API endpoints: 65%

**Integration Test Coverage Requirements:**
- Database operations: 70%
- API endpoint integration: 60%
- Service dependencies: 50%

**Critical Path Tests:**
- Offer creation and retrieval
- Bid creation and retrieval
- Marketplace analytics

### Trading Service

**Unit Test Coverage Requirements:**
- Domain models (TradeRequest, TradeMatch, TradeNegotiation, TradeAgreement, TradeSettlement, TradeFeedback, TradingAnalytics): 75%
- Service layer (TradingService): 70%
- API endpoints: 65%

**Integration Test Coverage Requirements:**
- Database operations: 70%
- API endpoint integration: 60%
- Service dependencies: 50%

**Critical Path Tests:**
- Trade request creation
- Trade matching logic
- Agreement creation
- Settlement processing

### Governance Service

**Unit Test Coverage Requirements:**
- Domain models (GovernanceProfile, Proposal, Vote, DaoTreasury, TransparencyReport): 75%
- Service layer (GovernanceService): 70%
- API endpoints: 65%

**Integration Test Coverage Requirements:**
- Database operations: 70%
- API endpoint integration: 60%
- Service dependencies: 50%

**Critical Path Tests:**
- Proposal creation
- Vote casting
- Proposal execution
- Treasury management

### API Gateway

**Unit Test Coverage Requirements:**
- Routing logic: 80%
- Service registry: 75%
- Proxy functionality: 70%

**Integration Test Coverage Requirements:**
- Gateway to service routing: 70%
- Load balancing: 50%
- Error handling: 60%

**Critical Path Tests:**
- Health check routing
- Service registry updates
- Request proxying to each service
- Unknown route handling

## Test Types

### Unit Tests

**Purpose**: Test individual functions and methods in isolation.

**Requirements**:
- Mock external dependencies (database, external APIs)
- Test edge cases and error conditions
- Test validation logic
- Test business logic

**Example Coverage Areas**:
- Domain model validation
- Service method logic
- Utility functions
- Helper methods

### Integration Tests

**Purpose**: Test interactions between components.

**Requirements**:
- Use test databases
- Test database operations
- Test API endpoint integration
- Test service-to-service communication

**Example Coverage Areas**:
- Database CRUD operations
- API request/response handling
- Service dependency resolution
- Transaction management

### End-to-End Tests

**Purpose**: Test complete workflows across services.

**Requirements**:
- Test critical user journeys
- Test gateway routing
- Test service orchestration
- Test error propagation

**Example Coverage Areas**:
- Complete trade flow (request → match → negotiate → agree → settle)
- Complete proposal flow (create → vote → execute)
- Gateway routing to all services

## Test Execution

### Running Tests

**Run all tests for a service:**
```bash
cd apps/<service-name>
pytest tests/
```

**Run with coverage:**
```bash
pytest tests/ --cov=src --cov-report=html --cov-report=term
```

**Run specific test file:**
```bash
pytest tests/test_main.py
```

**Run specific test:**
```bash
pytest tests/test_main.py::test_health_check
```

### CI/CD Integration

Tests should run automatically in CI/CD pipeline:

1. **On Pull Request**: Run all tests with coverage reporting
2. **On Merge to Main**: Run all tests with coverage reporting and enforce minimum coverage
3. **Nightly**: Run full test suite including end-to-end tests

### Coverage Enforcement

Minimum coverage thresholds should be enforced in CI:

```ini
[tool.coverage.run]
source = "src"

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]

[tool.coverage.fail_under]
minimum = 60
```

## Coverage Reporting

### Coverage Reports

Coverage reports should be generated in multiple formats:

- **HTML**: For detailed analysis (coverage/html/index.html)
- **Terminal**: For quick summary
- **XML**: For CI/CD integration

### Coverage Tracking

Coverage should be tracked over time to identify trends:

- Track coverage by service
- Track coverage by module
- Track coverage by test type
- Identify declining coverage

## Best Practices

### Test Organization

- Organize tests by module/functionality
- Use descriptive test names
- Keep tests independent
- Use fixtures for common setup

### Test Data

- Use factories for test data creation
- Use in-memory databases for unit tests
- Use test database for integration tests
- Clean up test data after each test

### Mocking

- Mock external dependencies
- Use pytest-mock for mocking
- Mock database calls in unit tests
- Use real database in integration tests

### Async Testing

- Use pytest-asyncio for async tests
- Mark async tests with @pytest.mark.asyncio
- Test async service methods
- Test async database operations

## Coverage Exclusions

The following can be excluded from coverage calculations:

- Type checking blocks (`if TYPE_CHECKING:`)
- Abstract methods
- Representation methods (`__repr__`)
- Test files themselves
- Configuration files
- Migration scripts

## Next Steps

1. Add coverage reporting to CI/CD pipeline
2. Set up coverage tracking dashboard
3. Review coverage reports regularly
4. Increase coverage targets as codebase matures
5. Add end-to-end tests for critical workflows
