#!/usr/bin/env python3
"""
Create a structured issue via Gitea API.
Requires GITEA_TOKEN in environment or /opt/aitbc/.gitea_token.sh.
"""
import os, sys, json, subprocess

def get_token():
    token_file = '/opt/aitbc/.gitea_token.sh'
    if os.path.exists(token_file):
        with open(token_file) as f:
            for line in f:
                if line.strip().startswith('GITEA_TOKEN='):
                    return line.strip().split('=', 1)[1].strip()
    return os.getenv('GITEA_TOKEN', '')

GITEA_TOKEN = get_token()
API_BASE = os.getenv('GITEA_API_BASE', 'http://gitea.bubuit.net:3000/api/v1')
REPO = 'oib/aitbc'

def create_issue(title, context, expected, files, implementation, difficulty, priority, labels, assignee=None):
    body = f"""## Task
{title}

## Context
{context}

## Expected Result
{expected}

## Files Likely Affected
{files}

## Suggested Implementation
{implementation}

## Difficulty
- [{'x' if difficulty == d else ' '}] {d}
{'' if difficulty != 'medium' else ''}

## Priority
- [{'x' if priority == p else ' '}] {p}

## Labels
{', '.join([f'[{l}]' for l in labels])}
"""
    data = {
        "title": title,
        "body": body,
        "labels": labels
    }
    if assignee:
        data["assignee"] = assignee
    url = f"{API_BASE}/repos/{REPO}/issues"
    cmd = ['curl', '-s', '-H', f'Authorization: token {GITEA_TOKEN}', '-X', 'POST',
           '-H', 'Content-Type: application/json', '-d', json.dumps(data), url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("API error:", result.stderr)
        sys.exit(1)
    try:
        resp = json.loads(result.stdout)
        print(f"Created issue #{resp['number']}: {resp['html_url']}")
    except Exception as e:
        print("Failed to parse response:", e, result.stdout)

if __name__ == "__main__":
    # Example usage; in practice, agents will fill these fields.
    create_issue(
        title="Add retry logic to Matrix event listener",
        context="Spurious network failures cause agent disconnects.",
        expected="Listener automatically reconnects and continues processing events.",
        files="apps/matrix-listener/src/event_handler.py",
        implementation="Wrap event loop in retry decorator with exponential backoff.",
        difficulty="medium",
        priority="high",
        labels=["bug", "infra"],
        assignee="aitbc1"
    )
