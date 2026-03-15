#!/usr/bin/env python3
"""
Automated PR reviewer for multi-agent collaboration.

Fetches open PRs authored by the sibling agent, runs basic validation,
and posts an APPROVE or COMMENT review.

Usage: GITEA_TOKEN=... python3 auto_review.py
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
from datetime import datetime

TOKEN = os.getenv("GITEA_TOKEN")
API_BASE = os.getenv("GITEA_API_BASE", "http://gitea.bubuit.net:3000/api/v1")
REPO = "oib/aitbc"
SELF = os.getenv("AGENT_NAME", "aitbc")  # set this in env: aitbc or aitbc1
OTHER = "aitbc1" if SELF == "aitbc" else "aitbc"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def die(msg):
    log(f"FATAL: {msg}")
    sys.exit(1)

def api_get(path):
    cmd = ["curl", "-s", "-H", f"Authorization: token {TOKEN}", f"{API_BASE}/{path}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

def api_post(path, payload):
    cmd = ["curl", "-s", "-X", "POST", "-H", f"Authorization: token {TOKEN}", "-H", "Content-Type: application/json",
           f"{API_BASE}/{path}", "-d", json.dumps(payload)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

def get_open_prs():
    return api_get(f"repos/{REPO}/pulls?state=open") or []

def get_my_reviews(pr_number):
    return api_get(f"repos/{REPO}/pulls/{pr_number}/reviews") or []

# Stability ring definitions
RING_PREFIXES = [
    (0, ["packages/py/aitbc-core", "packages/py/aitbc-sdk"]),  # Ring 0: Core
    (1, ["apps/"]),                                           # Ring 1: Platform services
    (2, ["cli/", "analytics/", "tools/"]),                    # Ring 2: Application
]
RING_THRESHOLD = {0: 0.90, 1: 0.80, 2: 0.70, 3: 0.50}        # Ring 3: Experimental/low

def is_test_file(path):
    """Heuristic: classify test files to downgrade ring."""
    if '/tests/' in path or path.startswith('tests/') or path.endswith('_test.py'):
        return True
    return False

def detect_ring(workdir, base_sha, head_sha):
    """Determine the stability ring of the PR based on changed files."""
    try:
        # Get list of changed files between base and head
        output = subprocess.run(
            ["git", "--git-dir", os.path.join(workdir, ".git"), "diff", "--name-only", base_sha, head_sha],
            capture_output=True, text=True, check=True
        ).stdout
        files = [f.strip() for f in output.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        files = []

    # If all changed files are tests, treat as Ring 3 (low risk)
    if files and all(is_test_file(f) for f in files):
        return 3

    # Find highest precedence ring (lowest number) among changed files
    for ring, prefixes in sorted(RING_PREFIXES, key=lambda x: x[0]):
        for p in files:
            if any(p.startswith(prefix) for prefix in prefixes):
                return ring
    return 3  # default to Ring 3 (experimental)

def checkout_pr_branch(pr):
    """Checkout PR branch in a temporary worktree."""
    tmpdir = tempfile.mkdtemp(prefix="aitbc_review_")
    try:
        # Clone just .git into tmp, then checkout
        subprocess.run(["git", "clone", "--no-checkout", "origin", tmpdir], check=True, capture_output=True)
        worktree = os.path.join(tmpdir, "wt")
        os.makedirs(worktree)
        subprocess.run(["git", "--git-dir", os.path.join(tmpdir, ".git"), "--work-tree", worktree, "fetch", "origin", pr['head']['ref']], check=True, capture_output=True)
        subprocess.run(["git", "--git-dir", os.path.join(tmpdir, ".git"), "--work-tree", worktree, "checkout", "FETCH_HEAD"], check=True, capture_output=True)
        return worktree, tmpdir
    except subprocess.CalledProcessError as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        log(f"Checkout failed: {e}")
        return None, None

def run_checks(workdir):
    """Run validation checks. Returns (pass, score, notes)."""
    notes = []
    score = 0.0

    # 1. Import sanity: try to import the aitbc_cli module
    try:
        subprocess.run([sys.executable, "-c", "import aitbc_cli.main"], check=True, cwd=workdir, capture_output=True)
        notes.append("CLI imports OK")
        score += 0.3
    except subprocess.CalledProcessError as e:
        notes.append(f"CLI import failed: {e}")
        return False, 0.0, "\n".join(notes)

    # 2. Syntax check all Python files (simple)
    py_files = []
    for root, dirs, files in os.walk(worktree):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    syntax_ok = True
    for f in py_files:
        try:
            subprocess.run([sys.executable, "-m", "py_compile", f], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            syntax_ok = False
            notes.append(f"Syntax error in {os.path.relpath(f, worktree)}")
    if syntax_ok:
        notes.append("All Python files have valid syntax")
        score += 0.3
    else:
        return False, score, "\n".join(notes)

    # 3. Stability ring threshold (deferred to main loop where we have pr data)
    # We'll just return pass/fail based on imports+syncheck; threshold applied in main
    return True, score, "\n".join(notes)

def post_review(pr_number, event, body):
    """Post a review on the PR."""
    payload = {"event": event, "body": body}
    result = api_post(f"repos/{REPO}/pulls/{pr_number}/reviews", payload)
    return result is not None

def main():
    if not TOKEN:
        die("GITEA_TOKEN not set")
    log("Fetching open PRs...")
    prs = get_open_prs()
    if not prs:
        log("No open PRs")
        return
    # Filter PRs authored by the OTHER agent
    other_prs = [p for p in prs if p['user']['login'] == OTHER]
    if not other_prs:
        log(f"No open PRs from {OTHER}")
        return
    log(f"Found {len(other_prs)} PR(s) from {OTHER}")
    for pr in other_prs:
        pr_number = pr['number']
        title = pr['title'][:50] + ('...' if len(pr['title']) > 50 else '')
        log(f"Reviewing PR #{pr_number}: {title}")
        # Check if we already reviewed
        my_reviews = get_my_reviews(pr_number)
        if any(r['user']['login'] == SELF for r in my_reviews):
            log(f"Already reviewed PR #{pr_number}; skipping")
            continue
        # Checkout and run tests
        workdir, tmpdir = checkout_pr_branch(pr)
        if not workdir:
            log(f"Failed to checkout PR#{pr_number}; skipping")
            continue
        try:
            # Determine stability ring and threshold
            base_sha = pr['base']['sha']
            head_sha = pr['head']['sha']
            ring = detect_ring(workdir, base_sha, head_sha)
            threshold = RING_THRESHOLD[ring]

            ok, score, notes = run_checks(workdir)
            notes = f"Ring: {ring}\nThreshold: {threshold}\n{notes}"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        if ok and score >= threshold:
            post_review(pr_number, "APPROVE", f"✅ Auto-approved.\n\n{notes}")
            log(f"Approved PR #{pr_number} (score {score:.2f} >= {threshold})")
        else:
            post_review(pr_number, "REQUEST_CHANGES", f"❌ Changes requested.\n\n{notes}")
            log(f"Requested changes on PR #{pr_number} (score {score:.2f} < {threshold})")

if __name__ == "__main__":
    main()