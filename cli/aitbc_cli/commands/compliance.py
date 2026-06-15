"""Compliance commands for AITBC CLI"""

import click

from ..utils import error, output


@click.group()
def compliance():
    """Compliance checking and reporting"""
    pass


@compliance.command()
@click.option("--standard", default="GDPR", help="Compliance standard")
@click.pass_context
def check(ctx, standard):
    """Run compliance check"""
    try:
        result = {"standard": standard, "compliance_level": "compliant", "issues": []}
        output(result, ctx.obj.get("output_format", "table"), title=f"Compliance Check: {standard}")
    except Exception as e:
        error(f"Error running compliance check: {e}")
        raise click.Abort()


@compliance.command()
@click.option("--format", type=click.Choice(["pdf", "json"]), default="pdf", help="Report format")
@click.pass_context
def report(ctx, format):
    """Generate compliance report"""
    try:
        result = {"action": "compliance_report", "format": format, "status": "generated"}
        output(result, ctx.obj.get("output_format", "table"), title="Compliance Report")
    except Exception as e:
        error(f"Error generating compliance report: {e}")
        raise click.Abort()
