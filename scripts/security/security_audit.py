#!/usr/bin/env python3
"""
AITBC Production Security Audit Script
Comprehensive security assessment for production deployment
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
import hashlib
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SecurityAudit:
    """Comprehensive security audit for AITBC production"""
    
    def __init__(self, project_root: str = "/opt/aitbc"):
        self.project_root = Path(project_root)
        self.results = {
            "timestamp": datetime.utcnow().isoformat(),
            "audit_version": "v0.2.0",
            "findings": [],
            "score": 0,
            "max_score": 100,
            "critical_issues": [],
            "warnings": [],
            "recommendations": []
        }
        
    def run_full_audit(self) -> Dict[str, Any]:
        """Run comprehensive security audit"""
        logger.info("Starting AITBC Production Security Audit...")
        
        # Security categories
        categories = [
            ("File Permissions", self.check_file_permissions, 15),
            ("Secret Management", self.check_secret_management, 20),
            ("Code Security", self.check_code_security, 15),
            ("Dependencies", self.check_dependencies, 10),
            ("Network Security", self.check_network_security, 10),
            ("Access Control", self.check_access_control, 10),
            ("Data Protection", self.check_data_protection, 10),
            ("Infrastructure", self.check_infrastructure_security, 10)
        ]
        
        total_score = 0
        total_weight = 0
        
        for category_name, check_function, weight in categories:
            logger.info(f"Checking {category_name}...")
            try:
                category_score, issues = check_function()
                total_score += category_score * weight
                total_weight += weight
                
                self.results["findings"].append({
                    "category": category_name,
                    "score": category_score,
                    "weight": weight,
                    "issues": issues
                })
                
                # Categorize issues
                for issue in issues:
                    if issue["severity"] == "critical":
                        self.results["critical_issues"].append(issue)
                    elif issue["severity"] == "warning":
                        self.results["warnings"].append(issue)
                        
            except Exception as e:
                logger.error(f"Error in {category_name} check: {e}")
                self.results["findings"].append({
                    "category": category_name,
                    "score": 0,
                    "weight": weight,
                    "issues": [{"type": "check_error", "message": str(e), "severity": "critical"}]
                })
                total_weight += weight
        
        # Calculate final score
        self.results["score"] = (total_score / total_weight) * 100 if total_weight > 0 else 0
        
        # Generate recommendations
        self.generate_recommendations()
        
        logger.info(f"Audit completed. Final score: {self.results['score']:.1f}/100")
        return self.results
        
    def check_file_permissions(self) -> Tuple[float, List[Dict]]:
        """Check file permissions and access controls"""
        issues = []
        score = 15.0
        
        # Check sensitive file permissions
        sensitive_files = [
            ("*.key", 600),  # Private keys
            ("*.pem", 600),  # Certificates
            ("config/*.env", 600),  # Environment files
            ("keystore/*", 600),  # Keystore files
            ("*.sh", 755),  # Shell scripts
        ]
        
        for pattern, expected_perm in sensitive_files:
            try:
                files = list(self.project_root.glob(pattern))
                for file_path in files:
                    if file_path.is_file():
                        current_perm = oct(file_path.stat().st_mode)[-3:]
                        if current_perm != str(expected_perm):
                            issues.append({
                                "type": "file_permission",
                                "file": str(file_path.relative_to(self.project_root)),
                                "current": current_perm,
                                "expected": str(expected_perm),
                                "severity": "warning" if current_perm > "644" else "critical"
                            })
                            score -= 1
            except Exception as e:
                logger.warning(f"Could not check {pattern}: {e}")
        
        # Check for world-writable files
        try:
            result = subprocess.run(
                ["find", str(self.project_root), "-perm", "-o+w", "!", "-type", "l"],
                capture_output=True, text=True, timeout=30
            )
            if result.stdout.strip():
                writable_files = result.stdout.strip().split('\n')
                issues.append({
                    "type": "world_writable_files",
                    "count": len(writable_files),
                    "files": writable_files[:5],  # Limit output
                    "severity": "critical"
                })
                score -= min(5, len(writable_files))
        except Exception as e:
            logger.warning(f"Could not check world-writable files: {e}")
        
        return max(0, score), issues
        
    def check_secret_management(self) -> Tuple[float, List[Dict]]:
        """Check secret management and key storage"""
        issues = []
        score = 20.0
        
        # Check for hardcoded secrets
        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "hardcoded_password"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "hardcoded_api_key"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "hardcoded_secret"),
            (r'token\s*=\s*["\'][^"\']+["\']', "hardcoded_token"),
            (r'private_key\s*=\s*["\'][^"\']+["\']', "hardcoded_private_key"),
            (r'0x[a-fA-F0-9]{40}', "ethereum_address"),
            (r'sk-[a-zA-Z0-9]{48}', "openai_api_key"),
        ]
        
        code_files = list(self.project_root.glob("**/*.py")) + list(self.project_root.glob("**/*.js"))
        
        for file_path in code_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                for pattern, issue_type in secret_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        issues.append({
                            "type": issue_type,
                            "file": str(file_path.relative_to(self.project_root)),
                            "count": len(matches),
                            "severity": "critical"
                        })
                        score -= 2
            except Exception as e:
                continue
        
        # Check for .env files in git
        try:
            result = subprocess.run(
                ["git", "ls-files", " | grep -E '\.env$|\.key$|\.pem$'"],
                shell=True, cwd=self.project_root, capture_output=True, text=True
            )
            if result.stdout.strip():
                issues.append({
                    "type": "secrets_in_git",
                    "files": result.stdout.strip().split('\n'),
                    "severity": "critical"
                })
                score -= 5
        except Exception as e:
            logger.warning(f"Could not check git for secrets: {e}")
        
        # Check keystore encryption
        keystore_dir = self.project_root / "keystore"
        if keystore_dir.exists():
            keystore_files = list(keystore_dir.glob("*"))
            for keystore_file in keystore_files:
                if keystore_file.is_file():
                    try:
                        with open(keystore_file, 'rb') as f:
                            content = f.read()
                            # Check if file is encrypted (not plain text)
                            try:
                                content.decode('utf-8')
                                if "private_key" in content.decode('utf-8').lower():
                                    issues.append({
                                        "type": "unencrypted_keystore",
                                        "file": str(keystore_file.relative_to(self.project_root)),
                                        "severity": "critical"
                                    })
                                    score -= 3
                            except UnicodeDecodeError:
                                # File is binary/encrypted, which is good
                                pass
                    except Exception as e:
                        continue
        
        return max(0, score), issues
        
    def check_code_security(self) -> Tuple[float, List[Dict]]:
        """Check code security vulnerabilities"""
        issues = []
        score = 15.0
        
        # Check for dangerous imports
        dangerous_imports = [
            "pickle",  # Insecure deserialization
            "eval",    # Code execution
            "exec",    # Code execution
            "subprocess.call",  # Command injection
            "os.system",        # Command injection
        ]
        
        python_files = list(self.project_root.glob("**/*.py"))
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                for dangerous in dangerous_imports:
                    if dangerous in content:
                        issues.append({
                            "type": "dangerous_import",
                            "file": str(file_path.relative_to(self.project_root)),
                            "import": dangerous,
                            "severity": "warning"
                        })
                        score -= 0.5
            except Exception as e:
                continue
        
        # Check for SQL injection patterns
        sql_patterns = [
            r'execute\s*\(\s*["\'][^"\']*\+',
            r'format.*SELECT.*\+',
            r'%s.*SELECT.*\+',
        ]
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                for pattern in sql_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        issues.append({
                            "type": "sql_injection_risk",
                            "file": str(file_path.relative_to(self.project_root)),
                            "severity": "warning"
                        })
                        score -= 1
            except Exception as e:
                continue
        
        # Check for input validation
        input_validation_files = [
            "apps/coordinator-api/src/app/services/secure_pickle.py",
            "apps/coordinator-api/src/app/middleware/security.py"
        ]
        
        for validation_file in input_validation_files:
            file_path = self.project_root / validation_file
            if file_path.exists():
                # Positive check - security measures in place
                score += 1
        
        return max(0, min(15, score)), issues
        
    def check_dependencies(self) -> Tuple[float, List[Dict]]:
        """Check dependency security"""
        issues = []
        score = 10.0
        
        # Check pyproject.toml for known vulnerable packages
        pyproject_file = self.project_root / "pyproject.toml"
        if pyproject_file.exists():
            try:
                with open(pyproject_file, 'r') as f:
                    content = f.read()
                    
                # Check for outdated packages (simplified)
                vulnerable_packages = {
                    "requests": "<2.25.0",
                    "urllib3": "<1.26.0",
                    "cryptography": "<3.4.0",
                    "pyyaml": "<5.4.0"
                }
                
                for package, version in vulnerable_packages.items():
                    if package in content:
                        issues.append({
                            "type": "potentially_vulnerable_dependency",
                            "package": package,
                            "recommended_version": version,
                            "severity": "warning"
                        })
                        score -= 1
            except Exception as e:
                logger.warning(f"Could not analyze dependencies: {e}")
        
        # Check for poetry.lock or requirements.txt
        lock_files = ["poetry.lock", "requirements.txt"]
        has_lock_file = any((self.project_root / f).exists() for f in lock_files)
        
        if not has_lock_file:
            issues.append({
                "type": "no_dependency_lock_file",
                "severity": "warning"
            })
            score -= 2
        
        return max(0, score), issues
        
    def check_network_security(self) -> Tuple[float, List[Dict]]:
        """Check network security configurations"""
        issues = []
        score = 10.0
        
        # Check for hardcoded URLs and endpoints
        network_files = list(self.project_root.glob("**/*.py")) + list(self.project_root.glob("**/*.js"))
        
        hardcoded_urls = []
        for file_path in network_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Look for hardcoded URLs
                url_patterns = [
                    r'http://localhost:\d+',
                    r'http://127\.0\.0\.1:\d+',
                    r'https?://[^/\s]+:\d+',
                ]
                
                for pattern in url_patterns:
                    matches = re.findall(pattern, content)
                    hardcoded_urls.extend(matches)
            except Exception as e:
                continue
        
        if hardcoded_urls:
            issues.append({
                "type": "hardcoded_network_endpoints",
                "count": len(hardcoded_urls),
                "examples": hardcoded_urls[:3],
                "severity": "warning"
            })
            score -= min(3, len(hardcoded_urls))
        
        # Check for SSL/TLS usage
        ssl_config_files = [
            "apps/coordinator-api/src/app/config.py",
            "apps/blockchain-node/src/aitbc_chain/config.py"
        ]
        
        ssl_enabled = False
        for config_file in ssl_config_files:
            file_path = self.project_root / config_file
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        if "ssl" in content.lower() or "tls" in content.lower():
                            ssl_enabled = True
                            break
                except Exception as e:
                    continue
        
        if not ssl_enabled:
            issues.append({
                "type": "no_ssl_configuration",
                "severity": "warning"
            })
            score -= 2
        
        return max(0, score), issues
        
    def check_access_control(self) -> Tuple[float, List[Dict]]:
        """Check access control mechanisms"""
        issues = []
        score = 10.0
        
        # Check for authentication mechanisms
        auth_files = [
            "apps/coordinator-api/src/app/auth/",
            "apps/coordinator-api/src/app/middleware/auth.py"
        ]
        
        has_auth = any((self.project_root / f).exists() for f in auth_files)
        if not has_auth:
            issues.append({
                "type": "no_authentication_mechanism",
                "severity": "critical"
            })
            score -= 5
        
        # Check for role-based access control
        rbac_patterns = ["role", "permission", "authorization"]
        rbac_found = False
        
        python_files = list(self.project_root.glob("**/*.py"))
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if any(pattern in content.lower() for pattern in rbac_patterns):
                        rbac_found = True
                        break
            except Exception as e:
                continue
        
        if not rbac_found:
            issues.append({
                "type": "no_role_based_access_control",
                "severity": "warning"
            })
            score -= 2
        
        return max(0, score), issues
        
    def check_data_protection(self) -> Tuple[float, List[Dict]]:
        """Check data protection measures"""
        issues = []
        score = 10.0
        
        # Check for encryption usage
        encryption_patterns = ["encrypt", "decrypt", "cipher", "hash"]
        encryption_found = False
        
        python_files = list(self.project_root.glob("**/*.py"))
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if any(pattern in content.lower() for pattern in encryption_patterns):
                        encryption_found = True
                        break
            except Exception as e:
                continue
        
        if not encryption_found:
            issues.append({
                "type": "no_encryption_mechanism",
                "severity": "warning"
            })
            score -= 3
        
        # Check for data validation
        validation_patterns = ["validate", "sanitize", "clean"]
        validation_found = False
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if any(pattern in content.lower() for pattern in validation_patterns):
                        validation_found = True
                        break
            except Exception as e:
                continue
        
        if not validation_found:
            issues.append({
                "type": "no_data_validation",
                "severity": "warning"
            })
            score -= 2
        
        return max(0, score), issues
        
    def check_infrastructure_security(self) -> Tuple[float, List[Dict]]:
        """Check infrastructure security"""
        issues = []
        score = 10.0
        
        # Check for systemd service files
        service_files = list(self.project_root.glob("**/*.service"))
        if service_files:
            for service_file in service_files:
                try:
                    with open(service_file, 'r') as f:
                        content = f.read()
                        
                    # Check for running as root
                    if "User=root" in content or "User=root" not in content:
                        issues.append({
                            "type": "service_running_as_root",
                            "file": str(service_file.relative_to(self.project_root)),
                            "severity": "warning"
                        })
                        score -= 1
                        
                except Exception as e:
                    continue
        
        # Check for Docker usage (should be none per policy)
        docker_files = list(self.project_root.glob("**/Dockerfile*")) + list(self.project_root.glob("**/docker-compose*"))
        if docker_files:
            issues.append({
                "type": "docker_usage_detected",
                "files": [str(f.relative_to(self.project_root)) for f in docker_files],
                "severity": "warning"
            })
            score -= 2
        
        # Check for firewall configuration
        firewall_configs = list(self.project_root.glob("**/firewall*")) + list(self.project_root.glob("**/ufw*"))
        if not firewall_configs:
            issues.append({
                "type": "no_firewall_configuration",
                "severity": "warning"
            })
            score -= 1
        
        return max(0, score), issues
        
    def generate_recommendations(self):
        """Generate security recommendations based on findings"""
        recommendations = []
        
        # Critical issues recommendations
        critical_types = set(issue["type"] for issue in self.results["critical_issues"])
        
        if "hardcoded_password" in critical_types:
            recommendations.append({
                "priority": "critical",
                "action": "Remove all hardcoded passwords and use environment variables or secret management",
                "files": [issue["file"] for issue in self.results["critical_issues"] if issue["type"] == "hardcoded_password"]
            })
        
        if "secrets_in_git" in critical_types:
            recommendations.append({
                "priority": "critical",
                "action": "Remove secrets from git history and configure .gitignore properly",
                "details": "Use git filter-branch to remove sensitive data from history"
            })
        
        if "unencrypted_keystore" in critical_types:
            recommendations.append({
                "priority": "critical",
                "action": "Encrypt all keystore files using AES-GCM encryption",
                "implementation": "Use the existing keystore.py encryption mechanisms"
            })
        
        if "world_writable_files" in critical_types:
            recommendations.append({
                "priority": "critical",
                "action": "Fix world-writable file permissions immediately",
                "command": "find /opt/aitbc -type f -perm /o+w -exec chmod 644 {} \\;"
            })
        
        # Warning level recommendations
        warning_types = set(issue["type"] for issue in self.results["warnings"])
        
        if "dangerous_import" in warning_types:
            recommendations.append({
                "priority": "high",
                "action": "Replace dangerous imports with secure alternatives",
                "details": "Use json instead of pickle, subprocess.run with shell=False"
            })
        
        if "no_ssl_configuration" in warning_types:
            recommendations.append({
                "priority": "high",
                "action": "Implement SSL/TLS configuration for all network services",
                "implementation": "Configure SSL certificates and HTTPS endpoints"
            })
        
        if "no_authentication_mechanism" in critical_types:
            recommendations.append({
                "priority": "critical",
                "action": "Implement proper authentication and authorization",
                "implementation": "Add JWT-based authentication with role-based access control"
            })
        
        # General recommendations
        if self.results["score"] < 70:
            recommendations.append({
                "priority": "medium",
                "action": "Conduct regular security audits and implement security testing in CI/CD",
                "implementation": "Add automated security scanning to GitHub Actions"
            })
        
        self.results["recommendations"] = recommendations
        
    def save_report(self, output_file: str):
        """Save audit report to file"""
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Security audit report saved to: {output_file}")

def main():
    """Main function to run security audit"""
    audit = SecurityAudit()
    
    # Run full audit
    results = audit.run_full_audit()
    
    # Save report
    report_file = "/opt/aitbc/security_audit_report.json"
    audit.save_report(report_file)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"AITBC PRODUCTION SECURITY AUDIT REPORT")
    print(f"{'='*60}")
    print(f"Overall Score: {results['score']:.1f}/100")
    print(f"Critical Issues: {len(results['critical_issues'])}")
    print(f"Warnings: {len(results['warnings'])}")
    print(f"Recommendations: {len(results['recommendations'])}")
    
    if results['critical_issues']:
        print(f"\n🚨 CRITICAL ISSUES:")
        for issue in results['critical_issues'][:5]:
            print(f"  - {issue['type']}: {issue.get('message', 'N/A')}")
    
    if results['recommendations']:
        print(f"\n💡 TOP RECOMMENDATIONS:")
        for rec in results['recommendations'][:3]:
            print(f"  - [{rec['priority'].upper()}] {rec['action']}")
    
    print(f"\n📄 Full report: {report_file}")
    
    # Exit with appropriate code
    if results['score'] < 50:
        sys.exit(2)  # Critical security issues
    elif results['score'] < 70:
        sys.exit(1)  # Security concerns
    else:
        sys.exit(0)  # Acceptable security posture

if __name__ == "__main__":
    main()
