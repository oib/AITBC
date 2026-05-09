"""
Dependency vulnerability scanning utilities for AITBC
Provides automated vulnerability scanning for Python dependencies
"""

import subprocess
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from .aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class VulnerabilityReport:
    """Vulnerability scan report"""
    package: str
    version: str
    vulnerability_id: str
    severity: str
    description: str
    fix_available: bool
    fixed_version: Optional[str]


class DependencyScanner:
    """
    Dependency vulnerability scanner.
    Scans Python dependencies for known vulnerabilities.
    """
    
    def __init__(self, requirements_file: Optional[Path] = None):
        """
        Initialize dependency scanner
        
        Args:
            requirements_file: Path to requirements.txt or pyproject.toml
        """
        self.requirements_file = requirements_file or Path("requirements.txt")
        self._vulnerabilities: List[VulnerabilityReport] = []
    
    def scan_with_pip_audit(self) -> List[VulnerabilityReport]:
        """
        Scan dependencies using pip-audit
        
        Returns:
            List of vulnerability reports
        """
        logger.info("Running pip-audit vulnerability scan")
        
        try:
            result = subprocess.run(
                ["pip-audit", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                logger.info("No vulnerabilities found")
                return []
            
            # Parse JSON output
            try:
                audit_data = json.loads(result.stdout)
                return self._parse_pip_audit_output(audit_data)
            except json.JSONDecodeError:
                logger.warning("Failed to parse pip-audit JSON output")
                return []
                
        except FileNotFoundError:
            logger.warning("pip-audit not found, skipping scan")
            return []
        except subprocess.TimeoutExpired:
            logger.error("pip-audit scan timed out")
            return []
        except Exception as e:
            logger.error(f"pip-audit scan failed: {e}")
            return []
    
    def scan_with_bandit(self, target_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        Scan code for security issues using Bandit
        
        Args:
            target_dir: Directory to scan (default: current directory)
            
        Returns:
            List of security issues
        """
        target_dir = target_dir or Path(".")
        logger.info(f"Running Bandit security scan on {target_dir}")
        
        try:
            result = subprocess.run(
                ["bandit", "-r", str(target_dir), "-f", "json"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            try:
                bandit_data = json.loads(result.stdout)
                return bandit_data.get("results", [])
            except json.JSONDecodeError:
                logger.warning("Failed to parse Bandit JSON output")
                return []
                
        except FileNotFoundError:
            logger.warning("Bandit not found, skipping scan")
            return []
        except subprocess.TimeoutExpired:
            logger.error("Bandit scan timed out")
            return []
        except Exception as e:
            logger.error(f"Bandit scan failed: {e}")
            return []
    
    def _parse_pip_audit_output(self, audit_data: Dict[str, Any]) -> List[VulnerabilityReport]:
        """
        Parse pip-audit JSON output
        
        Args:
            audit_data: Raw audit data from pip-audit
            
        Returns:
            List of vulnerability reports
        """
        vulnerabilities = []
        
        for dep in audit_data.get("dependencies", []):
            for vuln in dep.get("vulnerabilities", []):
                report = VulnerabilityReport(
                    package=dep.get("name", ""),
                    version=dep.get("version", ""),
                    vulnerability_id=vuln.get("id", ""),
                    severity=vuln.get("severity", "UNKNOWN"),
                    description=vuln.get("description", ""),
                    fix_available=vuln.get("fix_versions", []) != [],
                    fixed_version=vuln.get("fix_versions", [None])[0] if vuln.get("fix_versions") else None
                )
                vulnerabilities.append(report)
        
        return vulnerabilities
    
    def generate_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive vulnerability report
        
        Returns:
            Dictionary with scan results
        """
        pip_audit_results = self.scan_with_pip_audit()
        bandit_results = self.scan_with_bandit()
        
        # Count vulnerabilities by severity
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        for vuln in pip_audit_results:
            severity = vuln.severity.upper()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        return {
            "timestamp": datetime.now().isoformat(),
            "dependency_vulnerabilities": len(pip_audit_results),
            "security_issues": len(bandit_results),
            "severity_breakdown": severity_counts,
            "vulnerabilities": [
                {
                    "package": v.package,
                    "version": v.version,
                    "id": v.vulnerability_id,
                    "severity": v.severity,
                    "description": v.description,
                    "fix_available": v.fix_available,
                    "fixed_version": v.fixed_version
                }
                for v in pip_audit_results
            ],
            "bandit_issues": bandit_results
        }
    
    def save_report(self, output_file: Path) -> None:
        """
        Save vulnerability report to file
        
        Args:
            output_file: Path to output file
        """
        report = self.generate_report()
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Vulnerability report saved to {output_file}")


def run_dependency_scan(
    requirements_file: Optional[Path] = None,
    output_file: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Run comprehensive dependency vulnerability scan
    
    Args:
        requirements_file: Path to requirements file
        output_file: Path to save report
        
    Returns:
        Vulnerability scan report
    """
    scanner = DependencyScanner(requirements_file)
    report = scanner.generate_report()
    
    if output_file:
        scanner.save_report(output_file)
    
    return report


def check_vulnerability_thresholds(
    report: Dict[str, Any],
    max_critical: int = 0,
    max_high: int = 0,
    max_medium: int = 10,
    max_low: int = 50
) -> bool:
    """
    Check if vulnerability counts are within acceptable thresholds
    
    Args:
        report: Vulnerability scan report
        max_critical: Maximum allowed critical vulnerabilities
        max_high: Maximum allowed high vulnerabilities
        max_medium: Maximum allowed medium vulnerabilities
        max_low: Maximum allowed low vulnerabilities
        
    Returns:
        True if within thresholds, False otherwise
    """
    severity = report.get("severity_breakdown", {})
    
    if severity.get("CRITICAL", 0) > max_critical:
        logger.error(f"Critical vulnerabilities exceed threshold: {severity.get('CRITICAL')} > {max_critical}")
        return False
    
    if severity.get("HIGH", 0) > max_high:
        logger.error(f"High vulnerabilities exceed threshold: {severity.get('HIGH')} > {max_high}")
        return False
    
    if severity.get("MEDIUM", 0) > max_medium:
        logger.warning(f"Medium vulnerabilities exceed threshold: {severity.get('MEDIUM')} > {max_medium}")
    
    if severity.get("LOW", 0) > max_low:
        logger.warning(f"Low vulnerabilities exceed threshold: {severity.get('LOW')} > {max_low}")
    
    return True
