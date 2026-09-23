# Security Policy

## Reporting a Vulnerability

AITBC is developed privately on Gitea with a public GitHub mirror. To report a
security vulnerability:

- **GitHub**: use [private vulnerability reporting](https://github.com/oib/AITBC/security)
  (Security → Report a vulnerability), or open a draft security advisory.
- **Email**: `aitbc@bubuit.net` — the operator's direct contact.
- Please do not file public issues for unpatched vulnerabilities.

There is no public bug bounty program and no separate security team mailbox;
reports go directly to the maintainer.

## Dependency Security Management

### Tools

Security tooling is installed via `requirements-dev.txt` and run locally or in
CI:

1. **pip-audit** — scans Python packages for known vulnerabilities
2. **Safety** — checks against the Python Safety DB
3. **Bandit** — static analysis for Python security issues
4. **CodeQL** — configuration lives under `.github/codeql/` (`suppressions.yml`)

### Running a scan

```bash
# Scan Python dependencies (pip-audit + safety)
./scripts/security/dependency-scan.sh

# Scan source for hardcoded secrets
./venv/bin/python scripts/security/scan_secrets.py

# Full local audit
./venv/bin/python scripts/security/security_audit.py
```

### CI/CD

- `.github/workflows/ci.yml` and `.gitea/workflows/ci.yml` run the test suites,
  docs validation, port/bind-policy checks, and Foundry contract tests on every
  push and PR to `main`. There is currently no separate scheduled
  dependency-security workflow — scans are run manually with the scripts above.

### Dependency updates

- **Dependabot** (`.github/dependabot.yml`) opens weekly update PRs for pip,
  npm, and GitHub Actions dependencies (Mondays 09:00, limit 5).
- Manual updates:
  1. Run `./scripts/security/dependency-scan.sh`
  2. `pip install --upgrade <package>`; refresh `requirements.txt`
  3. Re-run the scan and the test suite
  4. Commit as `deps: update <package> to <version>`

### Security response process

When vulnerabilities are detected:

1. **Critical (CVSS ≥ 9.0)**: create a private advisory, patch within 24 hours,
   deploy hotfix if needed.
2. **High (CVSS 7.0–8.9)**: patch within 72 hours, schedule maintenance window.
3. **Medium/Low (CVSS < 7.0)**: include in the next scheduled update; document
   the risk assessment.

### Security best practices

#### Development
1. **Never commit secrets** to the repository
2. **Use environment variables** for sensitive data
3. **Run security scans** before committing
4. **Keep dependencies updated**
5. **Review dependency licenses** for compliance

#### Dependencies
1. **Pin versions** in `requirements.txt`
2. **Use virtual environments** for isolation
3. **Audit new dependencies** before adding
4. **Minimize attack surface** by removing unused dependencies
5. **Use `requirements-dev.txt`** for development-only dependencies

#### Code review
1. Security review for code touching sensitive data
2. Input validation on all user inputs
3. Error handling that does not expose sensitive information
4. Authentication/authorization checks on all endpoints
5. Logging without logging sensitive data

### Local development security

#### Pre-commit hook
Add to `.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Run security scan before commit
./scripts/security/dependency-scan.sh
```

#### IDE configuration
Enable warnings for:
- Hardcoded secrets
- SQL injection risks
- XSS vulnerabilities
- Insecure deserialization

### Resources

- [Python Safety Database](https://pyup.io/safety/)
- [pip-audit Documentation](https://pip-audit.readthedocs.io/)
- [OWASP Python Security](https://owasp.org/www-project-python-security/)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)

---

**Last Updated**: 2026-09-19
