# AITBC SDK Conformance Test Suite

Language-agnostic test suite for validating AITBC SDK implementations against the official API specification.

## Architecture

The test suite uses black-box HTTP API testing to validate SDK compliance:
- **Mock AITBC Server**: Validates requests against OpenAPI spec
- **Test Runners**: Docker containers for each language
- **Test Fixtures**: JSON/YAML test cases
- **Reporting**: Detailed compliance reports

## Quick Start

```bash
# Run Bronze certification tests
docker-compose run python-sdk bronze

# Run Silver certification tests
docker-compose run python-sdk silver

# Run all tests
docker-compose run python-sdk all
```

## Test Structure

```
test-suite/
├── fixtures/           # Test cases (JSON/YAML)
├── runners/           # Language-specific test runners
├── mock-server/       # OpenAPI mock server
├── reports/           # Test results
└── docker-compose.yml
```

## Certification Levels

### Bronze Tests
- API compliance
- Authentication
- Error handling
- Data model validation

### Silver Tests
- Performance benchmarks
- Rate limiting
- Retry logic
- Async support

### Gold Tests
- Enterprise features
- Scalability
- Security compliance
- SLA validation
