# Plugin Security

## Status
✅ Operational

## Overview
Security plugin for scanning, validating, and monitoring AITBC plugins for security vulnerabilities and compliance.

## Architecture

### Core Components
- **Vulnerability Scanner**: Scans plugins for security vulnerabilities
- **Code Analyzer**: Analyzes plugin code for security issues
- **Dependency Checker**: Checks plugin dependencies for vulnerabilities
- **Compliance Validator**: Validates plugin compliance with security standards
- **Policy Engine**: Enforces security policies

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Access to plugin files
- Vulnerability database access

### Installation
```bash
cd /opt/aitbc/apps/plugin-security
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
VULN_DB_URL=https://vuln-db.example.com
SCAN_DEPTH=full
COMPLIANCE_STANDARDS=OWASP,SANS
POLICY_FILE=/path/to/policies.yaml
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure vulnerability database
5. Configure security policies
6. Run tests: `pytest tests/`

### Project Structure
```
plugin-security/
├── src/
│   ├── vulnerability_scanner/ # Vulnerability scanning
│   ├── code_analyzer/        # Code analysis
│   ├── dependency_checker/   # Dependency checking
│   ├── compliance_validator/ # Compliance validation
│   └── policy_engine/       # Policy enforcement
├── policies/                # Security policies
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run vulnerability scanner tests
pytest tests/test_scanner.py

# Run compliance validator tests
pytest tests/test_compliance.py
```

## API Reference

### Vulnerability Scanning

#### Scan Plugin
```http
POST /api/v1/security/scan
Content-Type: application/json

{
  "plugin_id": "string",
  "version": "1.0.0",
  "scan_depth": "quick|full",
  "scan_types": ["code", "dependencies", "configuration"]
}
```

#### Get Scan Results
```http
GET /api/v1/security/scan/{scan_id}
```

#### Get Scan History
```http
GET /api/v1/security/scan/history?plugin_id=string
```

### Code Analysis

#### Analyze Code
```http
POST /api/v1/security/analyze
Content-Type: application/json

{
  "plugin_id": "string",
  "code_path": "/path/to/code",
  "analysis_types": ["sast", "secrets", "quality"]
}
```

#### Get Analysis Report
```http
GET /api/v1/security/analyze/{analysis_id}
```

### Dependency Checking

#### Check Dependencies
```http
POST /api/v1/security/dependencies/check
Content-Type: application/json

{
  "plugin_id": "string",
  "dependencies": [{"name": "string", "version": "string"}]
}
```

#### Get Vulnerability Report
```http
GET /api/v1/security/dependencies/vulnerabilities?plugin_id=string
```

### Compliance Validation

#### Validate Compliance
```http
POST /api/v1/security/compliance/validate
Content-Type: application/json

{
  "plugin_id": "string",
  "standards": ["OWASP", "SANS"],
  "severity": "high|medium|low"
}
```

#### Get Compliance Report
```http
GET /api/v1/security/compliance/report/{validation_id}
```

### Policy Enforcement

#### Check Policy Compliance
```http
POST /api/v1/security/policies/check
Content-Type: application/json

{
  "plugin_id": "string",
  "policy_name": "string"
}
```

#### List Policies
```http
GET /api/v1/security/policies
```

## Configuration

### Environment Variables
- `VULN_DB_URL`: Vulnerability database URL
- `SCAN_DEPTH`: Default scan depth (quick/full)
- `COMPLIANCE_STANDARDS`: Compliance standards to enforce
- `POLICY_FILE`: Path to security policies file

### Scan Types
- **SAST**: Static Application Security Testing
- **Secrets Detection**: Detect hardcoded secrets
- **Dependency Scanning**: Scan dependencies for vulnerabilities
- **Configuration Analysis**: Analyze configuration files

### Compliance Standards
- **OWASP**: OWASP security standards
- **SANS**: SANS security controls
- **CIS**: CIS benchmarks

## Troubleshooting

**Scan not running**: Check vulnerability database connectivity and plugin accessibility.

**False positives**: Review scan rules and adjust severity thresholds.

**Compliance validation failed**: Review plugin code against compliance standards.

**Policy check failed**: Verify policy configuration and plugin compliance.

## Security Notes

- Regularly update vulnerability database
- Use isolated environment for scanning
- Implement rate limiting for scan requests
- Secure scan results storage
- Regularly audit security policies
- Monitor for security incidents
