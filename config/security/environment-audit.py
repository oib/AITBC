#!/usr/bin/env python3
"""
Environment Configuration Security Auditor
Validates environment files against security rules
"""

import os
import re
import yaml
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any


class EnvironmentAuditor:
    """Audits environment configurations for security issues"""
    
    def __init__(self, config_dir: Path = None):
        self.config_dir = config_dir or Path(__file__).parent.parent
        self.validation_rules = self._load_validation_rules()
        self.issues: List[Dict[str, Any]] = []
    
    def _load_validation_rules(self) -> Dict[str, Any]:
        """Load secret validation rules"""
        rules_file = self.config_dir / "security" / "secret-validation.yaml"
        if rules_file.exists():
            with open(rules_file) as f:
                return yaml.safe_load(f)
        return {}
    
    def audit_environment_file(self, env_file: Path) -> List[Dict[str, Any]]:
        """Audit a single environment file"""
        issues = []
        
        if not env_file.exists():
            return [{"file": str(env_file), "level": "ERROR", "message": "File does not exist"}]
        
        with open(env_file) as f:
            content = f.read()
        
        # Check for forbidden patterns
        forbidden_patterns = self.validation_rules.get("forbidden_patterns", [])
        production_forbidden_patterns = self.validation_rules.get("production_forbidden_patterns", [])
        
        # Always check general forbidden patterns
        for pattern in forbidden_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append({
                    "file": str(env_file),
                    "level": "CRITICAL",
                    "message": f"Forbidden pattern detected: {pattern}",
                    "line": self._find_pattern_line(content, pattern)
                })
        
        # Check production-specific forbidden patterns
        if "production" in str(env_file):
            for pattern in production_forbidden_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    issues.append({
                        "file": str(env_file),
                        "level": "CRITICAL",
                        "message": f"Production forbidden pattern: {pattern}",
                        "line": self._find_pattern_line(content, pattern)
                    })
        
        # Check for template secrets
        template_patterns = [
            r"your-.*-key-here",
            r"change-this-.*",
            r"your-.*-password"
        ]
        
        for pattern in template_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append({
                    "file": str(env_file),
                    "level": "HIGH",
                    "message": f"Template secret found: {pattern}",
                    "line": self._find_pattern_line(content, pattern)
                })
        
        # Check for localhost in production files
        if "production" in str(env_file):
            localhost_patterns = [r"localhost", r"127\.0\.0\.1", r"sqlite://"]
            for pattern in localhost_patterns:
                if re.search(pattern, content):
                    issues.append({
                        "file": str(env_file),
                        "level": "HIGH",
                        "message": f"Localhost reference in production: {pattern}",
                        "line": self._find_pattern_line(content, pattern)
                    })
        
        # Validate secret references
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Check if value should be a secret reference
                if self._should_be_secret(key) and not value.startswith('secretRef:'):
                    issues.append({
                        "file": str(env_file),
                        "level": "MEDIUM",
                        "message": f"Potential secret not using secretRef: {key}",
                        "line": i
                    })
        
        return issues
    
    def _should_be_secret(self, key: str) -> bool:
        """Check if a key should be a secret reference"""
        secret_keywords = [
            'key', 'secret', 'password', 'token', 'credential',
            'api_key', 'encryption_key', 'hmac_secret', 'jwt_secret',
            'dsn', 'database_url'
        ]
        
        return any(keyword in key.lower() for keyword in secret_keywords)
    
    def _find_pattern_line(self, content: str, pattern: str) -> int:
        """Find line number where pattern appears"""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                return i
        return 0
    
    def audit_all_environments(self) -> Dict[str, List[Dict[str, Any]]]:
        """Audit all environment files"""
        results = {}
        
        # Check environments directory
        env_dir = self.config_dir / "environments"
        if env_dir.exists():
            for env_file in env_dir.rglob("*.env*"):
                if env_file.is_file():
                    issues = self.audit_environment_file(env_file)
                    if issues:
                        results[str(env_file)] = issues
        
        # Check root directory .env files
        root_dir = self.config_dir.parent
        for pattern in [".env.example", ".env*"]:
            for env_file in root_dir.glob(pattern):
                if env_file.is_file() and env_file.name != ".env":
                    issues = self.audit_environment_file(env_file)
                    if issues:
                        results[str(env_file)] = issues
        
        return results
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive security report"""
        results = self.audit_all_environments()
        
        # Count issues by severity
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        total_issues = 0
        
        for file_issues in results.values():
            for issue in file_issues:
                severity = issue["level"]
                severity_counts[severity] += 1
                total_issues += 1
        
        return {
            "summary": {
                "total_issues": total_issues,
                "files_audited": len(results),
                "severity_breakdown": severity_counts
            },
            "issues": results,
            "recommendations": self._generate_recommendations(severity_counts)
        }
    
    def _generate_recommendations(self, severity_counts: Dict[str, int]) -> List[str]:
        """Generate security recommendations based on findings"""
        recommendations = []
        
        if severity_counts["CRITICAL"] > 0:
            recommendations.append("CRITICAL: Fix forbidden patterns immediately")
        
        if severity_counts["HIGH"] > 0:
            recommendations.append("HIGH: Remove template secrets and localhost references")
        
        if severity_counts["MEDIUM"] > 0:
            recommendations.append("MEDIUM: Use secretRef for all sensitive values")
        
        if severity_counts["LOW"] > 0:
            recommendations.append("LOW: Review and improve configuration structure")
        
        if not any(severity_counts.values()):
            recommendations.append("✅ No security issues found")
        
        return recommendations


def main():
    """Main audit function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Audit environment configurations")
    parser.add_argument("--config-dir", help="Configuration directory path")
    parser.add_argument("--output", help="Output report to file")
    parser.add_argument("--format", choices=["json", "yaml", "text"], default="json", help="Report format")
    
    args = parser.parse_args()
    
    auditor = EnvironmentAuditor(Path(args.config_dir) if args.config_dir else None)
    report = auditor.generate_report()
    
    # Output report
    if args.format == "json":
        import json
        output = json.dumps(report, indent=2)
    elif args.format == "yaml":
        output = yaml.dump(report, default_flow_style=False)
    else:
        output = format_text_report(report)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Report saved to {args.output}")
    else:
        print(output)
    
    # Exit with error code if issues found
    if report["summary"]["total_issues"] > 0:
        sys.exit(1)


def format_text_report(report: Dict[str, Any]) -> str:
    """Format report as readable text"""
    lines = []
    lines.append("=" * 60)
    lines.append("ENVIRONMENT SECURITY AUDIT REPORT")
    lines.append("=" * 60)
    lines.append("")
    
    # Summary
    summary = report["summary"]
    lines.append(f"Files Audited: {summary['files_audited']}")
    lines.append(f"Total Issues: {summary['total_issues']}")
    lines.append("")
    
    # Severity breakdown
    lines.append("Severity Breakdown:")
    for severity, count in summary["severity_breakdown"].items():
        if count > 0:
            lines.append(f"  {severity}: {count}")
    lines.append("")
    
    # Issues by file
    if report["issues"]:
        lines.append("ISSUES FOUND:")
        lines.append("-" * 40)
        
        for file_path, file_issues in report["issues"].items():
            lines.append(f"\n📁 {file_path}")
            for issue in file_issues:
                lines.append(f"  {issue['level']}: {issue['message']}")
                if issue.get('line'):
                    lines.append(f"    Line: {issue['line']}")
    
    # Recommendations
    lines.append("\nRECOMMENDATIONS:")
    lines.append("-" * 40)
    for rec in report["recommendations"]:
        lines.append(f"• {rec}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    main()
