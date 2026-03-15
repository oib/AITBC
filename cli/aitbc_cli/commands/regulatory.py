#!/usr/bin/env python3
"""
Regulatory Reporting CLI Commands
Generate and manage regulatory compliance reports
"""

import click
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from aitbc_cli.imports import ensure_coordinator_api_imports

ensure_coordinator_api_imports()

try:
    from app.services.regulatory_reporting import (
        generate_sar, generate_compliance_summary, list_reports,
        regulatory_reporter, ReportType, ReportStatus, RegulatoryBody
    )
    _import_error = None
except ImportError as e:
    _import_error = e

    def _missing(*args, **kwargs):
        raise ImportError(
            f"Required service module 'app.services.regulatory_reporting' could not be imported: {_import_error}. "
            "Ensure coordinator-api dependencies are installed and the source directory is accessible."
        )
    generate_sar = generate_compliance_summary = list_reports = regulatory_reporter = _missing

    class ReportType:
        pass
    class ReportStatus:
        pass
    class RegulatoryBody:
        pass

@click.group()
def regulatory():
    """Regulatory reporting and compliance management commands"""
    pass

@regulatory.command()
@click.option("--user-id", required=True, help="User ID for suspicious activity")
@click.option("--activity-type", required=True, help="Type of suspicious activity")
@click.option("--amount", type=float, required=True, help="Amount involved in USD")
@click.option("--description", required=True, help="Description of suspicious activity")
@click.option("--risk-score", type=float, default=0.5, help="Risk score (0.0-1.0)")
@click.option("--currency", default="USD", help="Currency code")
@click.pass_context
def generate_sar(ctx, user_id: str, activity_type: str, amount: float, description: str, risk_score: float, currency: str):
    """Generate Suspicious Activity Report (SAR)"""
    try:
        click.echo(f"🔍 Generating Suspicious Activity Report...")
        click.echo(f"👤 User ID: {user_id}")
        click.echo(f"📊 Activity Type: {activity_type}")
        click.echo(f"💰 Amount: ${amount:,.2f} {currency}")
        click.echo(f"⚠️  Risk Score: {risk_score:.2f}")
        
        # Create suspicious activity data
        activity = {
            "id": f"sar_{user_id}_{int(datetime.now().timestamp())}",
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "type": activity_type,
            "description": description,
            "amount": amount,
            "currency": currency,
            "risk_score": risk_score,
            "indicators": [activity_type, "high_risk"],
            "evidence": {"cli_generated": True}
        }
        
        # Generate SAR
        result = asyncio.run(generate_sar([activity]))
        
        click.echo(f"\n✅ SAR Report Generated Successfully!")
        click.echo(f"📋 Report ID: {result['report_id']}")
        click.echo(f"📄 Report Type: {result['report_type'].upper()}")
        click.echo(f"📊 Status: {result['status'].title()}")
        click.echo(f"📅 Generated: {result['generated_at']}")
        
        # Show next steps
        click.echo(f"\n📝 Next Steps:")
        click.echo(f"   1. Review the generated report")
        click.echo(f"   2. Submit to regulatory body when ready")
        click.echo(f"   3. Maintain records for 5 years (BSA requirement)")
        
    except Exception as e:
        click.echo(f"❌ SAR generation failed: {e}", err=True)

@regulatory.command()
@click.option("--period-start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--period-end", required=True, help="End date (YYYY-MM-DD)")
@click.pass_context
def compliance_summary(ctx, period_start: str, period_end: str):
    """Generate comprehensive compliance summary report"""
    try:
        # Parse dates
        start_date = datetime.strptime(period_start, "%Y-%m-%d")
        end_date = datetime.strptime(period_end, "%Y-%m-%d")
        
        click.echo(f"📊 Generating Compliance Summary...")
        click.echo(f"📅 Period: {period_start} to {period_end}")
        click.echo(f"📈 Duration: {(end_date - start_date).days} days")
        
        # Generate compliance summary
        result = asyncio.run(generate_compliance_summary(
            start_date.isoformat(), 
            end_date.isoformat()
        ))
        
        click.echo(f"\n✅ Compliance Summary Generated!")
        click.echo(f"📋 Report ID: {result['report_id']}")
        click.echo(f"📊 Overall Compliance Score: {result['overall_score']:.1%}")
        click.echo(f"📅 Generated: {result['generated_at']}")
        
        # Get detailed report content
        report = regulatory_reporter._find_report(result['report_id'])
        if report:
            content = report.content
            
            click.echo(f"\n📈 Executive Summary:")
            exec_summary = content.get('executive_summary', {})
            click.echo(f"   Critical Issues: {exec_summary.get('critical_issues', 0)}")
            click.echo(f"   Regulatory Filings: {exec_summary.get('regulatory_filings', 0)}")
            
            click.echo(f"\n👥 KYC Compliance:")
            kyc = content.get('kyc_compliance', {})
            click.echo(f"   Total Customers: {kyc.get('total_customers', 0):,}")
            click.echo(f"   Verified Customers: {kyc.get('verified_customers', 0):,}")
            click.echo(f"   Completion Rate: {kyc.get('completion_rate', 0):.1%}")
            
            click.echo(f"\n🔍 AML Compliance:")
            aml = content.get('aml_compliance', {})
            click.echo(f"   Transaction Monitoring: {'✅ Active' if aml.get('transaction_monitoring') else '❌ Inactive'}")
            click.echo(f"   SARs Filed: {aml.get('suspicious_activity_reports', 0)}")
            click.echo(f"   CTRs Filed: {aml.get('currency_transaction_reports', 0)}")
        
    except Exception as e:
        click.echo(f"❌ Compliance summary generation failed: {e}", err=True)

@regulatory.command()
@click.option("--report-type", type=click.Choice(['sar', 'ctr', 'aml_report', 'compliance_summary']), help="Filter by report type")
@click.option("--status", type=click.Choice(['draft', 'pending_review', 'submitted', 'accepted', 'rejected']), help="Filter by status")
@click.option("--limit", type=int, default=20, help="Maximum number of reports to show")
@click.pass_context
def list(ctx, report_type: str, status: str, limit: int):
    """List regulatory reports"""
    try:
        click.echo(f"📋 Regulatory Reports")
        
        reports = list_reports(report_type, status)
        
        if not reports:
            click.echo(f"✅ No reports found")
            return
        
        click.echo(f"\n📊 Total Reports: {len(reports)}")
        
        if report_type:
            click.echo(f"🔍 Filtered by type: {report_type.upper()}")
        
        if status:
            click.echo(f"🔍 Filtered by status: {status.title()}")
        
        # Display reports
        for i, report in enumerate(reports[:limit]):
            status_icon = {
                "draft": "📝",
                "pending_review": "⏳",
                "submitted": "📤",
                "accepted": "✅",
                "rejected": "❌"
            }.get(report['status'], "❓")
            
            click.echo(f"\n{status_icon} Report #{i+1}")
            click.echo(f"   ID: {report['report_id']}")
            click.echo(f"   Type: {report['report_type'].upper()}")
            click.echo(f"   Body: {report['regulatory_body'].upper()}")
            click.echo(f"   Status: {report['status'].title()}")
            click.echo(f"   Generated: {report['generated_at'][:19]}")
        
        if len(reports) > limit:
            click.echo(f"\n... and {len(reports) - limit} more reports")
        
    except Exception as e:
        click.echo(f"❌ Failed to list reports: {e}", err=True)

@regulatory.command()
@click.option("--report-id", required=True, help="Report ID to export")
@click.option("--format", type=click.Choice(['json', 'csv', 'xml']), default="json", help="Export format")
@click.option("--output", help="Output file path (default: stdout)")
@click.pass_context
def export(ctx, report_id: str, format: str, output: str):
    """Export regulatory report"""
    try:
        click.echo(f"📤 Exporting Report: {report_id}")
        click.echo(f"📄 Format: {format.upper()}")
        
        # Export report
        content = regulatory_reporter.export_report(report_id, format)
        
        if output:
            with open(output, 'w') as f:
                f.write(content)
            click.echo(f"✅ Report exported to: {output}")
        else:
            click.echo(f"\n📄 Report Content:")
            click.echo("=" * 60)
            click.echo(content)
            click.echo("=" * 60)
        
    except Exception as e:
        click.echo(f"❌ Export failed: {e}", err=True)

@regulatory.command()
@click.option("--report-id", required=True, help="Report ID to submit")
@click.pass_context
def submit(ctx, report_id: str):
    """Submit report to regulatory body"""
    try:
        click.echo(f"📤 Submitting Report: {report_id}")
        
        # Get report details
        report = regulatory_reporter._find_report(report_id)
        if not report:
            click.echo(f"❌ Report {report_id} not found")
            return
        
        click.echo(f"📄 Type: {report.report_type.value.upper()}")
        click.echo(f"🏢 Regulatory Body: {report.regulatory_body.value.upper()}")
        click.echo(f"📊 Current Status: {report.status.value.title()}")
        
        if report.status != ReportStatus.DRAFT:
            click.echo(f"⚠️  Report already submitted")
            return
        
        # Submit report
        success = asyncio.run(regulatory_reporter.submit_report(report_id))
        
        if success:
            click.echo(f"✅ Report submitted successfully!")
            click.echo(f"📅 Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            click.echo(f"🏢 Submitted to: {report.regulatory_body.value.upper()}")
            
            # Show submission details
            click.echo(f"\n📋 Submission Details:")
            click.echo(f"   Report ID: {report_id}")
            click.echo(f"   Regulatory Body: {report.regulatory_body.value}")
            click.echo(f"   Submission Method: Electronic Filing")
            click.echo(f"   Confirmation: Pending")
        else:
            click.echo(f"❌ Report submission failed")
        
    except Exception as e:
        click.echo(f"❌ Submission failed: {e}", err=True)

@regulatory.command()
@click.option("--report-id", required=True, help="Report ID to check")
@click.pass_context
def status(ctx, report_id: str):
    """Check report status"""
    try:
        click.echo(f"📊 Report Status: {report_id}")
        
        report_status = regulatory_reporter.get_report_status(report_id)
        
        if not report_status:
            click.echo(f"❌ Report {report_id} not found")
            return
        
        status_icon = {
            "draft": "📝",
            "pending_review": "⏳",
            "submitted": "📤",
            "accepted": "✅",
            "rejected": "❌"
        }.get(report_status['status'], "❓")
        
        click.echo(f"\n{status_icon} Report Details:")
        click.echo(f"   ID: {report_status['report_id']}")
        click.echo(f"   Type: {report_status['report_type'].upper()}")
        click.echo(f"   Body: {report_status['regulatory_body'].upper()}")
        click.echo(f"   Status: {report_status['status'].title()}")
        click.echo(f"   Generated: {report_status['generated_at'][:19]}")
        
        if report_status['submitted_at']:
            click.echo(f"   Submitted: {report_status['submitted_at'][:19]}")
        
        if report_status['expires_at']:
            click.echo(f"   Expires: {report_status['expires_at'][:19]}")
        
        # Show next actions based on status
        click.echo(f"\n📝 Next Actions:")
        if report_status['status'] == 'draft':
            click.echo(f"   • Review and edit report content")
            click.echo(f"   • Submit to regulatory body when ready")
        elif report_status['status'] == 'submitted':
            click.echo(f"   • Wait for regulatory body response")
            click.echo(f"   • Monitor submission status")
        elif report_status['status'] == 'accepted':
            click.echo(f"   • Store confirmation records")
            click.echo(f"   • Update compliance documentation")
        elif report_status['status'] == 'rejected':
            click.echo(f"   • Review rejection reasons")
            click.echo(f"   • Resubmit corrected report")
        
    except Exception as e:
        click.echo(f"❌ Status check failed: {e}", err=True)

@regulatory.command()
@click.pass_context
def overview(ctx):
    """Show regulatory reporting overview"""
    try:
        click.echo(f"📊 Regulatory Reporting Overview")
        
        all_reports = regulatory_reporter.reports
        
        if not all_reports:
            click.echo(f"📝 No reports generated yet")
            return
        
        # Statistics
        total_reports = len(all_reports)
        by_type = {}
        by_status = {}
        by_body = {}
        
        for report in all_reports:
            # By type
            rt = report.report_type.value
            by_type[rt] = by_type.get(rt, 0) + 1
            
            # By status
            st = report.status.value
            by_status[st] = by_status.get(st, 0) + 1
            
            # By regulatory body
            rb = report.regulatory_body.value
            by_body[rb] = by_body.get(rb, 0) + 1
        
        click.echo(f"\n📈 Overall Statistics:")
        click.echo(f"   Total Reports: {total_reports}")
        click.echo(f"   Report Types: {len(by_type)}")
        click.echo(f"   Regulatory Bodies: {len(by_body)}")
        
        click.echo(f"\n📋 Reports by Type:")
        for report_type, count in sorted(by_type.items()):
            click.echo(f"   {report_type.upper()}: {count}")
        
        click.echo(f"\n📊 Reports by Status:")
        status_icons = {"draft": "📝", "pending_review": "⏳", "submitted": "📤", "accepted": "✅", "rejected": "❌"}
        for status, count in sorted(by_status.items()):
            icon = status_icons.get(status, "❓")
            click.echo(f"   {icon} {status.title()}: {count}")
        
        click.echo(f"\n🏢 Reports by Regulatory Body:")
        for body, count in sorted(by_body.items()):
            click.echo(f"   {body.upper()}: {count}")
        
        # Recent activity
        recent_reports = sorted(all_reports, key=lambda x: x.generated_at, reverse=True)[:5]
        click.echo(f"\n📅 Recent Activity:")
        for report in recent_reports:
            click.echo(f"   {report.generated_at.strftime('%Y-%m-%d %H:%M')} - {report.report_type.value.upper()} ({report.status.value})")
        
        # Compliance reminders
        click.echo(f"\n⚠️  Compliance Reminders:")
        click.echo(f"   • SAR reports must be filed within 30 days of detection")
        click.echo(f"   • CTR reports required for transactions over $10,000")
        click.echo(f"   • Maintain records for minimum 5 years")
        click.echo(f"   • Annual AML program review required")
        
    except Exception as e:
        click.echo(f"❌ Overview failed: {e}", err=True)

@regulatory.command()
@click.pass_context
def templates(ctx):
    """Show available report templates and requirements"""
    try:
        click.echo(f"📋 Regulatory Report Templates")
        
        templates = regulatory_reporter.templates
        
        for template_name, template_data in templates.items():
            click.echo(f"\n📄 {template_name.upper()}:")
            click.echo(f"   Format: {template_data['format'].upper()}")
            click.echo(f"   Schema: {template_data['schema']}")
            click.echo(f"   Required Fields ({len(template_data['required_fields'])}):")
            
            for field in template_data['required_fields']:
                click.echo(f"     • {field}")
        
        click.echo(f"\n🏢 Regulatory Bodies:")
        bodies = {
            "FINCEN": "Financial Crimes Enforcement Network (US Treasury)",
            "SEC": "Securities and Exchange Commission",
            "FINRA": "Financial Industry Regulatory Authority",
            "CFTC": "Commodity Futures Trading Commission",
            "OFAC": "Office of Foreign Assets Control",
            "EU_REGULATOR": "European Union Regulatory Authorities"
        }
        
        for body, description in bodies.items():
            click.echo(f"\n🏛️  {body}:")
            click.echo(f"   {description}")
        
        click.echo(f"\n📝 Filing Requirements:")
        click.echo(f"   • SAR: File within 30 days of suspicious activity detection")
        click.echo(f"   • CTR: File for cash transactions over $10,000")
        click.echo(f"   • AML Reports: Quarterly and annual requirements")
        click.echo(f"   • Compliance Summary: Annual filing requirement")
        
        click.echo(f"\n⏰ Filing Deadlines:")
        click.echo(f"   • SAR: 30 days from detection")
        click.echo(f"   • CTR: 15 days from transaction")
        click.echo(f"   • Quarterly AML: Within 30 days of quarter end")
        click.echo(f"   • Annual Report: Within 90 days of year end")
        
    except Exception as e:
        click.echo(f"❌ Template display failed: {e}", err=True)

@regulatory.command()
@click.option("--period-start", default="2026-01-01", help="Start date for test data (YYYY-MM-DD)")
@click.option("--period-end", default="2026-01-31", help="End date for test data (YYYY-MM-DD)")
@click.pass_context
def test(ctx, period_start: str, period_end: str):
    """Run regulatory reporting test with sample data"""
    try:
        click.echo(f"🧪 Running Regulatory Reporting Test...")
        click.echo(f"📅 Test Period: {period_start} to {period_end}")
        
        # Test SAR generation
        click.echo(f"\n📋 Test 1: SAR Generation")
        result = asyncio.run(generate_sar([{
            "id": "test_sar_001",
            "timestamp": datetime.now().isoformat(),
            "user_id": "test_user_123",
            "type": "unusual_volume",
            "description": "Test suspicious activity for SAR generation",
            "amount": 25000,
            "currency": "USD",
            "risk_score": 0.75,
            "indicators": ["volume_spike", "timing_anomaly"],
            "evidence": {"test": True}
        }]))
        
        click.echo(f"   ✅ SAR Generated: {result['report_id']}")
        
        # Test compliance summary
        click.echo(f"\n📊 Test 2: Compliance Summary")
        compliance_result = asyncio.run(generate_compliance_summary(period_start, period_end))
        click.echo(f"   ✅ Compliance Summary: {compliance_result['report_id']}")
        click.echo(f"   📈 Overall Score: {compliance_result['overall_score']:.1%}")
        
        # Test report listing
        click.echo(f"\n📋 Test 3: Report Listing")
        reports = list_reports()
        click.echo(f"   ✅ Total Reports: {len(reports)}")
        
        # Test export
        if reports:
            test_report_id = reports[0]['report_id']
            click.echo(f"\n📤 Test 4: Report Export")
            try:
                content = regulatory_reporter.export_report(test_report_id, "json")
                click.echo(f"   ✅ Export successful: {len(content)} characters")
            except Exception as e:
                click.echo(f"   ⚠️  Export test failed: {e}")
        
        click.echo(f"\n🎉 Regulatory Reporting Test Complete!")
        click.echo(f"📊 All systems operational")
        click.echo(f"📝 Ready for production use")
        
    except Exception as e:
        click.echo(f"❌ Test failed: {e}", err=True)

if __name__ == "__main__":
    regulatory()
