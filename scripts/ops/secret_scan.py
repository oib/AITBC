#!/usr/bin/env python3
"""Repo secret-pattern scan (SEC-10).

Emits METADATA ONLY — scope, commit, path, line, pattern class, triage
verdict — never the matched text, so it is safe to run in CI/pre-push.

Usage:
    secret_scan.py [--tree] [--history] [--repo PATH] [--fail-on-real]

    --tree        scan the working tree at HEAD (default when no mode given)
    --history     scan added lines across `git log -p --all` (slow)
    --repo PATH   repository root (default: cwd)
    --fail-on-real  exit 1 if any row triages as REAL?

Triage verdicts: REAL? (needs human look), placeholder, test-fixture,
test-fixture? (test path but suspicious shape), public-by-design?,
name-only (file-name heuristic), informational size notes.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterator

PATTERNS: list[tuple[str, str]] = [
    ("pem-privkey", r"-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED |DSA |PGP )?PRIVATE KEY( BLOCK)?-----"),
    ("age-secret", r"AGE-SECRET-KEY-[A-Z0-9]{50,}"),
    (
        "hex64-keyname",
        r"(?i)(private_?key|secret|seed|mnemonic|signing_?key|api_?key|access_?key|wallet_?key|master_?key)[\"' _-]*[:=][\"' ]*(0x)?[0-9a-fA-F]{64}\b",
    ),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ("bearer-auth", r"(?i)bearer [A-Za-z0-9._~+/-]{20,}"),
    (
        "password-assign",
        r"(?i)\b(password|passwd|pass_phrase|passphrase|db_password|secret)\b[\"' _-]*[:=][\"' ]*[^\s\"']{6,}",
    ),
    ("cred-url", r"[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:@'\"]+:[^/\s@'\"]+@"),
    ("aws-akid", r"\bAKIA[0-9A-Z]{16}\b"),
    ("gh-token", r"\b(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b"),
    ("gitea-token", r"(?i)gitea.{0,30}\b[a-f0-9]{40}\b|\b[a-f0-9]{40}\b.{0,30}gitea"),
    ("slack-token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ("webhook-url", r"(?i)(ntfy\.sh|hooks\.slack\.com|discord(app)?\.com/api/webhooks|webhook)[^/\s\"']*/[^\s\"']+"),
    ("keystore-json", r"ciphertext.*kdfparams|kdfparams.*ciphertext"),
    ("openssh-priv", r"openssh-key-v1"),
    ("mnemonic-line", r"^\s*['\"]?(?:[a-z]{3,8} ){11,23}[a-z]{3,8}\s*['\"]?\s*$"),
]
VAL_RES = [(c, re.compile(p)) for c, p in PATTERNS]

ERE_LIST = [
    "-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED |DSA |PGP )?PRIVATE KEY( BLOCK)?-----",
    "AGE-SECRET-KEY-[A-Z0-9]{50,}",
    "eyJ[A-Za-z0-9_-]{10,}[.][A-Za-z0-9_-]{10,}[.][A-Za-z0-9_-]{10,}",
    "(password|passwd|passphrase|secret)[\"' _-]*[:=][\"' ]*[^ \"']{6,}",
    "[a-zA-Z][a-zA-Z0-9+.-]*://[^/ :@'\"]+:[^/ @'\"]+@",
    "AKIA[0-9A-Z]{16}",
    "(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}",
    "xox[baprs]-[A-Za-z0-9-]{10,}",
    "openssh-key-v1",
    "ciphertext.*kdfparams|kdfparams.*ciphertext",
    "ntfy[.]sh|hooks[.]slack[.]com|discord(app)?[.]com/api/webhooks",
    "(private_?key|secret|seed|mnemonic|signing_?key|api_?key|access_?key|wallet_?key|master_?key)[\"' _-]*[:=][\"' ]*(0x)?[0-9a-fA-F]{64}",
    "bearer [A-Za-z0-9._~+/-]{20,}",
]

PLACEHOLDER = re.compile(
    r"(?i)(changeme|change[-_ ]?me|example|sample|placeholder|your[_-]|dummy|fake|"
    r"xxxx|<[^>]*>|\$\{|localhost|127\.0\.0\.1|todo|fixme|test[_-]?key|notakey|"
    r"deadbeef|aaaa|000000|111111)"
)
TESTPATH = re.compile(r"(?i)(test|fixture|conftest|example|sample|mock|docs/|\.md$|readme|changelog)")
ZEROES = re.compile(r"\b(0x)?(0{20,}|f{20,}|1{20,}|a{20,}|deadbeef[0-9a-f]*)\b", re.I)
PUBNAME = re.compile(
    r"(?i)(public_?key|pubkey|_address|tx_?hash|block_?hash|chain_?id|contract|"
    r"validator|proposer|recipient|beneficiary)"
)

Row = tuple[str, str, str, str, str, str]


def classify(line: str, path: str) -> tuple[str, str] | None:
    for cls, rx in VAL_RES:
        if rx.search(line):
            v = "REAL?"
            if PLACEHOLDER.search(line):
                v = "placeholder"
            if ZEROES.search(line):
                v = "test-fixture" if v == "REAL?" else v
            if TESTPATH.search(path) and v == "REAL?":
                v = "test-fixture?"
            if PUBNAME.search(line) and cls in ("hex64-keyname", "bearer-auth"):
                v = "public-by-design?"
            return cls, v
    return None


def scan_tree(repo: str) -> Iterator[Row]:
    for ere in ERE_LIST:
        p = subprocess.run(
            ["git", "-C", repo, "grep", "-nIi", "-E", ere, "HEAD"],
            capture_output=True,
            text=True,
        )
        for ln in p.stdout.splitlines():
            m = re.match(r"HEAD:(.*?):(\d+):(.*)$", ln)
            if not m:
                continue
            r = classify(m.group(3), m.group(1))
            if r:
                yield ("tree", "HEAD", m.group(1), m.group(2), r[0], r[1])


def scan_history(repo: str) -> Iterator[Row]:
    log = subprocess.Popen(
        [
            "git",
            "-C",
            repo,
            "--no-pager",
            "log",
            "-p",
            "--all",
            "--no-color",
            "--format=@@@COMMIT %H",
            "-G",
            r"(private.?key|secret|mnemonic|seed.?phrase|api.?key|password|passwd|bearer|authorization|AGE-SECRET|ciphertext|token|webhook|ntfy)",
        ],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1 << 20,
    )
    assert log.stdout is not None
    commit = path = None
    hunk_no = 0
    for ln in log.stdout:
        if ln.startswith("@@@COMMIT "):
            commit = ln.split()[1].strip()
        elif ln.startswith("+++ b/"):
            path = ln[6:].rstrip()
        elif ln.startswith("@@"):
            m = re.search(r"\+(\d+)", ln)
            hunk_no = int(m.group(1)) - 1 if m else 0
        elif ln.startswith("+") and not ln.startswith("+++"):
            hunk_no += 1
            if commit and path:
                r = classify(ln[1:], path)
                if r:
                    yield ("hist", commit[:9], path, str(hunk_no), r[0], r[1])
        elif ln.startswith(" "):
            hunk_no += 1
    log.wait()


def scan_names(repo: str) -> Iterator[Row]:
    name_rx = re.compile(
        r"(?i)(\.(key|pem|p12|pfx|keystore|jks|kdb)$|\.env|wallet|secret|credential|id_rsa|id_ed25519|\.age$)"
    )
    ls = subprocess.run(["git", "-C", repo, "ls-files", "-s"], capture_output=True, text=True)
    for ln in ls.stdout.splitlines():
        parts = ln.split(None, 3)
        if len(parts) == 4 and name_rx.search(parts[3]):
            yield ("fname", "HEAD", parts[3], "0", "tracked-secretname", "name-only")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tree", action="store_true", help="scan working tree at HEAD")
    ap.add_argument("--history", action="store_true", help="scan added lines in all history")
    ap.add_argument("--repo", default=".", help="repository root (default: cwd)")
    ap.add_argument("--fail-on-real", action="store_true", help="exit 1 when REAL? rows exist")
    args = ap.parse_args()

    if not (args.tree or args.history):
        args.tree = True

    rows: list[Row] = []
    if args.tree:
        rows.extend(scan_tree(args.repo))
        rows.extend(scan_names(args.repo))
    if args.history:
        rows.extend(scan_history(args.repo))

    print("scope\tcommit\tpath\tline\tclass\tverdict")
    real = 0
    for r in rows:
        print("\t".join(r))
        if r[5] == "REAL?":
            real += 1
    print(f"# rows={len(rows)} REAL?={real}", file=sys.stderr)
    return 1 if (args.fail_on_real and real) else 0


if __name__ == "__main__":
    sys.exit(main())
