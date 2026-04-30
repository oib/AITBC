#!/usr/bin/env python3
"""
QA Cycle: Run tests, exercise scenarios, find bugs, perform code reviews.
Runs periodically to ensure repository health and discover regressions.
"""
import os
import subprocess
import json
import sys
import shutil
import time
import random
from datetime import datetime, UTC
from pathlib import Path

# Jitter: random delay up to 15 minutes (900 seconds)
time.sleep(random.randint(0, 900))

REPO_DIR = '/opt/aitbc'
LOG_FILE = '/opt/aitbc/qa-cycle.log'
TOKEN_FILE = '/opt/aitbc/.gitea_token.sh'

def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            for line in f:
                if line.strip().startswith('GITEA_TOKEN='):
                    return line.strip().split('=', 1)[1].strip()
    return os.getenv('GITEA_TOKEN', '')

GITEA_TOKEN = get_token()
API_BASE = os.getenv('GITEA_API_BASE', 'http://gitea.bubuit.net:3000/api/v1')
REPO = 'oib/aitbc'

def log(msg):
    now = datetime.now(datetime.UTC).isoformat() + 'Z'
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{now}] {msg}\n")
    print(msg)

def run_cmd(cmd, cwd=REPO_DIR, timeout=300):
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -2, "", str(e)

def fetch_latest_main():
    log("Fetching latest main...")
    rc, out, err = run_cmd("git fetch origin main")
    if rc != 0:
        log(f"Fetch failed: {err}")
        return False
    rc, out, err = run_cmd("git checkout main")
    if rc != 0:
        log(f"Checkout main failed: {err}")
        return False
    rc, out, err = run_cmd("git reset --hard origin/main")
    if rc != 0:
        log(f"Reset to origin/main failed: {err}")
        return False
    log("Main updated to latest.")
    return True

def run_tests():
    log("Running test suites...")
    results = []
    for pkg in ['aitbc-core', 'aitbc-sdk', 'aitbc-crypto']:
        testdir = f"packages/py/{pkg}/tests"
        if not os.path.exists(os.path.join(REPO_DIR, testdir)):
            continue
        log(f"Testing {pkg}...")
        rc, out, err = run_cmd(f"python3 -m pytest {testdir} -q", timeout=120)
        if rc == 0:
            log(f"✅ {pkg} tests passed.")
        else:
            log(f"❌ {pkg} tests failed (rc={rc}). Output: {out}\nError: {err}")
        results.append((pkg, rc == 0))
    return results

def run_lint():
    log("Running linters (flake8 if available)...")
    if shutil.which('flake8'):
        rc, out, err = run_cmd("flake8 packages/py/ --count --select=E9,F63,F7,F82 --show-source --statistics", timeout=60)
        if rc == 0:
            log("✅ No critical lint errors.")
        else:
            log(f"❌ Lint errors: {out}")
    else:
        log("flake8 not installed; skipping lint.")

def query_api(path, method='GET', data=None):
    import urllib.request
    import urllib.error
    url = f"{API_BASE}/{path}"
    headers = {'Authorization': f'token {GITEA_TOKEN}'}
    if data:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except Exception as e:
        log(f"API error {path}: {e}")
        return None

def review_my_open_prs():
    log("Checking my open PRs for missing reviews...")
    my_prs = query_api(f'repos/{REPO}/pulls?state=open&author={MY_AGENT}') or []
    for pr in my_prs:
        num = pr['number']
        title = pr['title']
        requested = pr.get('requested_reviewers', [])
        if not any(r.get('login') == SIBLING_AGENT for r in requested):
            log(f"PR #{num} '{title}' missing sibling review. Requesting...")
            query_api(f'repos/{REPO}/pulls/{num}/requested_reviewers', method='POST', data={'reviewers': [SIBLING_AGENT]})
        else:
            log(f"PR #{num} already has sibling review requested.")

def synthesize_status():
    log("Collecting repository status...")
    issues = query_api(f'repos/{REPO}/issues?state=open') or []
    prs = query_api(f'repos/{REPO}/pulls?state=open') or []
    log(f"Open issues: {len(issues)}, open PRs: {len(prs)}")
    unassigned_issues = [i for i in issues if not i.get('assignees') and 'pull_request' not in i]
    log(f"Unassigned issues: {len(unassigned_issues)}")
    if unassigned_issues:
        for i in unassigned_issues[:3]:
            log(f" - #{i['number']} {i['title'][:50]}")
    # Check CI for open PRs
    for pr in prs:
        num = pr['number']
        statuses = query_api(f'repos/{REPO}/commits/{pr["head"]["sha"]}/statuses') or []
        failing = [s for s in statuses if s.get('status') not in ('success', 'pending')]
        if failing:
            log(f"PR #{num} has failing checks: {', '.join(s.get('context','?') for s in failing)}")

def main():
    now = datetime.now(datetime.UTC).isoformat() + 'Z'
    log(f"\n=== QA Cycle start: {now} ===")
    if not GITEA_TOKEN:
        log("GITEA_TOKEN not set; aborting.")
        sys.exit(1)
    global MY_AGENT, SIBLING_AGENT
    MY_AGENT = os.getenv('AGENT_NAME', 'aitbc1')
    SIBLING_AGENT = 'aitbc' if MY_AGENT == 'aitbc1' else 'aitbc1'
    if not fetch_latest_main():
        log("Aborting due to fetch failure.")
        return
    run_tests()
    run_lint()
    review_my_open_prs()
    synthesize_status()
    log(f"=== QA Cycle complete ===")

if __name__ == '__main__':
    main()
