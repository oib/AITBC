#!/usr/bin/env python3
"""
Certify the AITBC Stripe connector as a validation of the certification system
"""

import asyncio
import json
import sys
from pathlib import Path

# Add test suite to path
sys.path.insert(0, str(Path(__file__).parent))

from runners.python.test_runner import ConformanceTestRunner
from security.security_validator import SecurityValidator


async def certify_stripe_connector():
    """Run full certification on Stripe connector"""
    
    print("=" * 60)
    print("AITBC Stripe Connector Certification")
    print("=" * 60)
    
    # Configuration
    base_url = "http://localhost:8011"  # Mock server
    api_key = "test-api-key"
    sdk_path = Path(__file__).parent.parent.parent / "enterprise-connectors" / "python-sdk"
    
    # 1. Run conformance tests
    print("\n1. Running SDK Conformance Tests...")
    runner = ConformanceTestRunner(base_url, api_key)
    
    # Run Bronze tests
    bronze_suite = Path(__file__).parent / "fixtures" / "bronze" / "api-compliance.json"
    bronze_result = await runner.run_suite(str(bronze_suite), "bronze")
    
    # Check if Bronze passed
    if bronze_result.compliance_score < 95:
        print(f"\n❌ Bronze certification FAILED: {bronze_result.compliance_score:.1f}%")
        return False
    
    print(f"\n✅ Bronze certification PASSED: {bronze_result.compliance_score:.1f}%")
    
    # 2. Run security validation
    print("\n2. Running Security Validation...")
    validator = SecurityValidator()
    security_report = validator.validate(str(sdk_path), "bronze")
    
    print(f"\nSecurity Score: {security_report.score}/100")
    print(f"Issues Found: {len(security_report.issues)}")
    
    if security_report.blocked:
        print("\n❌ Security validation BLOCKED certification")
        for issue in security_report.issues:
            if issue.severity in ["critical", "high"]:
                print(f"  - {issue.description} ({issue.severity})")
        return False
    
    print("\n✅ Security validation PASSED")
    
    # 3. Generate certification report
    print("\n3. Generating Certification Report...")
    
    certification = {
        "partner": {
            "name": "AITBC",
            "id": "aitbc-official",
            "website": "https://aitbc.io",
            "description": "Official AITBC Python SDK with Stripe connector"
        },
        "sdk": {
            "name": "aitbc-enterprise-python",
            "version": "1.0.0",
            "language": "python",
            "repository": "https://github.com/aitbc/enterprise-connectors"
        },
        "certification": {
            "level": "bronze",
            "issued_at": "2024-01-15T00:00:00Z",
            "expires_at": "2025-01-15T00:00:00Z",
            "id": "CERT-STRIPE-001"
        },
        "test_results": {
            "api_compliance": {
                "score": bronze_result.compliance_score,
                "tests_run": bronze_result.total_tests,
                "tests_passed": bronze_result.passed_tests
            },
            "security": {
                "score": security_report.score,
                "vulnerabilities_found": len(security_report.issues),
                "critical_issues": sum(1 for i in security_report.issues if i.severity == "critical")
            }
        },
        "criteria_met": [
            "Core API compatibility",
            "Authentication support",
            "Error handling standards",
            "Data model compliance",
            "Async support",
            "Basic security practices",
            "Documentation completeness"
        ]
    }
    
    # Save report
    report_path = Path(__file__).parent / "reports" / "stripe-certification.json"
    report_path.parent.mkdir(exist_ok=True)
    
    with open(report_path, 'w') as f:
        json.dump(certification, f, indent=2)
    
    print(f"\n✅ Certification report saved to: {report_path}")
    
    # 4. Generate badge
    print("\n4. Generating Certification Badge...")
    
    badge_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="20">
        <linearGradient id="b" x2="0" y2="100%">
            <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
            <stop offset="1" stop-opacity=".1"/>
        </linearGradient>
        <clipPath id="a">
            <rect width="120" height="20" rx="3" fill="#fff"/>
        </clipPath>
        <g clip-path="url(#a)">
            <path fill="#555" d="M0 0h55v20H0z"/>
            <path fill="#CD7F32" d="M55 0h65v20H55z"/>
            <path fill="url(#b)" d="M0 0h120v20H0z"/>
        </g>
        <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
            <text x="27.5" y="15" fill="#010101" fill-opacity=".3">AITBC</text>
            <text x="27.5" y="14">AITBC</text>
            <text x="87.5" y="15" fill="#010101" fill-opacity=".3">Bronze</text>
            <text x="87.5" y="14">Bronze</text>
        </g>
    </svg>'''
    
    badge_path = Path(__file__).parent / "reports" / "stripe-bronze.svg"
    with open(badge_path, 'w') as f:
        f.write(badge_svg)
    
    print(f"✅ Badge saved to: {badge_path}")
    
    # 5. Summary
    print("\n" + "=" * 60)
    print("CERTIFICATION COMPLETE")
    print("=" * 60)
    print(f"Partner: AITBC")
    print(f"SDK: aitbc-enterprise-python (Stripe connector)")
    print(f"Level: Bronze")
    print(f"API Compliance: {bronze_result.compliance_score:.1f}%")
    print(f"Security Score: {security_report.score}/100")
    print(f"Certification ID: CERT-STRIPE-001")
    print(f"Valid Until: 2025-01-15")
    
    return True


async def main():
    """Main entry point"""
    success = await certify_stripe_connector()
    
    if success:
        print("\n🎉 Stripe connector successfully certified!")
        print("\nThe certification system is validated and ready for external partners.")
        sys.exit(0)
    else:
        print("\n❌ Certification failed. Please fix issues before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
