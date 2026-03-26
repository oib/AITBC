# Security Scanning Configuration

## Overview

This document outlines the security scanning configuration for the AITBC project, including Dependabot setup, Bandit security scanning, and comprehensive CI/CD security workflows.

## 🔒 Security Scanning Components

### 1. Dependabot Configuration

**File**: `.github/dependabot.yml`

**Features**:
- **Python Dependencies**: Weekly updates with conservative approach
- **GitHub Actions**: Weekly updates for CI/CD dependencies
- **Docker Dependencies**: Weekly updates for container dependencies
- **npm Dependencies**: Weekly updates for frontend components
- **Conservative Updates**: Patch and minor updates allowed, major updates require review

**Schedule**:
- **Frequency**: Weekly on Mondays at 09:00 UTC
- **Reviewers**: @oib
- **Assignees**: @oib
- **Labels**: dependencies, [ecosystem], [language]

**Conservative Approach**:
- Allow patch updates for all dependencies
- Allow minor updates for most dependencies
- Require manual review for major updates of critical dependencies
- Critical dependencies: fastapi, uvicorn, sqlalchemy, alembic, httpx, click, pytest, cryptography

### 2. Bandit Security Scanning

**File**: `bandit.toml`

**Configuration**:
- **Severity Level**: Medium and above
- **Confidence Level**: Medium and above
- **Excluded Directories**: tests, test_*, __pycache__, .venv, build, dist
- **Skipped Tests**: Comprehensive list of skipped test rules for development efficiency
- **Output Format**: JSON and human-readable reports
- **Parallel Processing**: 4 processes for faster scanning

**Scanned Directories**:
- `apps/coordinator-api/src`
- `cli/aitbc_cli`
- `packages/py/aitbc-core/src`
- `packages/py/aitbc-crypto/src`
- `packages/py/aitbc-sdk/src`
- `tests`

### 3. CodeQL Security Analysis

**Features**:
- **Languages**: Python, JavaScript
- **Queries**: security-extended, security-and-quality
- **SARIF Output**: Results uploaded to GitHub Security tab
- **Auto-build**: Automatic code analysis setup

### 4. Dependency Security Scanning

**Python Dependencies**:
- **Tool**: Safety
- **Check**: Known vulnerabilities in Python packages
- **Output**: JSON and human-readable reports

**npm Dependencies**:
- **Tool**: npm audit
- **Check**: Known vulnerabilities in npm packages
- **Coverage**: explorer-web and website packages

### 5. Container Security Scanning

**Tool**: Trivy
- **Trigger**: When Docker files are modified
- **Output**: SARIF format for GitHub Security tab
- **Scope**: Container vulnerability scanning

### 6. OSSF Scorecard

**Purpose**: Open Source Security Foundation security scorecard
- **Metrics**: Security best practices compliance
- **Output**: SARIF format for GitHub Security tab
- **Frequency**: On every push and PR

## 🚀 CI/CD Integration

### Security Scanning Workflow

**File**: `.github/workflows/security-scanning.yml`

**Triggers**:
- **Push**: main, develop branches
- **Pull Requests**: main, develop branches
- **Schedule**: Daily at 2 AM UTC

**Jobs**:

1. **Bandit Security Scan**
   - Matrix strategy for multiple directories
   - Parallel execution for faster results
   - JSON and text report generation
   - Artifact upload for 30 days
   - PR comments with findings

2. **CodeQL Security Analysis**
   - Multi-language support (Python, JavaScript)
   - Extended security queries
   - SARIF upload to GitHub Security tab

3. **Dependency Security Scan**
   - Python dependency scanning with Safety
   - npm dependency scanning with audit
   - JSON report generation
   - Artifact upload

4. **Container Security Scan**
   - Trivy vulnerability scanner
   - Conditional execution on Docker changes
   - SARIF output for GitHub Security tab

5. **OSSF Scorecard**
   - Security best practices assessment
   - SARIF output for GitHub Security tab
   - Regular security scoring

6. **Security Summary Report**
   - Comprehensive security scan summary
   - PR comments with security overview
   - Recommendations for security improvements
   - Artifact upload for 90 days

## 📊 Security Reporting

### Report Types

1. **Bandit Reports**
   - **JSON**: Machine-readable format
   - **Text**: Human-readable format
   - **Coverage**: All Python source directories
   - **Retention**: 30 days

2. **Safety Reports**
   - **JSON**: Known vulnerabilities
   - **Text**: Human-readable summary
   - **Coverage**: Python dependencies
   - **Retention**: 30 days

3. **CodeQL Reports**
   - **SARIF**: GitHub Security tab integration
   - **Coverage**: Python and JavaScript
   - **Retention**: GitHub Security tab

4. **Dependency Reports**
   - **JSON**: npm audit results
   - **Coverage**: Frontend dependencies
   - **Retention**: 30 days

5. **Security Summary**
   - **Markdown**: Comprehensive summary
   - **PR Comments**: Direct feedback
   - **Retention**: 90 days

### Security Metrics

- **Scan Frequency**: Daily automated scans
- **Coverage**: All source code and dependencies
- **Severity Threshold**: Medium and above
- **Confidence Level**: Medium and above
- **False Positive Rate**: Minimized through configuration

## 🔧 Configuration Files

### bandit.toml
```toml
[bandit]
exclude_dirs = ["tests", "test_*", "__pycache__", ".venv"]
severity_level = "medium"
confidence_level = "medium"
output_format = "json"
number_of_processes = 4
```

### .github/dependabot.yml
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
```

### .github/workflows/security-scanning.yml
```yaml
name: Security Scanning
on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
  schedule:
    - cron: '0 2 * * *'
```

## 🛡️ Security Best Practices

### Code Security
- **Input Validation**: Validate all user inputs
- **SQL Injection**: Use parameterized queries
- **XSS Prevention**: Escape user-generated content
- **Authentication**: Secure password handling
- **Authorization**: Proper access controls

### Dependency Security
- **Regular Updates**: Keep dependencies up-to-date
- **Vulnerability Scanning**: Regular security scans
- **Known Vulnerabilities**: Address immediately
- **Supply Chain Security**: Verify package integrity

### Infrastructure Security
- **Container Security**: Regular container scanning
- **Network Security**: Proper firewall rules
- **Access Control**: Least privilege principle
- **Monitoring**: Security event monitoring

## 📋 Security Checklist

### Development Phase
- [ ] Code review for security issues
- [ ] Static analysis with Bandit
- [ ] Dependency vulnerability scanning
- [ ] Security testing

### Deployment Phase
- [ ] Container security scanning
- [ ] Infrastructure security review
- [ ] Access control verification
- [ ] Monitoring setup

### Maintenance Phase
- [ ] Regular security scans
- [ ] Dependency updates
- [ ] Security patch application
- [ ] Security audit review

## 🚨 Incident Response

### Security Incident Process
1. **Detection**: Automated security scan alerts
2. **Assessment**: Security team evaluation
3. **Response**: Immediate patch deployment
4. **Communication**: Stakeholder notification
5. **Post-mortem**: Incident analysis and improvement

### Escalation Levels
- **Low**: Informational findings
- **Medium**: Security best practice violations
- **High**: Security vulnerabilities
- **Critical**: Active security threats

## 📈 Security Metrics Dashboard

### Key Metrics
- **Vulnerability Count**: Number of security findings
- **Severity Distribution**: Breakdown by severity level
- **Remediation Time**: Time to fix vulnerabilities
- **Scan Coverage**: Percentage of code scanned
- **False Positive Rate**: Accuracy of security tools

### Reporting Frequency
- **Daily**: Automated scan results
- **Weekly**: Security summary reports
- **Monthly**: Security metrics dashboard
- **Quarterly**: Security audit reports

## 🔮 Future Enhancements

### Planned Improvements
- **Dynamic Application Security Testing (DAST)**
- **Interactive Application Security Testing (IAST)**
- **Software Composition Analysis (SCA)**
- **Security Information and Event Management (SIEM)**
- **Threat Modeling Integration**

### Tool Integration
- **SonarQube**: Code quality and security
- **Snyk**: Dependency vulnerability scanning
- **OWASP ZAP**: Web application security
- **Falco**: Runtime security monitoring
- **Aqua**: Container security platform

## 📞 Security Contacts

### Security Team
- **Security Lead**: security@aitbc.dev
- **Development Team**: dev@aitbc.dev
- **Operations Team**: ops@aitbc.dev

### External Resources
- **GitHub Security Advisory**: https://github.com/advisories
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **CISA Vulnerabilities**: https://www.cisa.gov/known-exploited-vulnerabilities-catalog

---

**Last Updated**: March 3, 2026
**Next Review**: March 10, 2026
**Security Team**: AITBC Security Team
