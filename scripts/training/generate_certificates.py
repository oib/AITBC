#!/usr/bin/env python3
"""
Certificate and Badge Generator for AITBC Training

Generates:
1. Markdown badges (shields.io style) for completed stages
2. HTML certificates with proper formatting
3. Summary certificate for completing all stages
"""

import json
from datetime import UTC, datetime
from pathlib import Path

CERT_DIR = Path(__file__).parent / ".training_state" / "certificates"
BADGE_DIR = Path(__file__).parent / ".training_state" / "badges"
HTML_DIR = Path(__file__).parent / ".training_state" / "html_certificates"


def ensure_dirs():
    """Ensure output directories exist."""
    BADGE_DIR.mkdir(parents=True, exist_ok=True)
    HTML_DIR.mkdir(parents=True, exist_ok=True)


def load_certificate(stage_num: int) -> dict:
    """Load certificate JSON for a stage."""
    cert_file = CERT_DIR / f"stage{stage_num}_certificate.json"
    if not cert_file.exists():
        return None
    with open(cert_file) as f:
        return json.load(f)


def generate_markdown_badge(stage_num: int, cert_data: dict) -> str:
    """Generate shields.io markdown badge for a stage."""
    badge_label = f"Stage {stage_num}"
    badge_message = "Completed"
    badge_color = "brightgreen"

    # URL encode spaces
    badge_url = f"https://img.shields.io/badge/{badge_label.replace(' ', '%20')}-{badge_message.replace(' ', '%20')}-{badge_color}?style=flat-square"
    markdown = f"[![Stage {stage_num}]({badge_url})]({CERT_DIR}/stage{stage_num}_certificate.json)"
    return markdown


def generate_html_certificate(stage_num: int, cert_data: dict) -> str:
    """Generate HTML certificate for a stage."""
    stage_name = cert_data.get("stage_name", f"Stage {stage_num}")
    timestamp = cert_data.get("completion_timestamp", datetime.now(UTC).isoformat())
    wallet = cert_data.get("wallet_name", "Unknown")
    cert_id = cert_data.get("certificate_id", "Unknown")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Certificate - Stage {stage_num}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .certificate {{
            background: white;
            padding: 60px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 800px;
            text-align: center;
        }}
        .header {{
            font-size: 48px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 20px;
        }}
        .subtitle {{
            font-size: 24px;
            color: #666;
            margin-bottom: 40px;
        }}
        .stage-name {{
            font-size: 36px;
            font-weight: bold;
            color: #333;
            margin: 30px 0;
            padding: 20px;
            background: #f5f5f5;
            border-radius: 10px;
        }}
        .details {{
            text-align: left;
            margin: 30px 0;
            padding: 20px;
            background: #f9f9f9;
            border-radius: 10px;
        }}
        .detail-row {{
            margin: 10px 0;
            font-size: 16px;
        }}
        .detail-label {{
            font-weight: bold;
            color: #667eea;
        }}
        .footer {{
            margin-top: 40px;
            font-size: 14px;
            color: #999;
        }}
        .badge {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            margin: 5px;
        }}
    </style>
</head>
<body>
    <div class="certificate">
        <div class="header">🏆 Certificate of Completion</div>
        <div class="subtitle">AITBC Agent Training Program</div>

        <div class="stage-name">Stage {stage_num}: {stage_name}</div>

        <div class="details">
            <div class="detail-row">
                <span class="detail-label">Certificate ID:</span> {cert_id}
            </div>
            <div class="detail-row">
                <span class="detail-label">Completed:</span> {timestamp}
            </div>
            <div class="detail-row">
                <span class="detail-label">Wallet:</span> {wallet}
            </div>
            <div class="detail-row">
                <span class="detail-label">Training Program:</span> hermes AITBC Mastery Training
            </div>
        </div>

        <div>
            <span class="badge">✓ Stage Completed</span>
            <span class="badge">✓ Hands-On Training</span>
            <span class="badge">✓ Blockchain Verified</span>
        </div>

        <div class="footer">
            Generated on {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}
        </div>
    </div>
</body>
</html>"""
    return html


def generate_summary_certificate(completed_stages: list) -> str:
    """Generate summary HTML certificate for completing all stages."""
    stages_html = ""
    for stage in sorted(completed_stages):
        cert = load_certificate(stage)
        stage_name = cert.get("stage_name", f"Stage {stage}") if cert else f"Stage {stage}"
        stages_html += f'            <div class="stage-badge">Stage {stage}: {stage_name}</div>\n'

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Mastery Certificate - AITBC Training</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .certificate {{
            background: white;
            padding: 60px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 900px;
            text-align: center;
        }}
        .header {{
            font-size: 56px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 20px;
        }}
        .subtitle {{
            font-size: 28px;
            color: #666;
            margin-bottom: 20px;
        }}
        .achievement {{
            font-size: 24px;
            color: #333;
            margin: 30px 0;
            padding: 20px;
            background: linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%);
            border-radius: 10px;
            border: 3px solid #667eea;
        }}
        .stages {{
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
            margin: 30px 0;
        }}
        .stage-badge {{
            background: #667eea;
            color: white;
            padding: 10px 20px;
            border-radius: 25px;
            font-size: 16px;
            font-weight: bold;
        }}
        .footer {{
            margin-top: 40px;
            font-size: 14px;
            color: #999;
        }}
    </style>
</head>
<body>
    <div class="certificate">
        <div class="header">🎓 Mastery Certificate</div>
        <div class="subtitle">AITBC Agent Training Program</div>

        <div class="achievement">
            Congratulations! You have completed all {len(completed_stages)} training stages
        </div>

        <div class="stages">
{stages_html}
        </div>

        <div class="footer">
            Generated on {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}<br>
            Total Stages Completed: {len(completed_stages)} / 11
        </div>
    </div>
</body>
</html>"""
    return html


def generate_markdown_summary(completed_stages: list) -> str:
    """Generate Markdown summary with all badges."""
    markdown = "# AITBC Training Certificates\n\n"
    markdown += f"Completed {len(completed_stages)} / 11 stages\n\n"

    markdown += "## Badges\n\n"
    for stage in sorted(completed_stages):
        cert = load_certificate(stage)
        if cert:
            badge = generate_markdown_badge(stage, cert)
            markdown += f"{badge} "

    markdown += "\n\n## Stages Completed\n\n"
    for stage in sorted(completed_stages):
        cert = load_certificate(stage)
        if cert:
            stage_name = cert.get("stage_name", f"Stage {stage}")
            timestamp = cert.get("completion_timestamp", "Unknown")
            markdown += f"- **Stage {stage}: {stage_name}** - Completed {timestamp}\n"

    return markdown


def main():
    """Main function."""
    ensure_dirs()

    # Find all completed stages
    completed_stages = []
    for i in range(11):  # Stages 0-10
        cert = load_certificate(i)
        if cert:
            completed_stages.append(i)

            # Generate markdown badge
            badge_md = generate_markdown_badge(i, cert)
            badge_file = BADGE_DIR / f"stage{i}_badge.md"
            with open(badge_file, "w") as f:
                f.write(badge_md)

            # Generate HTML certificate
            html = generate_html_certificate(i, cert)
            html_file = HTML_DIR / f"stage{i}_certificate.html"
            with open(html_file, "w") as f:
                f.write(html)

            print(f"✓ Generated badge and HTML certificate for Stage {i}")

    # Generate summary certificate if all stages completed
    if len(completed_stages) == 11:
        summary_html = generate_summary_certificate(completed_stages)
        summary_file = HTML_DIR / "mastery_certificate.html"
        with open(summary_file, "w") as f:
            f.write(summary_html)
        print(f"✓ Generated Mastery Certificate: {summary_file}")

    # Generate Markdown summary
    if completed_stages:
        md_summary = generate_markdown_summary(completed_stages)
        summary_md_file = BADGE_DIR / "training_summary.md"
        with open(summary_md_file, "w") as f:
            f.write(md_summary)
        print(f"✓ Generated Markdown summary: {summary_md_file}")

    print(f"\nTotal completed stages: {len(completed_stages)} / 11")
    print(f"Badges directory: {BADGE_DIR}")
    print(f"HTML certificates: {HTML_DIR}")


if __name__ == "__main__":
    main()
