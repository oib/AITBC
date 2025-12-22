"""
Security validation framework for AITBC SDK certification
"""

import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import yaml


@dataclass
class SecurityIssue:
    """Security issue representation"""
    tool: str
    severity: str  # critical, high, medium, low
    type: str  # vulnerability, dependency, code_issue
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    cve_id: Optional[str] = None
    remediation: Optional[str] = None


@dataclass
class SecurityReport:
    """Security validation report"""
    sdk_path: str
    sdk_language: str
    timestamp: datetime
    issues: List[SecurityIssue]
    score: float
    certification_level: str
    blocked: bool


class SecurityValidator:
    """Main security validation orchestrator"""
    
    def __init__(self):
        self.tools = {
            "python": PythonSecurityValidator(),
            "java": JavaSecurityValidator(),
            "javascript": JavaScriptSecurityValidator(),
            "typescript": TypeScriptSecurityValidator()
        }
    
    def validate(self, sdk_path: str, certification_level: str = "bronze") -> SecurityReport:
        """Validate SDK security"""
        sdk_path = Path(sdk_path).resolve()
        
        # Detect language
        language = self._detect_language(sdk_path)
        if language not in self.tools:
            raise ValueError(f"Unsupported language: {language}")
        
        # Run validation
        validator = self.tools[language]
        issues = validator.validate(sdk_path, certification_level)
        
        # Calculate score and determine certification status
        score = self._calculate_score(issues, certification_level)
        blocked = self._should_block_certification(issues, certification_level)
        
        return SecurityReport(
            sdk_path=str(sdk_path),
            sdk_language=language,
            timestamp=datetime.utcnow(),
            issues=issues,
            score=score,
            certification_level=certification_level,
            blocked=blocked
        )
    
    def _detect_language(self, path: Path) -> str:
        """Detect SDK programming language"""
        # Check for language-specific files
        if (path / "setup.py").exists() or (path / "pyproject.toml").exists():
            return "python"
        elif (path / "pom.xml").exists() or (path / "build.gradle").exists():
            return "java"
        elif (path / "package.json").exists():
            # Check if it's TypeScript
            if any(path.rglob("*.ts")):
                return "typescript"
            return "javascript"
        
        raise ValueError("Could not detect SDK language")
    
    def _calculate_score(self, issues: List[SecurityIssue], level: str) -> float:
        """Calculate security score (0-100)"""
        weights = {
            "critical": 25,
            "high": 15,
            "medium": 5,
            "low": 1
        }
        
        total_deduction = 0
        for issue in issues:
            total_deduction += weights.get(issue.severity, 0)
        
        score = max(0, 100 - total_deduction)
        return score
    
    def _should_block_certification(self, issues: List[SecurityIssue], level: str) -> bool:
        """Determine if issues should block certification"""
        if level == "bronze":
            # Block for critical or high severity issues
            return any(i.severity in ["critical", "high"] for i in issues)
        elif level == "silver":
            # Block for critical issues
            return any(i.severity == "critical" for i in issues)
        elif level == "gold":
            # Block for any issues
            return len(issues) > 0
        
        return False
    
    def export_sarif(self, report: SecurityReport, output_path: str):
        """Export report in SARIF format"""
        sarif = {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "aitbc-security-validator",
                            "version": "1.0.0",
                            "informationUri": "https://aitbc.io/security"
                        }
                    },
                    "results": [
                        {
                            "ruleId": f"{issue.tool}-{issue.type}",
                            "level": self._map_severity_to_sarif(issue.severity),
                            "message": {
                                "text": issue.description
                            },
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {
                                            "uri": issue.file_path or ""
                                        },
                                        "region": {
                                            "startLine": issue.line_number or 1
                                        }
                                    }
                                }
                            ],
                            "properties": {
                                "cve": issue.cve_id,
                                "remediation": issue.remediation
                            }
                        }
                        for issue in report.issues
                    ]
                }
            ]
        }
        
        with open(output_path, 'w') as f:
            json.dump(sarif, f, indent=2)
    
    def _map_severity_to_sarif(self, severity: str) -> str:
        """Map severity to SARIF level"""
        mapping = {
            "critical": "error",
            "high": "error",
            "medium": "warning",
            "low": "note"
        }
        return mapping.get(severity, "warning")


class PythonSecurityValidator:
    """Python-specific security validation"""
    
    def validate(self, path: Path, level: str) -> List[SecurityIssue]:
        """Run Python security checks"""
        issues = []
        
        # Dependency scanning with safety
        issues.extend(self._scan_dependencies(path))
        
        # Code analysis with bandit
        if level in ["silver", "gold"]:
            issues.extend(self._analyze_code(path))
        
        # Check for secrets
        if level == "gold":
            issues.extend(self._scan_secrets(path))
        
        return issues
    
    def _scan_dependencies(self, path: Path) -> List[SecurityIssue]:
        """Scan Python dependencies for vulnerabilities"""
        issues = []
        
        # Find requirements files
        req_files = list(path.rglob("requirements*.txt")) + list(path.rglob("pyproject.toml"))
        
        for req_file in req_files:
            try:
                # Run safety check
                result = subprocess.run(
                    ["safety", "check", "--json", "--file", str(req_file)],
                    capture_output=True,
                    text=True,
                    cwd=path
                )
                
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    
                    for vuln in data:
                        issues.append(SecurityIssue(
                            tool="safety",
                            severity=self._map_safety_severity(vuln.get("advisory", "")),
                            type="dependency",
                            description=vuln.get("advisory", ""),
                            cve_id=vuln.get("cve"),
                            remediation=f"Update {vuln.get('package')} to {vuln.get('analyzed_version')}"
                        ))
            except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
                # Safety not installed or failed
                pass
        
        return issues
    
    def _analyze_code(self, path: Path) -> List[SecurityIssue]:
        """Analyze Python code for security issues"""
        issues = []
        
        try:
            # Run bandit
            result = subprocess.run(
                ["bandit", "-r", str(path), "-f", "json"],
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                data = json.loads(result.stdout)
                
                for issue in data.get("results", []):
                    issues.append(SecurityIssue(
                        tool="bandit",
                        severity=issue.get("issue_severity", "medium").lower(),
                        type="code_issue",
                        description=issue.get("issue_text", ""),
                        file_path=issue.get("filename"),
                        line_number=issue.get("line_number"),
                        remediation=issue.get("issue_cwe", {}).get("link")
                    ))
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            # Bandit not installed or failed
            pass
        
        return issues
    
    def _scan_secrets(self, path: Path) -> List[SecurityIssue]:
        """Scan for hardcoded secrets"""
        issues = []
        
        try:
            # Run truffleHog
            result = subprocess.run(
                ["trufflehog", "--json", str(path)],
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        finding = json.loads(line)
                        issues.append(SecurityIssue(
                            tool="trufflehog",
                            severity="high",
                            type="code_issue",
                            description="Hardcoded secret detected",
                            file_path=finding.get("path"),
                            line_number=finding.get("line"),
                            remediation="Remove hardcoded secret and use environment variables"
                        ))
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            # TruffleHog not installed or failed
            pass
        
        return issues
    
    def _map_safety_severity(self, advisory: str) -> str:
        """Map safety advisory to severity"""
        advisory_lower = advisory.lower()
        if any(word in advisory_lower for word in ["critical", "remote code execution"]):
            return "critical"
        elif any(word in advisory_lower for word in ["high", "execution", "bypass"]):
            return "high"
        elif any(word in advisory_lower for word in ["medium"]):
            return "medium"
        else:
            return "low"


class JavaSecurityValidator:
    """Java-specific security validation"""
    
    def validate(self, path: Path, level: str) -> List[SecurityIssue]:
        """Run Java security checks"""
        issues = []
        
        # Dependency scanning with OWASP Dependency Check
        issues.extend(self._scan_dependencies(path))
        
        # Code analysis with SpotBugs
        if level in ["silver", "gold"]:
            issues.extend(self._analyze_code(path))
        
        return issues
    
    def _scan_dependencies(self, path: Path) -> List[SecurityIssue]:
        """Scan Java dependencies for vulnerabilities"""
        issues = []
        
        # Look for pom.xml or build.gradle
        pom_file = path / "pom.xml"
        gradle_file = path / "build.gradle"
        
        if pom_file.exists():
            # Run Maven dependency check
            try:
                result = subprocess.run(
                    ["mvn", "org.owasp:dependency-check-maven:check"],
                    capture_output=True,
                    text=True,
                    cwd=path
                )
                
                # Parse XML report
                report_path = path / "target" / "dependency-check-report.xml"
                if report_path.exists():
                    issues.extend(self._parse_dependency_check_report(report_path))
            except subprocess.CalledProcessError:
                pass
        
        elif gradle_file.exists():
            # Run Gradle dependency check
            try:
                result = subprocess.run(
                    ["./gradlew", "dependencyCheckAnalyze"],
                    capture_output=True,
                    text=True,
                    cwd=path
                )
                
                # Parse XML report
                report_path = path / "build" / "reports" / "dependency-check-report.xml"
                if report_path.exists():
                    issues.extend(self._parse_dependency_check_report(report_path))
            except subprocess.CalledProcessError:
                pass
        
        return issues
    
    def _parse_dependency_check_report(self, report_path: Path) -> List[SecurityIssue]:
        """Parse OWASP Dependency Check XML report"""
        import xml.etree.ElementTree as ET
        
        issues = []
        try:
            tree = ET.parse(report_path)
            root = tree.getroot()
            
            for vulnerability in root.findall(".//vulnerability"):
                name = vulnerability.get("name")
                severity = vulnerability.get("severity")
                cve = vulnerability.get("cve")
                
                # Map severity
                if severity.upper() in ["CRITICAL", "HIGH"]:
                    mapped_severity = "high"
                elif severity.upper() == "MEDIUM":
                    mapped_severity = "medium"
                else:
                    mapped_severity = "low"
                
                issues.append(SecurityIssue(
                    tool="dependency-check",
                    severity=mapped_severity,
                    type="dependency",
                    description=f"Vulnerability in {name}",
                    cve_id=cve,
                    remediation="Update dependency to patched version"
                ))
        except ET.ParseError:
            pass
        
        return issues
    
    def _analyze_code(self, path: Path) -> List[SecurityIssue]:
        """Analyze Java code with SpotBugs"""
        issues = []
        
        try:
            # Run SpotBugs
            result = subprocess.run(
                ["spotbugs", "-textui", "-xml:withMessages", "-low", str(path)],
                capture_output=True,
                text=True
            )
            
            # Parse SpotBugs XML report
            report_path = path / "spotbugsXml.xml"
            if report_path.exists():
                issues.extend(self._parse_spotbugs_report(report_path))
        except subprocess.CalledProcessError:
            pass
        
        return issues
    
    def _parse_spotbugs_report(self, report_path: Path) -> List[SecurityIssue]:
        """Parse SpotBugs XML report"""
        import xml.etree.ElementTree as ET
        
        issues = []
        try:
            tree = ET.parse(report_path)
            root = tree.getroot()
            
            for instance in root.findall(".//BugInstance"):
                bug_type = instance.get("type")
                priority = instance.get("priority")
                
                # Map priority to severity
                if priority == "1":
                    severity = "high"
                elif priority == "2":
                    severity = "medium"
                else:
                    severity = "low"
                
                source_line = instance.find(".//SourceLine")
                if source_line is not None:
                    issues.append(SecurityIssue(
                        tool="spotbugs",
                        severity=severity,
                        type="code_issue",
                        description=bug_type,
                        file_path=source_line.get("sourcepath"),
                        line_number=int(source_line.get("start", 0)),
                        remediation=f"Fix {bug_type} security issue"
                    ))
        except ET.ParseError:
            pass
        
        return issues


class JavaScriptSecurityValidator:
    """JavaScript-specific security validation"""
    
    def validate(self, path: Path, level: str) -> List[SecurityIssue]:
        """Run JavaScript security checks"""
        issues = []
        
        # Dependency scanning with npm audit
        issues.extend(self._scan_dependencies(path))
        
        # Code analysis with ESLint security rules
        if level in ["silver", "gold"]:
            issues.extend(self._analyze_code(path))
        
        return issues
    
    def _scan_dependencies(self, path: Path) -> List[SecurityIssue]:
        """Scan npm dependencies for vulnerabilities"""
        issues = []
        
        package_json = path / "package.json"
        if not package_json.exists():
            return issues
        
        try:
            # Run npm audit
            result = subprocess.run(
                ["npm", "audit", "--json"],
                capture_output=True,
                text=True,
                cwd=path
            )
            
            if result.stdout:
                data = json.loads(result.stdout)
                
                for advisory_id, advisory in data.get("vulnerabilities", {}).items():
                    severity = advisory.get("severity", "low")
                    
                    issues.append(SecurityIssue(
                        tool="npm-audit",
                        severity=severity,
                        type="dependency",
                        description=advisory.get("title", ""),
                        cve_id=advisory.get("cwe"),
                        remediation=f"Run npm audit fix"
                    ))
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            pass
        
        return issues
    
    def _analyze_code(self, path: Path) -> List[SecurityIssue]:
        """Analyze JavaScript code with ESLint"""
        issues = []
        
        try:
            # Run ESLint with security plugin
            result = subprocess.run(
                ["npx", "eslint", "--format", "json", str(path)],
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                data = json.loads(result.stdout)
                
                for file_result in data:
                    for message in file_result.get("messages", []):
                        if "security" in message.get("ruleId", "").lower():
                            issues.append(SecurityIssue(
                                tool="eslint",
                                severity="medium",
                                type="code_issue",
                                description=message.get("message"),
                                file_path=file_result.get("filePath"),
                                line_number=message.get("line"),
                                remediation=f"Fix {message.get('ruleId')} issue"
                            ))
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            pass
        
        return issues


class TypeScriptSecurityValidator(JavaScriptSecurityValidator):
    """TypeScript-specific security validation (inherits from JavaScript)"""
    
    def validate(self, path: Path, level: str) -> List[SecurityIssue]:
        """Run TypeScript security checks"""
        # Run JavaScript checks first
        issues = super().validate(path, level)
        
        # Additional TypeScript-specific checks
        if level == "gold":
            issues.extend(self._check_typescript_config(path))
        
        return issues
    
    def _check_typescript_config(self, path: Path) -> List[SecurityIssue]:
        """Check TypeScript configuration for security"""
        issues = []
        
        tsconfig = path / "tsconfig.json"
        if tsconfig.exists():
            try:
                with open(tsconfig) as f:
                    config = json.load(f)
                
                compiler_options = config.get("compilerOptions", {})
                
                # Check for implicit any
                if compiler_options.get("noImplicitAny") is not True:
                    issues.append(SecurityIssue(
                        tool="typescript-config",
                        severity="low",
                        type="code_issue",
                        description="TypeScript should disable implicit any",
                        file_path=str(tsconfig),
                        remediation="Set noImplicitAny to true"
                    ))
                
                # Check for strict mode
                if compiler_options.get("strict") is not True:
                    issues.append(SecurityIssue(
                        tool="typescript-config",
                        severity="low",
                        type="code_issue",
                        description="TypeScript should use strict mode",
                        file_path=str(tsconfig),
                        remediation="Set strict to true"
                    ))
            except json.JSONDecodeError:
                pass
        
        return issues


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="AITBC SDK Security Validator")
    parser.add_argument("sdk_path", help="Path to SDK directory")
    parser.add_argument("--level", choices=["bronze", "silver", "gold"], default="bronze")
    parser.add_argument("--output", help="Output SARIF report path")
    parser.add_argument("--format", choices=["json", "sarif"], default="json")
    
    args = parser.parse_args()
    
    # Run validation
    validator = SecurityValidator()
    report = validator.validate(args.sdk_path, args.level)
    
    # Output results
    if args.format == "sarif" and args.output:
        validator.export_sarif(report, args.output)
    else:
        print(json.dumps(asdict(report), indent=2, default=str))
    
    # Exit with error if blocked
    if report.blocked:
        print(f"\nCERTIFICATION BLOCKED: Security issues found")
        for issue in report.issues:
            if issue.severity in ["critical", "high"]:
                print(f"  - {issue.description} ({issue.severity})")
        exit(1)
    else:
        print(f"\nSECURITY CHECK PASSED: Score {report.score}/100")


if __name__ == "__main__":
    main()
