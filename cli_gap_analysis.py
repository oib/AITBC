import os
import re
import sys
from pathlib import Path

os.environ.setdefault("AITBC_SKIP_ENV_FILES", "1")

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Ensure the repo-root aitbc package wins over packages/py/aitbc-core/src/aitbc
# when the test conftest has put the package source trees first.
for _src in (REPO / "packages" / "py").glob("*/src"):
    try:
        sys.path.remove(str(_src))
    except ValueError:
        pass
sys.path.insert(0, str(REPO))

import click  # noqa: E402

from aitbc_cli.core.main import cli  # noqa: E402


def collect_subcommands(cmd):
    if not isinstance(cmd, click.Group):
        return set()
    return set(cmd.commands.keys())


def normalize_token(t):
    t = re.sub(r"^[\`\'\"\)\.,\(]+|[\`\'\"\)\.,\(]+$", "", t)
    if t in ("", "—", "-", "--", "...", "ops", "or", "and") or re.match(r"^-+$", t):
        return None
    # allow wildcard patterns like config-* or multisig-*
    if re.match(r"^[a-z0-9_*-]+$", t) and len(t) > 1:
        return t
    return None

def is_generic(cell):
    """Return True if the key subcommands cell is generic prose, not a specific list."""
    stripped = cell.strip().lower()
    if stripped in ("", "—", "-", "--", "..."):
        return True
    # parens like (ops), (perf ops), (GPU service ops), etc.
    if stripped.startswith("(") and stripped.endswith(")"):
        return True
    if "ops" in stripped and "`" not in cell:
        return True
    return False


def expand_wildcard(token, actual):
    if "*" not in token:
        return {token}
    prefix = token.replace("-*", "").replace("*", "")
    return {sub for sub in actual if sub.startswith(prefix)}


def parse_readme_table(text):
    groups = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("| Group") and "Description" in line and "Key subcommands" in line:
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                continue
            group = normalize_token(parts[1])
            if not group:
                continue
            cell = parts[3]
            if is_generic(cell):
                groups[group] = None
                continue
            tokens = [normalize_token(t) for t in re.split(r"[,/\s]+", cell) if t.strip()]
            tokens = [t for t in tokens if t]
            groups[group] = tokens
    return groups


def parse_usage_guide_groups(text):
    groups = {}
    for line in text.splitlines():
        m = re.match(r"\s*[-*]\s+`?([a-z0-9_-]+)`?\s*[-—]\s*(.*)", line)
        if m:
            group = m.group(1)
            rest = m.group(2)
            # If rest has parenthetical (ops) it is generic
            if "(" in rest and ")" in rest and "ops" in rest:
                groups[group] = None
                continue
            subs = []
            for word in re.findall(r"`([a-z0-9_*-]+)`", rest):
                t = normalize_token(word)
                if t:
                    subs.append(t)
            groups[group] = subs if subs else None
    return groups


def main():
    top_level = set(cli.commands.keys())

    readme_text = (REPO / "cli" / "README.md").read_text()
    usage_text = (REPO / "cli" / "CLI_USAGE_GUIDE.md").read_text()

    readme_groups = parse_readme_table(readme_text)
    usage_groups = parse_usage_guide_groups(usage_text)

    # merge: explicit subcommand lists from README take precedence; Usage Guide fills gaps
    expected = {}
    for g in set(readme_groups) | set(usage_groups):
        r = readme_groups.get(g)
        u = usage_groups.get(g)
        if r is not None:
            expected[g] = r
        elif u is not None:
            expected[g] = u
        else:
            expected[g] = None

    print("=" * 60)
    print("Top-level CLI commands not documented as groups:")
    doc_top = set(expected)
    for cmd in sorted(top_level - doc_top):
        print(f"  aitbc {cmd}")

    print()
    print("Top-level commands documented but missing from CLI:")
    for cmd in sorted(doc_top - top_level):
        print(f"  aitbc {cmd}")

    print()
    print("Subcommand gaps for groups with explicit key subcommand lists:")
    for group in sorted(expected):
        subs = expected[group]
        if subs is None:
            continue
        if group not in cli.commands:
            print(f"  {group}: group does not exist in CLI")
            continue
        cmd = cli.commands[group]
        if not isinstance(cmd, click.Group):
            print(f"  {group}: documented as group but is a leaf command in CLI")
            continue
        actual = set(cmd.commands.keys())
        documented = set()
        for token in subs:
            documented.update(expand_wildcard(token, actual))
        missing = documented - actual
        extra = actual - documented
        if missing or extra:
            print(f"  {group}:")
            if missing:
                print(f"    documented but missing: {', '.join(sorted(missing))}")
            if extra:
                print(f"    implemented but not documented: {', '.join(sorted(extra))}")

    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Top-level CLI commands: {len(top_level)}")
    print(f"  Top-level groups in docs: {len(doc_top)}")
    print(f"  Undocumented top-level commands: {len(top_level - doc_top)}")
    print(f"  Documented but missing top-level commands: {len(doc_top - top_level)}")


if __name__ == "__main__":
    main()
