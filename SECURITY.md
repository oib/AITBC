# Security Policy

## Supported Versions

Use this section to tell people about which versions of your project are
currently being supported with security updates.

| Version | Supported          | Release Date | Security Support |
| ------- | ------------------ | ------------ | ---------------- |
| 2.0.x   | :white_check_mark: | 2026-03-04   | Current production version |
| 1.5.x   | :white_check_mark: | 2026-02-15   | Legacy support (limited) |
| 1.0.x   | :x:                | 2025-12-01   | End of life |
| < 1.0   | :x:                | Historical   | No support |

## Security Policy Overview

The AITBC (AI Trading Blockchain Compute) platform takes security seriously. This document outlines our security practices and how to responsibly report vulnerabilities.

### Security Scope

The following components are within scope for security vulnerability reports:

- **Core Services**: Coordinator API, Exchange API, Blockchain Node, RPC services
- **Smart Contracts**: All on-chain contracts and token implementations
- **Infrastructure**: Authentication, authorization, and data protection mechanisms
- **Dependencies**: Third-party libraries and packages used in production
- **Configuration**: Environment variables, secrets management, and deployment scripts

### Out of Scope

The following are typically out of scope unless they directly impact the security of our production systems:

- **Development Tools**: Scripts, utilities, and development-only code
- **Documentation**: Informational content and documentation files
- **Test Networks**: Test deployments and staging environments
- **Third-party Services**: External services not directly controlled by AITBC

## Reporting a Vulnerability

### How to Report

**Primary Method**: Send an email to our security team
- **Email**: security@aitbc.dev
- **PGP Key**: Available upon request for encrypted communications

**Alternative Method**: Use GitHub's private vulnerability reporting
- Visit: https://github.com/oib/AITBC/security/advisories/new
- Select "Report a vulnerability privately"

### What to Include

Please include the following information in your report:

1. **Vulnerability Type**: Brief description of the vulnerability class
2. **Affected Components**: Which parts of the system are affected
3. **Impact Assessment**: Potential impact if exploited
4. **Reproduction Steps**: Detailed steps to reproduce the issue
5. **Proof of Concept**: Code, screenshots, or other evidence
6. **Environment Details**: Version, configuration, and environment information

### Response Timeline

- **Initial Response**: Within 24 hours (acknowledgment)
- **Initial Assessment**: Within 3 business days
- **Detailed Analysis**: Within 7 business days
- **Remediation Timeline**: Based on severity (see below)
- **Public Disclosure**: After fix is deployed and coordinated disclosure

### Severity Classification

| Severity | Description | Response Time | Disclosure Timeline |
| -------- | ----------- | ------------- | ------------------- |
| **Critical** | Remote code execution, data breach, financial loss | 24 hours | 7 days after fix |
| **High** | Privilege escalation, significant data exposure | 72 hours | 14 days after fix |
| **Medium** | Limited data exposure, service disruption | 7 days | 30 days after fix |
| **Low** | Information disclosure, minor issues | 14 days | 90 days after fix |

## Security Practices

### Development Security

- **Code Review**: All code changes undergo security review
- **Static Analysis**: Automated security scanning tools
- **Dependency Scanning**: Regular vulnerability scanning of dependencies
- **Penetration Testing**: Regular security assessments
- **Security Training**: Team members receive regular security training

### Infrastructure Security

- **Encryption**: All data in transit and at rest is encrypted
- **Access Control**: Principle of least privilege enforced
- **Audit Logging**: Comprehensive logging and monitoring
- **Network Security**: Firewalls, intrusion detection, and prevention
- **Regular Updates**: Security patches applied promptly

### Smart Contract Security

- **Audits**: All smart contracts undergo professional security audits
- **Formal Verification**: Critical contracts verified mathematically
- **Bug Bounties**: Responsible disclosure program for vulnerabilities
- **Testing**: Comprehensive test suite including security tests
- **Upgradability**: Secure upgrade mechanisms implemented

## Coordinated Disclosure

### Disclosure Process

1. **Report Received**: Security team acknowledges receipt
2. **Validation**: Vulnerability is validated and assessed
3. **Remediation**: Fix is developed and tested
4. **Deployment**: Fix is deployed to production
5. **Disclosure**: Public disclosure with credit to reporter

### Credit and Recognition

- **Public Credit**: Reporter acknowledged in security advisories
- **Bug Bounty**: Financial rewards for qualifying vulnerabilities
- **Hall of Fame**: Recognition in our security acknowledgments
- **Swag**: AITBC merchandise for significant contributions

### Communication

- **Status Updates**: Regular updates on remediation progress
- **Technical Details**: Clear explanation of vulnerability and fix
- **Mitigation Advice**: Guidance for users to protect themselves
- **Coordination**: Coordination with other affected parties if needed

## Security Best Practices for Users

### For Node Operators

- **Regular Updates**: Keep software updated to latest versions
- **Secure Configuration**: Follow security configuration guidelines
- **Access Control**: Limit access to authorized personnel only
- **Monitoring**: Monitor for suspicious activity
- **Backups**: Regular, encrypted backups of critical data

### For Developers

- **Secure Coding**: Follow secure coding practices
- **Input Validation**: Validate all user inputs
- **Error Handling**: Proper error handling without information leakage
- **Authentication**: Use strong authentication mechanisms
- **Dependencies**: Keep dependencies updated and vetted

### For Users

- **Strong Passwords**: Use unique, strong passwords
- **Two-Factor Authentication**: Enable 2FA where available
- **Phishing Awareness**: Be cautious of suspicious communications
- **Software Updates**: Keep client software updated
- **Private Keys**: Never share private keys or sensitive data

## Security Contacts

### Security Team

- **Email**: security@aitbc.dev
- **PGP**: Available upon request
- **Response Time**: 24 hours for critical issues

### General Inquiries

- **Email**: info@aitbc.dev
- **Website**: https://aitbc.dev
- **Documentation**: https://docs.aitbc.dev

### Bug Bounty Program

- **Platform**: Private program (contact security team)
- **Rewards**: Based on severity and impact
- **Guidelines**: Available upon request

## Legal Information

### Safe Harbor

This security policy is intended to give security researchers clear guidelines for conducting vulnerability research and reporting. We commit to not take legal action against researchers who:

1. Follow this vulnerability disclosure policy
2. Only perform testing on systems they have authorized access to
3. Do not exfiltrate, modify, or destroy data
4. Do not disrupt service for other users
5. Report findings promptly and responsibly

### Disclaimer

This security policy may be updated from time to time. The latest version will always be available at https://github.com/oib/AITBC/blob/main/SECURITY.md

### License

This security policy is provided under the same license as the AITBC project.

## Security Advisories

Past security advisories and vulnerability disclosures are available at:
- https://github.com/oib/AITBC/security/advisories
- https://docs.aitbc.dev/security/advisories

## Acknowledgments

We thank all security researchers who contribute to the security of the AITBC platform through responsible vulnerability disclosure.

---

**Last Updated**: 2026-03-04  
**Version**: 1.0  
**Contact**: security@aitbc.dev  
**Project**: AITBC (AI Trading Blockchain Compute)
