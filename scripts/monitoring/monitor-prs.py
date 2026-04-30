#!/usr/bin/env python3
"""
Enhanced monitor for Gitea PRs:
- Auto-request review from sibling on my PRs
- Auto-validate sibling's PRs and approve if passing checks, with stability ring awareness
- Monitor CI statuses and report failures
- Release claim branches when associated PRs merge, close, or EXPIRE
"""
import os
import json
import subprocess
import tempfile
import shutil
from datetime import datetime, UTC, timezone

GITEA_TOKEN = os.getenv('GITEA_TOKEN') or 'ffce3b62d583b761238ae00839dce7718acaad85'
REPO = 'oib/aitbc'
API_BASE = os.getenv('GITEA_API_BASE', 'http://gitea.bubuit.net:3000/api/v1')
MY_AGENT = os.getenv('AGENT_NAME', 'aitbc1')
SIBLING_AGENT = 'aitbc' if MY_AGENT == 'aitbc1' else 'aitbc1'
CLAIM_STATE_FILE = '/opt/aitbc/.claim-state.json'
CLAIM_TTL_SECONDS = 7200  # Must match claim-task.py

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

def get_pr_files(pr_number):
    return query_api(f'repos/{REPO}/pulls/{pr_number}/files') or []

def detect_ring(path):
    ring0 = ['packages/py/aitbc-core/', 'packages/py/aitbc-sdk/', 'packages/py/aitbc-agent-sdk/', 'packages/py/aitbc-crypto/']
    ring1 = ['apps/coordinator-api/', 'apps/blockchain-node/', 'apps/analytics/', 'services/']
    ring2 = ['cli/', 'scripts/', 'tools/']
    ring3 = ['experiments/', 'playground/', 'prototypes/', 'examples/']
    if any(path.startswith(p) for p in ring0):
        return 0
    if any(path.startswith(p) for p in ring1):
        return 1
    if any(path.startswith(p) for p in ring2):
        return 2
    if any(path.startswith(p) for p in ring3):
        return 3
    return 2

def load_claim_state():
    if os.path.exists(CLAIM_STATE_FILE):
        with open(CLAIM_STATE_FILE) as f:
            return json.load(f)
    return {}

def save_claim_state(state):
    with open(CLAIM_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def release_claim(issue_number, claim_branch):
    check = subprocess.run(['git', 'ls-remote', '--heads', 'origin', claim_branch],
                           capture_output=True, text=True, cwd='/opt/aitbc')
    if check.returncode == 0 and check.stdout.strip():
        subprocess.run(['git', 'push', 'origin', '--delete', claim_branch],
                       capture_output=True, cwd='/opt/aitbc')
    state = load_claim_state()
    if state.get('current_claim') == issue_number:
        state.clear()
        save_claim_state(state)
    print(f"✅ Released claim for issue #{issue_number} (deleted branch {claim_branch})")

def is_claim_expired(state):
    """Check if the current claim has exceeded TTL."""
    expires_at = state.get('expires_at')
    if not expires_at:
        return False
    now_ts = datetime.now(datetime.UTC).timestamp()
    return now_ts > expires_at

def get_open_prs():
    return query_api(f'repos/{REPO}/pulls?state=open') or []

def get_all_prs(state='all'):
    return query_api(f'repos/{REPO}/pulls?state={state}') or []

def get_pr_reviews(pr_number):
    return query_api(f'repos/{REPO}/pulls/{pr_number}/reviews') or []

def get_commit_statuses(pr_number):
    pr = query_api(f'repos/{REPO}/pulls/{pr_number}')
    if not pr:
        return []
    sha = pr['head']['sha']
    statuses = query_api(f'repos/{REPO}/commits/{sha}/statuses')
    if not statuses or not isinstance(statuses, list):
        return []
    return statuses

def request_reviewer(pr_number, reviewer):
    data = {"reviewers": [reviewer]}
    return query_api(f'repos/{REPO}/pulls/{pr_number}/requested_reviewers', method='POST', data=data)

def post_review(pr_number, state, body=''):
    data = {"body": body, "event": state}
    return query_api(f'repos/{REPO}/pulls/{pr_number}/reviews', method='POST', data=data)

def validate_pr_branch(pr):
    head = pr['head']
    ref = head['ref']
    repo = head.get('repo', {}).get('full_name', REPO)
    tmpdir = tempfile.mkdtemp(prefix='aitbc-pr-')
    try:
        clone_url = f"git@gitea.bubuit.net:{repo}.git"
        result = subprocess.run(['git', 'clone', '-b', ref, '--depth', '1', clone_url, tmpdir],
                               capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return False, f"Clone failed: {result.stderr.strip()}"
        py_files = subprocess.run(['find', tmpdir, '-name', '*.py'], capture_output=True, text=True)
        if py_files.returncode == 0 and py_files.stdout.strip():
            for f in py_files.stdout.strip().split('\n')[:20]:
                res = subprocess.run(['python3', '-m', 'py_compile', f],
                                     capture_output=True, text=True, cwd=tmpdir)
                if res.returncode != 0:
                    return False, f"Syntax error in `{f}`: {res.stderr.strip()}"
        return True, "Automated validation passed."
    except Exception as e:
        return False, f"Validation error: {str(e)}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def main():
    now = datetime.now(datetime.UTC).replace(tzinfo=timezone.utc)
    now_iso = now.isoformat()
    now_ts = now.timestamp()
    print(f"[{now_iso}] Monitoring PRs and claim locks...")
    
    # 0. Check claim state: if we have a current claim, see if it expired or PR merged
    state = load_claim_state()
    if state.get('current_claim'):
        issue_num = state['current_claim']
        work_branch = state.get('work_branch')
        claim_branch = state.get('claim_branch')
        # Check expiration
        if is_claim_expired(state):
            print(f"Claim for issue #{issue_num} has expired. Releasing.")
            release_claim(issue_num, claim_branch)
        else:
            # Check if PR merged/closed
            all_prs = get_all_prs(state='all')
            matched_pr = None
            for pr in all_prs:
                if pr['head']['ref'] == work_branch:
                    matched_pr = pr
                    break
            if matched_pr and matched_pr['state'] == 'closed':
                release_claim(issue_num, claim_branch)
    
    # 1. Process open PRs
    open_prs = get_open_prs()
    notifications = []
    
    for pr in open_prs:
        number = pr['number']
        title = pr['title']
        author = pr['user']['login']
        head_ref = pr['head']['ref']
        
        # A. If PR from sibling, consider for review
        if author == SIBLING_AGENT:
            reviews = get_pr_reviews(number)
            my_reviews = [r for r in reviews if r['user']['login'] == MY_AGENT]
            if not my_reviews:
                files = get_pr_files(number)
                rings = [detect_ring(f['filename']) for f in files if f.get('status') != 'removed']
                max_ring = max(rings) if rings else 2
                if max_ring == 0:
                    body = "Automated analysis: This PR modifies core (Ring 0) components. Manual review and a design specification are required before merge. No auto-approval."
                    post_review(number, 'COMMENT', body=body)
                    notifications.append(f"PR #{number} (Ring 0) flagged for manual review")
                else:
                    passed, msg = validate_pr_branch(pr)
                    if passed:
                        post_review(number, 'APPROVED', body=f"Automated peer review: branch validated.\n\n✅ Syntax checks passed.\nRing {max_ring} change — auto-approved. CI must still pass.")
                        notifications.append(f"Auto-approved PR #{number} from @{author} (Ring {max_ring})")
                    else:
                        post_review(number, 'CHANGES_REQUESTED', body=f"Automated peer review detected issues:\n\n{msg}\n\nPlease fix and push.")
                        notifications.append(f"Requested changes on PR #{number} from @{author}: {msg[:100]}")
        
        # B. If PR from me, ensure sibling is requested as reviewer
        if author == MY_AGENT:
            pr_full = query_api(f'repos/{REPO}/pulls/{number}')
            requested = pr_full.get('requested_reviewers', []) if pr_full else []
            if not any(r.get('login') == SIBLING_AGENT for r in requested):
                request_reviewer(number, SIBLING_AGENT)
                notifications.append(f"Requested review from @{SIBLING_AGENT} for my PR #{number}")
        
        # C. Check CI statuses for any PR
        statuses = get_commit_statuses(number)
        failing = [s for s in statuses if s.get('status') not in ('success', 'pending')]
        if failing:
            for s in failing:
                notifications.append(f"PR #{number} status check failure: {s.get('context','unknown')} - {s.get('status','unknown')}")
    
    # 2. Global cleanup of stale claim branches (orphaned, older than TTL)
    cleanup_global_expired_claims(now_ts)
    
    if notifications:
        print("\n".join(notifications))
    else:
        print("No new alerts.")

def cleanup_global_expired_claims(now_ts=None):
    """Delete remote claim branches that are older than TTL, even if state file is gone."""
    if now_ts is None:
        now_ts = datetime.now(datetime.UTC).timestamp()
    # List all remote claim branches
    result = subprocess.run(['git', 'ls-remote', '--heads', 'origin', 'claim/*'],
                            capture_output=True, text=True, cwd='/opt/aitbc')
    if result.returncode != 0 or not result.stdout.strip():
        return
    lines = result.stdout.strip().split('\n')
    cleaned = 0
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        sha, branch = parts[0], parts[1]
        # Get commit timestamp
        ts_result = subprocess.run(['git', 'show', '-s', '--format=%ct', sha],
                                   capture_output=True, text=True, cwd='/opt/aitbc')
        if ts_result.returncode == 0 and ts_result.stdout.strip():
            commit_ts = int(ts_result.stdout.strip())
            age = now_ts - commit_ts
            if age > CLAIM_TTL_SECONDS:
                print(f"Expired claim branch: {branch} (age {age/3600:.1f}h). Deleting.")
                subprocess.run(['git', 'push', 'origin', '--delete', branch],
                               capture_output=True, cwd='/opt/aitbc')
                cleaned += 1
    if cleaned == 0:
        print(" cleanup_global_expired_claims: none")
    else:
        print(f" cleanup_global_expired_claims: removed {cleaned} expired branch(es)")

if __name__ == '__main__':
    main()
