#!/usr/bin/env python3
"""
Helm Values Security Auditor
Validates Helm values files for proper secret references
"""

import os
import re
import yaml
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any


class HelmValuesAuditor:
    """Audits Helm values files for security issues"""
    
    def __init__(self, helm_dir: Path = None):
        self.helm_dir = helm_dir or Path(__file__).parent.parent.parent / "infra" / "helm"
        self.issues: List[Dict[str, Any]] = []
    
    def audit_helm_values_file(self, values_file: Path) -> List[Dict[str, Any]]:
        """Audit a single Helm values file"""
        issues = []
        
        if not values_file.exists():
            return [{"file": str(values_file), "level": "ERROR", "message": "File does not exist"}]
        
        with open(values_file) as f:
            try:
                values = yaml.safe_load(f)
            except yaml.YAMLError as e:
                return [{"file": str(values_file), "level": "ERROR", "message": f"YAML parsing error: {e}"}]
        
        # Recursively check for potential secrets
        self._check_secrets_recursive(values, "", values_file, issues)
        
        return issues
    
    def _check_secrets_recursive(self, obj: Any, path: str, file_path: Path, issues: List[Dict[str, Any]]):
        """Recursively check object for potential secrets"""
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                
                if isinstance(value, str):
                    # Check for potential secrets that should use secretRef
                    if self._is_potential_secret(key, value):
                        if not value.startswith('secretRef:'):
                            issues.append({
                                "file": str(file_path),
                                "level": "HIGH",
                                "message": f"Potential secret not using secretRef: {current_path}",
                                "value": value,
                                "suggestion": f"Use secretRef:secret-name:key"
                            })
                
                # Recursively check nested objects
                self._check_secrets_recursive(value, current_path, file_path, issues)
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                current_path = f"{path}[{i}]" if path else f"[{i}]"
                self._check_secrets_recursive(item, current_path, file_path, issues)
    
    def _is_potential_secret(self, key: str, value: str) -> bool:
        """Check if a key-value pair represents a potential secret"""
        
        # Skip Kubernetes built-in values
        kubernetes_builtins = [
            'topology.kubernetes.io/zone',
            'topology.kubernetes.io/region',
            'kubernetes.io/hostname',
            'app.kubernetes.io/name'
        ]
        
        if value in kubernetes_builtins:
            return False
        
        # Skip common non-secret values
        non_secret_values = [
            'warn', 'info', 'debug', 'error',
            'admin', 'user', 'postgres',
            'http://prometheus-server:9090',
            'http://127.0.0.1:5001/',
            'stable', 'latest', 'IfNotPresent',
            'db-credentials', 'redis-credentials',
            'aitbc', 'coordinator', 'postgresql'
        ]
        
        if value in non_secret_values:
            return False
        
        # Skip Helm chart specific configurations
        helm_config_keys = [
            'existingSecret', 'existingSecretPassword',
            'serviceAccountName', 'serviceAccount.create',
            'ingress.enabled', 'networkPolicy.enabled',
            'podSecurityPolicy.enabled', 'autoscaling.enabled'
        ]
        
        if key in helm_config_keys:
            return False
        
        # Check key patterns for actual secrets
        secret_key_patterns = [
            r'.*password$', r'.*secret$', r'.*token$',
            r'.*credential$', r'.*dsn$',
            r'database_url', r'api_key', r'encryption_key', r'hmac_secret',
            r'jwt_secret', r'private_key', r'adminPassword'
        ]
        
        key_lower = key.lower()
        value_lower = value.lower()
        
        # Check if key suggests it's a secret
        for pattern in secret_key_patterns:
            if re.match(pattern, key_lower):
                return True
        
        # Check if value looks like a secret (more strict)
        secret_value_patterns = [
            r'^postgresql://.*:.*@',  # PostgreSQL URLs with credentials
            r'^mysql://.*:.*@',  # MySQL URLs with credentials
            r'^mongodb://.*:.*@',  # MongoDB URLs with credentials
            r'^sk-[a-zA-Z0-9]{48}',  # Stripe keys
            r'^ghp_[a-zA-Z0-9]{36}',  # GitHub personal access tokens
            r'^xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]{24}',  # Slack bot tokens
            r'^[a-fA-F0-9]{64}$',  # 256-bit hex keys
            r'^[a-zA-Z0-9+/]{40,}={0,2}$',  # Base64 encoded secrets
        ]
        
        for pattern in secret_value_patterns:
            if re.match(pattern, value):
                return True
        
        # Check for actual secrets in value (more strict)
        if len(value) > 20 and any(indicator in value_lower for indicator in ['password', 'secret', 'key', 'token']):
            return True
        
        return False
    
    def audit_all_helm_values(self) -> Dict[str, List[Dict[str, Any]]]:
        """Audit all Helm values files"""
        results = {}
        
        # Find all values.yaml files
        for values_file in self.helm_dir.rglob("values*.yaml"):
            if values_file.is_file():
                issues = self.audit_helm_values_file(values_file)
                if issues:
                    results[str(values_file)] = issues
        
        return results
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive security report"""
        results = self.audit_all_helm_values()
        
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
            recommendations.append("CRITICAL: Fix critical secret exposure immediately")
        
        if severity_counts["HIGH"] > 0:
            recommendations.append("HIGH: Use secretRef for all sensitive values")
        
        if severity_counts["MEDIUM"] > 0:
            recommendations.append("MEDIUM: Review and validate secret references")
        
        if severity_counts["LOW"] > 0:
            recommendations.append("LOW: Improve secret management practices")
        
        if not any(severity_counts.values()):
            recommendations.append("✅ No security issues found")
        
        return recommendations


def main():
    """Main audit function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Audit Helm values for security issues")
    parser.add_argument("--helm-dir", help="Helm directory path")
    parser.add_argument("--output", help="Output report to file")
    parser.add_argument("--format", choices=["json", "yaml", "text"], default="json", help="Report format")
    
    args = parser.parse_args()
    
    auditor = HelmValuesAuditor(Path(args.helm_dir) if args.helm_dir else None)
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
    lines.append("HELM VALUES SECURITY AUDIT REPORT")
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
                if 'value' in issue:
                    lines.append(f"    Current value: {issue['value']}")
                if 'suggestion' in issue:
                    lines.append(f"    Suggestion: {issue['suggestion']}")
    
    # Recommendations
    lines.append("\nRECOMMENDATIONS:")
    lines.append("-" * 40)
    for rec in report["recommendations"]:
        lines.append(f"• {rec}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    main()
