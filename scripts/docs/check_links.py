#!/usr/bin/env python3
"""Validate internal markdown links across the AITBC documentation tree.

Exit codes:
    0 - all links valid
    1 - one or more broken internal .md links found
"""

import re
import sys
from pathlib import Path

# Paths owned by the agentic-boilerplate repo, not this one.
#
# The SAFe/agentic governance docs under docs/sop/, docs/onboarding/ and docs/guides/
# were written while the boilerplate was vendored in-tree. v0.21 stripped it
# ("refactor(harness): strip boilerplate"), so these relative links no longer resolve
# here -- but the documents they point at still exist, and still govern this repo, in
# https://gitlab.haemosan.at/boilerplate/agentic-boilerplate (local checkout:
# /opt/boilerplate).
#
# They are cross-repo references, not broken links, so this checker does not own them.
# Anything added here must genuinely live in the boilerplate repo.
BOILERPLATE_OWNED_PREFIXES = (
    "adrs/",
    "dark-factory/",
    "profiles/",
    "specs_templates/",
    "patterns_library/",
    "knowledge/",
    "work/improvement-proposals/",
    ".agentic/templates/",
    ".claude/agents/",
    ".claude/README.md",
    ".claude/SETUP.md",
    ".claude/TROUBLESHOOTING.md",
    ".gemini/",
    ".codex/",
    "TEMPLATE_SETUP.md",
)

# Documentation trees excluded from link validation.
#
# docs/archive/ holds retired material, including README-TEMPLATE.md -- a template meant
# to be copied into *other* repos, whose "./AGENTS.md"-style links are deliberate
# placeholders relative to the consuming project. Resolving them against this repo is
# meaningless.
EXCLUDED_DOC_DIRS = ("docs/archive/",)

LINK_RE = re.compile(r"(\[[^\]]*\]\()([^)]+)(\))")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def strip_code_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line count.

    Links inside fences are illustrative samples (e.g. a skeleton README shown in an
    authoring guide), not navigable links, and must not be resolved against the tree.
    """
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    docs_dir = repo / "docs"

    scan_files = [
        p for p in docs_dir.rglob("*.md") if not any(str(p.relative_to(repo)).startswith(d) for d in EXCLUDED_DOC_DIRS)
    ]
    if (repo / "README.md").exists():
        scan_files.append(repo / "README.md")

    broken: list[tuple[str, str]] = []
    checked = 0
    skipped_boilerplate = 0

    for src in scan_files:
        text = strip_code_fences(src.read_text(errors="ignore"))
        for m in LINK_RE.finditer(text):
            target = m.group(2).strip()
            base = target.split("#", 1)[0]
            if not base:
                continue
            if base.startswith(("http://", "https://", "mailto://", "vscode-remote://")):
                continue
            if not base.endswith(".md"):
                continue

            if base.startswith("/"):
                resolved = repo / base.lstrip("/")
            else:
                resolved = (src.parent / base).resolve()

            try:
                rel = resolved.relative_to(repo).as_posix()
            except ValueError:
                # Escapes the repo root entirely; judge it by the literal target.
                rel = base.lstrip("./")

            if rel.startswith(BOILERPLATE_OWNED_PREFIXES):
                skipped_boilerplate += 1
                continue

            checked += 1
            if not resolved.exists():
                broken.append((str(src.relative_to(repo)), target))

    suffix = f" ({skipped_boilerplate} boilerplate-owned reference(s) skipped)" if skipped_boilerplate else ""

    if not broken:
        print(f"Checked {checked} internal .md link(s). All valid.{suffix}")
        return 0

    print(f"Checked {checked} internal .md link(s). Found {len(broken)} broken link(s):{suffix}\n")
    for src, target in broken:
        print(f"  {src} -> {target}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
