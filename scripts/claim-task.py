#!/usr/bin/env python3
"""
Task Claim System for AITBC agents.
Uses Git branch atomic creation as a distributed lock to prevent duplicate work.
"""
import os
import json
import subprocess
from datetime import datetime

REPO_DIR = '/opt/aitbc'
STATE_FILE = '/opt/aitbc/.claim-state.json'
GITEA_TOKEN = os.getenv('GITEA_TOKEN') or 'ffce3b62d583b761238ae00839dce7718acaad85'
API_BASE = os.getenv('GITEA_API_BASE', 'http://gitea.bubuit.net:3000/api/v1')
MY_AGENT = os.getenv('AGENT_NAME', 'aitbc1')
ISSUE_LABELS = ['security', 'bug', 'feature', 'refactor', 'task']  # priority order
BONUS_LABELS = ['good-first-task-for-agent']
AVOID_LABELS = ['needs-design', 'blocked', 'needs-reproduction']

def query_api(path, method='GET', data=None):
    url = f"{API_BASE}/{path}"
    cmd = ['curl', '-s', '-H', f'Authorization: token {GITEA_TOKEN}', '-X', method]
    if data:
        cmd += ['-d', json.dumps(data), '-H', 'Content-Type: application/json']
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'current_claim': None, 'claimed_at': None, 'work_branch': None}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_open_unassigned_issues():
    """Fetch open issues (excluding PRs) with no assignee, sorted by utility."""
    all_items = query_api('repos/oib/aitbc/issues?state=open') or []
    # Exclude pull requests
    issues = [i for i in all_items if 'pull_request' not in i]
    unassigned = [i for i in issues if not i.get('assignees')]
    
    label_priority = {lbl: idx for idx, lbl in enumerate(ISSUE_LABELS)}
    avoid_set = set(AVOID_LABELS)
    bonus_set = set(BONUS_LABELS)
    
    def utility(issue):
        labels = [lbl['name'] for lbl in issue.get('labels', [])]
        if any(lbl in avoid_set for lbl in labels):
            return -1
        base = 1.0
        for lbl in labels:
            if lbl in label_priority:
                base += (len(ISSUE_LABELS) - label_priority[lbl]) * 0.2
                break
        else:
            base = 0.5
        if any(lbl in bonus_set for lbl in labels):
            base += 0.2
        if issue.get('comments', 0) > 10:
            base *= 0.8
        return base
    
    unassigned.sort(key=utility, reverse=True)
    return unassigned

def git_current_branch():
    result = subprocess.run(['git', 'branch', '--show-current'], capture_output=True, text=True, cwd=REPO_DIR)
    return result.stdout.strip()

def ensure_main_uptodate():
    subprocess.run(['git', 'checkout', 'main'], capture_output=True, cwd=REPO_DIR)
    subprocess.run(['git', 'pull', 'origin', 'main'], capture_output=True, cwd=REPO_DIR)

def claim_issue(issue_number):
    """Atomically create a claim branch on the remote."""
    ensure_main_uptodate()
    branch_name = f'claim/{issue_number}'
    subprocess.run(['git', 'branch', '-f', branch_name, 'origin/main'], capture_output=True, cwd=REPO_DIR)
    result = subprocess.run(['git', 'push', 'origin', branch_name], capture_output=True, text=True, cwd=REPO_DIR)
    return result.returncode == 0

def assign_issue(issue_number, assignee):
    data = {"assignee": assignee}
    return query_api(f'repos/oib/aitbc/issues/{issue_number}/assignees', method='POST', data=data)

def add_comment(issue_number, body):
    data = {"body": body}
    return query_api(f'repos/oib/aitbc/issues/{issue_number}/comments', method='POST', data=data)

def create_work_branch(issue_number, title):
    """Create the actual work branch from main."""
    ensure_main_uptodate()
    slug = ''.join(c if c.isalnum() else '-' for c in title.lower())[:40].strip('-')
    branch_name = f'{MY_AGENT}/{issue_number}-{slug}'
    subprocess.run(['git', 'checkout', '-b', branch_name, 'main'], check=True, cwd=REPO_DIR)
    return branch_name

def main():
    now = datetime.utcnow().isoformat() + 'Z'
    print(f"[{now}] Claim task cycle starting...")
    
    state = load_state()
    current_claim = state.get('current_claim')
    
    if current_claim:
        print(f"Already working on issue #{current_claim} (branch {state.get('work_branch')})")
        # Optional: could check if that PR has been merged/closed and release claim here
        return
    
    issues = get_open_unassigned_issues()
    if not issues:
        print("No unassigned issues available.")
        return
    
    for issue in issues:
        num = issue['number']
        title = issue['title']
        labels = [lbl['name'] for lbl in issue.get('labels', [])]
        print(f"Attempting to claim issue #{num}: {title} (labels={labels})")
        if claim_issue(num):
            assign_issue(num, MY_AGENT)
            work_branch = create_work_branch(num, title)
            state.update({
                'current_claim': num,
                'claim_branch': f'claim/{num}',
                'work_branch': work_branch,
                'claimed_at': datetime.utcnow().isoformat() + 'Z',
                'issue_title': title,
                'labels': labels
            })
            save_state(state)
            print(f"✅ Claimed issue #{num}. Work branch: {work_branch}")
            add_comment(num, f"Agent `{MY_AGENT}` claiming this task. (automated)")
            return
        else:
            print(f"Claim failed for #{num} (branch exists). Trying next...")
    
    print("Could not claim any issue; all taken or unavailable.")

if __name__ == '__main__':
    main()
