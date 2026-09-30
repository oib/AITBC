#!/usr/bin/env python3
"""Orphan-docs check: every .md file should be reachable from another .md file.

Extracts relative links from all Markdown files (inline `[x](y)`,
reference-style `[x][r]`/`[r]: y`, and `<a href="y">`), skipping fenced and
inline code, and resolves each against the source file's directory. A file
with zero inbound links is an orphan.

Expected orphans (release notes, archive, skills, CI templates, READMEs that
sit beside the code they document) are allowed by prefix. Everything else
must either be linked or listed in `orphan-docs-baseline.txt` — the baseline
ratchets: new orphans fail the check, and baseline entries that have since
been linked are reported so the list only shrinks.

Usage:
    check_orphan_docs.py            # verify against the baseline
    check_orphan_docs.py --write-baseline   # regenerate the baseline
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("orphan-docs-baseline.txt")

# Files that are legitimately reached by means other than Markdown links:
# release logs are curated lists, archive is history, skills are loaded by
# tooling, CI templates render outside the docs tree, and src-adjacent
# READMEs are read next to the code they document.
ALLOWED_PREFIXES = (
    "docs/releases/",
    "docs/archive/",
    "skills/",
    ".github/",
    ".gitea/",
    "apps/",  # src-adjacent service READMEs are code docs, not web docs
)

FENCE = re.compile(r"^(```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
INLINE_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
REF_USE = re.compile(r"\[[^\]]*\]\[([^\]]+)\]")
REF_DEF = re.compile(r"^\s*\[([^\]]+)\]:\s*(\S+)", re.M)
HTML_LINK = re.compile(r"""<a\s+[^>]*href=["']([^"']+)["']""")


def links_in(text: str) -> list[str]:
    # drop fenced code blocks
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    body = INLINE_CODE.sub("", "\n".join(out))
    refs = {k.lower(): v for k, v in REF_DEF.findall(body)}
    targets = [m.group(1) for m in INLINE_LINK.finditer(body)]
    targets += [refs[m.group(1).lower()] for m in REF_USE.finditer(body) if m.group(1).lower() in refs]
    targets += HTML_LINK.findall(body)
    return targets


def is_relative(target: str) -> bool:
    if "://" in target or target.startswith(("mailto:", "/", "#")):
        return False
    return True


def main() -> int:
    files = sorted(ROOT.rglob("*.md"))
    inbound: set[Path] = set()
    for f in files:
        for t in links_in(f.read_text(errors="replace")):
            if not is_relative(t):
                continue
            t = t.split("#")[0].split("?")[0]
            if not t:
                continue
            resolved = (f.parent / t).resolve()
            if resolved.is_dir() and (resolved / "README.md").exists():
                resolved = resolved / "README.md"
            if resolved.suffix == ".md" and resolved.is_file():
                inbound.add(resolved)

    orphans = sorted(
        f.relative_to(ROOT).as_posix()
        for f in files
        if f.resolve() not in inbound and not f.relative_to(ROOT).as_posix().startswith(ALLOWED_PREFIXES)
    )

    if "--write-baseline" in sys.argv:
        BASELINE.write_text("\n".join(orphans) + ("\n" if orphans else ""))
        print(f"wrote {len(orphans)} orphans to {BASELINE}")
        return 0

    baseline = set()
    if BASELINE.exists():
        baseline = {ln.strip() for ln in BASELINE.read_text().splitlines() if ln.strip()}

    new = [o for o in orphans if o not in baseline]
    fixed = sorted(baseline - set(orphans))
    rc = 0
    for o in new:
        print(f"NEW ORPHAN: {o}")
        rc = 1
    for o in fixed:
        print(f"baseline entry now linked (remove it): {o}")
        rc = 1
    if rc == 0:
        print(f"orphan-docs check clean — {len(orphans)} known orphans, no new ones")
    else:
        print("link the file from another .md, or list it in the baseline with --write-baseline")
    return rc


if __name__ == "__main__":
    sys.exit(main())
