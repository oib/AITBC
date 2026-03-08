#!/usr/bin/env python3
"""
Compliance CLI Commands - KYC/AML Integration
Real compliance verification and monitoring commands
"""

import click
import asyncio
import json
from typing import Optional, Dict, Any
from datetime import datetime

# Import compliance providers
from aitbc_cli.kyc_aml_providers import submit_kyc_verification, check_kyc_status, perform_aml_screening

@click.group()
def compliance():
    """Compliance and regulatory management commands"""
    pass

@compliance.command()
@click.option("--user-id", required=True, help="User ID to verify")
@click.option("--provider", required=True, type=click.Choice(['chainalysis', 'sumsub', 'onfido', 'jumio', 'veriff']), help="KYC provider")
@click.option("--first-name", required=True, help="Customer first name")
@click.option("--last-name", required=True, help="Customer last name")
@click.option("--email", required=True, help="Customer email")
@click.option("--dob", help="Date of birth (YYYY-MM-DD)")
@click.option("--phone", help="Phone number")
@click.pass_context
def kyc_submit(ctx, user_id: str, provider: str, first_name: str, last_name: str, email: str, dob: str, phone: str):
    """Submit KYC verification request"""
    try:
        # Prepare customer data
        customer_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "date_of_birth": dob,
            "phone": phone
        }
        
        # Remove None values
        customer_data = {k: v for k, v in customer_data.items() if v is not None}
        
        # Submit KYC
        click.echo(f"🔍 Submitting KYC verification for user {user_id} to {provider}...")
        
        result = asyncio.run(submit_kyc_verification(user_id, provider, customer_data))
        
        click.echo(f"✅ KYC verification submitted successfully!")
        click.echo(f"📋 Request ID: {result['request_id']}")
        click.echo(f"👤 User ID: {result['user_id']}")
        click.echo(f"🏢 Provider: {result['provider']}")
        click.echo(f"📊 Status: {result['status']}")
        click.echo(f"⚠️  Risk Score: {result['risk_score']:.3f}")
        click.echo(f"📅 Submitted: {result['created_at']}")
        
    except Exception as e:
        click.echo(f"❌ KYC submission failed: {e}", err=True)

@compliance.command()
@click.option("--request-id", required=True, help="KYC request ID to check")
@click.option("--provider", required=True, type=click.Choice(['chainalysis', 'sumsub', 'onfido', 'jumio', 'veriff']), help="KYC provider")
@click.pass_context
def kyc_status(ctx, request_id: str, provider: str):
    """Check KYC verification status"""
    try:
        click.echo(f"🔍 Checking KYC status for request {request_id}...")
        
        result = asyncio.run(check_kyc_status(request_id, provider))
        
        # Status icons
        status_icons = {
            "pending": "⏳",
            "approved": "✅",
            "rejected": "❌",
            "failed": "💥",
            "expired": "⏰"
        }
        
        status_icon = status_icons.get(result['status'], "❓")
        
        click.echo(f"{status_icon} KYC Status: {result['status'].upper()}")
        click.echo(f"📋 Request ID: {result['request_id']}")
        click.echo(f"👤 User ID: {result['user_id']}")
        click.echo(f"🏢 Provider: {result['provider']}")
        click.echo(f"⚠️  Risk Score: {result['risk_score']:.3f}")
        
        if result.get('rejection_reason'):
            click.echo(f"🚫 Rejection Reason: {result['rejection_reason']}")
        
        click.echo(f"📅 Created: {result['created_at']}")
        
        # Provide guidance based on status
        if result['status'] == 'pending':
            click.echo(f"\n💡 Verification is in progress. Check again later.")
        elif result['status'] == 'approved':
            click.echo(f"\n🎉 User is verified and can proceed with trading!")
        elif result['status'] in ['rejected', 'failed']:
            click.echo(f"\n⚠️  Verification failed. User may need to resubmit documents.")
        
    except Exception as e:
        click.echo(f"❌ KYC status check failed: {e}", err=True)

@compliance.command()
@click.option("--user-id", required=True, help="User ID to screen")
@click.option("--first-name", required=True, help="User first name")
@click.option("--last-name", required=True, help="User last name")
@click.option("--email", required=True, help="User email")
@click.option("--dob", help="Date of birth (YYYY-MM-DD)")
@click.option("--phone", help="Phone number")
@click.pass_context
def aml_screen(ctx, user_id: str, first_name: str, last_name: str, email: str, dob: str, phone: str):
    """Perform AML screening on user"""
    try:
        # Prepare user data
        user_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "date_of_birth": dob,
            "phone": phone
        }
        
        # Remove None values
        user_data = {k: v for k, v in user_data.items() if v is not None}
        
        click.echo(f"🔍 Performing AML screening for user {user_id}...")
        
        result = asyncio.run(perform_aml_screening(user_id, user_data))
        
        # Risk level icons
        risk_icons = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴"
        }
        
        risk_icon = risk_icons.get(result['risk_level'], "❓")
        
        click.echo(f"{risk_icon} AML Risk Level: {result['risk_level'].upper()}")
        click.echo(f"📊 Risk Score: {result['risk_score']:.3f}")
        click.echo(f"👤 User ID: {result['user_id']}")
        click.echo(f"🏢 Provider: {result['provider']}")
        click.echo(f"📋 Check ID: {result['check_id']}")
        click.echo(f"📅 Screened: {result['checked_at']}")
        
        # Sanctions hits
        if result['sanctions_hits']:
            click.echo(f"\n🚨 SANCTIONS HITS FOUND:")
            for hit in result['sanctions_hits']:
                click.echo(f"   • List: {hit['list']}")
                click.echo(f"     Name: {hit['name']}")
                click.echo(f"     Confidence: {hit['confidence']:.2%}")
        else:
            click.echo(f"\n✅ No sanctions hits found")
        
        # Guidance based on risk level
        if result['risk_level'] == 'critical':
            click.echo(f"\n🚨 CRITICAL RISK: Immediate action required!")
        elif result['risk_level'] == 'high':
            click.echo(f"\n⚠️  HIGH RISK: Manual review recommended")
        elif result['risk_level'] == 'medium':
            click.echo(f"\n🟡 MEDIUM RISK: Monitor transactions closely")
        else:
            click.echo(f"\n✅ LOW RISK: User cleared for normal activity")
        
    except Exception as e:
        click.echo(f"❌ AML screening failed: {e}", err=True)

@compliance.command()
@click.option("--user-id", required=True, help="User ID for full compliance check")
@click.option("--first-name", required=True, help="User first name")
@click.option("--last-name", required=True, help="User last name")
@click.option("--email", required=True, help="User email")
@click.option("--dob", help="Date of birth (YYYY-MM-DD)")
@click.option("--phone", help="Phone number")
@click.option("--kyc-provider", default="chainalysis", type=click.Choice(['chainalysis', 'sumsub', 'onfido', 'jumio', 'veriff']), help="KYC provider")
@click.pass_context
def full_check(ctx, user_id: str, first_name: str, last_name: str, email: str, dob: str, phone: str, kyc_provider: str):
    """Perform full compliance check (KYC + AML)"""
    try:
        click.echo(f"🔍 Performing full compliance check for user {user_id}...")
        click.echo(f"🏢 KYC Provider: {kyc_provider}")
        click.echo()
        
        # Prepare user data
        user_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "date_of_birth": dob,
            "phone": phone
        }
        
        user_data = {k: v for k, v in user_data.items() if v is not None}
        
        # Step 1: Submit KYC
        click.echo("📋 Step 1: Submitting KYC verification...")
        kyc_result = asyncio.run(submit_kyc_verification(user_id, kyc_provider, user_data))
        click.echo(f"✅ KYC submitted: {kyc_result['request_id']}")
        
        # Step 2: Check KYC status
        click.echo("\n📋 Step 2: Checking KYC status...")
        kyc_status = asyncio.run(check_kyc_status(kyc_result['request_id'], kyc_provider))
        
        # Step 3: AML Screening
        click.echo("\n🔍 Step 3: Performing AML screening...")
        aml_result = asyncio.run(perform_aml_screening(user_id, user_data))
        
        # Display comprehensive results
        click.echo(f"\n{'='*60}")
        click.echo(f"📊 COMPLIANCE CHECK SUMMARY")
        click.echo(f"{'='*60}")
        
        # KYC Results
        kyc_icons = {"pending": "⏳", "approved": "✅", "rejected": "❌", "failed": "💥"}
        kyc_icon = kyc_icons.get(kyc_status['status'], "❓")
        
        click.echo(f"\n{kyc_icon} KYC Verification:")
        click.echo(f"   Status: {kyc_status['status'].upper()}")
        click.echo(f"   Risk Score: {kyc_status['risk_score']:.3f}")
        click.echo(f"   Provider: {kyc_status['provider']}")
        
        if kyc_status.get('rejection_reason'):
            click.echo(f"   Reason: {kyc_status['rejection_reason']}")
        
        # AML Results
        risk_icons = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
        aml_icon = risk_icons.get(aml_result['risk_level'], "❓")
        
        click.echo(f"\n{aml_icon} AML Screening:")
        click.echo(f"   Risk Level: {aml_result['risk_level'].upper()}")
        click.echo(f"   Risk Score: {aml_result['risk_score']:.3f}")
        click.echo(f"   Sanctions Hits: {len(aml_result['sanctions_hits'])}")
        
        # Overall Assessment
        click.echo(f"\n📋 OVERALL ASSESSMENT:")
        
        kyc_approved = kyc_status['status'] == 'approved'
        aml_safe = aml_result['risk_level'] in ['low', 'medium']
        
        if kyc_approved and aml_safe:
            click.echo(f"✅ USER APPROVED FOR TRADING")
            click.echo(f"   ✅ KYC: Verified")
            click.echo(f"   ✅ AML: Safe")
        elif not kyc_approved:
            click.echo(f"❌ USER REJECTED")
            click.echo(f"   ❌ KYC: {kyc_status['status']}")
            click.echo(f"   AML: {aml_result['risk_level']}")
        else:
            click.echo(f"⚠️  USER REQUIRES MANUAL REVIEW")
            click.echo(f"   KYC: {kyc_status['status']}")
            click.echo(f"   ⚠️  AML: {aml_result['risk_level']} risk")
        
        click.echo(f"\n{'='*60}")
        
    except Exception as e:
        click.echo(f"❌ Full compliance check failed: {e}", err=True)

@compliance.command()
@click.pass_context
def list_providers(ctx):
    """List all supported compliance providers"""
    try:
        click.echo("🏢 Supported KYC Providers:")
        kyc_providers = [
            ("chainalysis", "Blockchain-focused KYC/AML"),
            ("sumsub", "Multi-channel verification"),
            ("onfido", "Document verification"),
            ("jumio", "Identity verification"),
            ("veriff", "Video-based verification")
        ]
        
        for provider, description in kyc_providers:
            click.echo(f"  • {provider.title()}: {description}")
        
        click.echo(f"\n🔍 AML Screening:")
        click.echo(f"  • Chainalysis AML: Blockchain transaction analysis")
        click.echo(f"  • Sanctions List Screening: OFAC, UN, EU lists")
        click.echo(f"  • PEP Screening: Politically Exposed Persons")
        click.echo(f"  • Adverse Media: News and public records")
        
        click.echo(f"\n📝 Usage Examples:")
        click.echo(f"  aitbc compliance kyc-submit --user-id user123 --provider chainalysis --first-name John --last-name Doe --email john@example.com")
        click.echo(f"  aitbc compliance aml-screen --user-id user123 --first-name John --last-name Doe --email john@example.com")
        click.echo(f"  aitbc compliance full-check --user-id user123 --first-name John --last-name Doe --email john@example.com")
        
    except Exception as e:
        click.echo(f"❌ Error listing providers: {e}", err=True)

if __name__ == "__main__":
    compliance()
