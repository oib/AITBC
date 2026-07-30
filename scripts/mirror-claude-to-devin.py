#!/usr/bin/env python3
"""Mirror .claude skills and agents into .devin/ with Devin CLI frontmatter.

Usage:
    python3 scripts/mirror-claude-to-devin.py \
        --skills-src .claude/skills \
        --agents-src .claude/agents \
        --skills-dst .devin/skills \
        --agents-dst .devin/agents

It converts Claude-style frontmatter (allowed-tools: Read, Bash, ...,
context: fork, agent: Explore) into the Devin CLI skill/subagent format
(allowed-tools: [read, exec, ...]) and rewrites harness/claude/ and .claude/
references to .devin/ in the .devin copies.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


TOOL_MAP = {
    "Read": "read",
    "Write": "write",
    "Edit": "edit",
    "MultiEdit": "multi_edit",
    "Bash": "exec",
    "Grep": "grep",
    "Glob": "glob",
    "Skill": "skill",
    "Task": "todo_write",
    "WebSearch": "web_search",
    "WebFetch": "webfetch",
    "AskUserQuestion": "ask_user_question",
    "TodoWrite": "todo_write",
    "RunSubagent": "run_subagent",
    "McpCallTool": "mcp_call_tool",
    # unknown mcp__* tools collapse to the generic mcp_call_tool
}


def normalize_tool(name: str) -> str | None:
    name = str(name).strip()
    if name in TOOL_MAP:
        return TOOL_MAP[name]
    if name.startswith("mcp__"):
        return "mcp_call_tool"
    lower = name.lower()
    # If it already looks like a Devin tool, pass through.
    if re.fullmatch(r"[a-z_]+", lower):
        return lower
    # Fallback: keep the lowered name and let Devin ignore it if invalid.
    return lower


def convert_model(model: str | None) -> str | None:
    """Normalize a Claude model name to the Devin boilerplate default.

    The Devin boilerplate default model is `swe-1.7-medium`. Any
    Claude `opus` / `sonnet` / `codex` reference is mapped to that default so
    generated Devin agents do not accidentally pin to Anthropic-specific
    aliases. Non-Claude / already-Devin names are passed through unchanged.
    """
    if not model:
        return None
    model = str(model).strip()
    if re.fullmatch(r"claude-.*", model, re.I) or re.fullmatch(r"opus|sonnet|codex|haiku", model, re.I):
        return "swe-1.7-medium"
    return model


def split_frontmatter(text: str):
    """Return (frontmatter dict or None, body)."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, parts[2].lstrip("\n")


def dump_frontmatter(fm: dict) -> str:
    # PyYAML default_flow_style=False gives the list/block format Devin examples use.
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, default_flow_style=False) + "---\n"


def rewrite_body(text: str, skills_dst: Path, agents_dst: Path) -> str:
    """Point references at the .devin/ tree in the mirrored copies."""
    text = text.replace("harness/claude/skills/", str(skills_dst.relative_to(Path.cwd())) + "/")
    text = text.replace("harness/.claude/skills/", str(skills_dst.relative_to(Path.cwd())) + "/")
    text = text.replace("harness/devin/skills/", str(skills_dst.relative_to(Path.cwd())) + "/")
    text = text.replace("harness/.devin/skills/", str(skills_dst.relative_to(Path.cwd())) + "/")
    text = text.replace(".claude/skills/", str(skills_dst.relative_to(Path.cwd())) + "/")
    text = text.replace("harness/claude/agents/", str(agents_dst.relative_to(Path.cwd())) + "/")
    text = text.replace("harness/.claude/agents/", str(agents_dst.relative_to(Path.cwd())) + "/")
    text = text.replace("harness/devin/agents/", str(agents_dst.relative_to(Path.cwd())) + "/")
    text = text.replace("harness/.devin/agents/", str(agents_dst.relative_to(Path.cwd())) + "/")
    text = text.replace(".claude/agents/", str(agents_dst.relative_to(Path.cwd())) + "/")
    return text


def rewrite_text_file(path: Path, skills_dst: Path, agents_dst: Path) -> None:
    """Rewrite harness/ and .claude/ skill/agent references in a text file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    new_text = rewrite_body(text, skills_dst, agents_dst)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")


def rewrite_tree(dst: Path, skills_dst: Path, agents_dst: Path) -> None:
    for child in dst.rglob("*"):
        if child.is_file():
            rewrite_text_file(child, skills_dst, agents_dst)


def mirror_skills(skills_src: Path, skills_dst: Path, agents_dst: Path):
    skills_dst.mkdir(parents=True, exist_ok=True)
    for src_dir in skills_src.iterdir():
        if not src_dir.is_dir():
            continue
        src_skill = src_dir / "SKILL.md"
        if not src_skill.exists():
            continue

        dst_dir = skills_dst / src_dir.name
        dst_dir.mkdir(parents=True, exist_ok=True)

        # Copy all non-SKILL.md files in the skill directory (scripts, references).
        for child in src_dir.iterdir():
            if child.name == "SKILL.md":
                continue
            if child.is_dir():
                # shallow copy of subdirs
                import shutil
                shutil.copytree(child, dst_dir / child.name, dirs_exist_ok=True)
            else:
                import shutil
                shutil.copy2(child, dst_dir / child.name)

        text = src_skill.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        if fm is None:
            fm = {}

        new_fm = {
            "name": fm.get("name", src_dir.name),
            "description": fm.get("description", ""),
            "triggers": ["user", "model"],
        }

        # Preserve Devin-specific or already-generated frontmatter so a second
        # pass (harness/devin -> .devin) is lossless.
        for key in ("triggers", "context", "subagent", "timeout"):
            if key in fm:
                new_fm[key] = fm[key]

        if "model" in fm:
            converted = convert_model(fm["model"])
            if converted:
                new_fm["model"] = converted

        # Convert allowed-tools
        raw_tools = fm.get("allowed-tools", fm.get("tools", []))
        if isinstance(raw_tools, str):
            raw_tools = [t.strip() for t in re.split(r"[,\s]+", raw_tools) if t.strip()]
        devin_tools = sorted({t for t in (normalize_tool(x) for x in raw_tools) if t})
        if devin_tools:
            new_fm["allowed-tools"] = devin_tools

        if str(fm.get("agent", "")).lower() == "explore":
            new_fm["subagent"] = True

        body = rewrite_body(body, skills_dst, agents_dst)
        (dst_dir / "SKILL.md").write_text(dump_frontmatter(new_fm) + "\n" + body, encoding="utf-8")

        # Rewrite references in any companion files (scripts, references).
        rewrite_tree(dst_dir, skills_dst, agents_dst)


def mirror_agents(agents_src: Path, agents_dst: Path, skills_dst: Path):
    agents_dst.mkdir(parents=True, exist_ok=True)
    for src_file in agents_src.iterdir():
        if not src_file.is_file() or not src_file.suffix == ".md" or src_file.name.startswith("_") or src_file.name.lower().startswith("readme"):
            continue

        text = src_file.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        if fm is None:
            fm = {}

        new_fm = {
            "name": fm.get("name", src_file.stem),
            "description": fm.get("description", ""),
        }

        if "model" in fm:
            converted = convert_model(fm["model"])
            if converted:
                new_fm["model"] = converted
        else:
            # Boilerplate default for Devin agents.
            new_fm["model"] = "swe-1.7-medium"

        raw_tools = fm.get("tools", fm.get("allowed-tools", []))
        if isinstance(raw_tools, str):
            raw_tools = [t.strip() for t in re.split(r"[,\s\[\]]+", raw_tools) if t.strip()]
        devin_tools = sorted({t for t in (normalize_tool(x) for x in raw_tools) if t})
        if devin_tools:
            new_fm["allowed-tools"] = devin_tools

        body = rewrite_body(body, skills_dst, agents_dst)
        (agents_dst / src_file.name).write_text(dump_frontmatter(new_fm) + "\n" + body, encoding="utf-8")


def _symlink_tree(link_dir: Path, target_dir: Path) -> None:
    """Ensure link_dir is a symlink to target_dir, creating parents as needed."""
    link_dir.parent.mkdir(parents=True, exist_ok=True)
    if link_dir.is_symlink():
        if link_dir.readlink() == target_dir:
            return
    if link_dir.exists():
        raise FileExistsError(f"{link_dir} exists and is not the required symlink to {target_dir}")
    link_dir.symlink_to(target_dir, target_is_directory=True)


def _diff_dirs(temp_dir: Path, real_dir: Path, allow_extras: bool) -> list[str]:
    """Run `diff -rq` and return the lines that represent real drift."""
    if not real_dir.exists():
        return [f"real directory missing: {real_dir}"]
    result = subprocess.run(
        ["diff", "-rq", str(temp_dir), str(real_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return []
    fails = []
    real_prefix = f"Only in {real_dir}"
    for line in result.stdout.splitlines() + result.stderr.splitlines():
        line = line.strip()
        if not line:
            continue
        if allow_extras and line.startswith(real_prefix):
            continue
        fails.append(line)
    return fails


def check_mirror(skills_src: Path, agents_src: Path, skills_dst: Path, agents_dst: Path) -> int:
    """Mirror to a temp tree and compare with the real destination.

    This lets `harness/devin` and `.devin` consumers be drift-guarded without
    writing to the real destination. Extras in the real `.devin/` consumer are
    allowed (project-specific skills/agents) but a missing or differing
    generated file is a fail.
    """
    repo_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="devin-mirror-check-") as tmp:
        temp_root = Path(tmp)
        for src in (skills_src, agents_src):
            src_parent = src.parent
            _symlink_tree(temp_root / src_parent, repo_root / src_parent)

        # Destination directories are materialized inside the temp tree.
        for dst in (skills_dst, agents_dst):
            (temp_root / dst).parent.mkdir(parents=True, exist_ok=True)

        old_cwd = os.getcwd()
        try:
            os.chdir(temp_root)
            mirror_skills(skills_src, temp_root / skills_dst, temp_root / agents_dst)
            mirror_agents(agents_src, temp_root / agents_dst, temp_root / skills_dst)
        finally:
            os.chdir(old_cwd)

        real_skills = repo_root / skills_dst
        real_agents = repo_root / agents_dst
        # A consumer .devin tree may carry project-specific additions.
        allow_extras = str(skills_dst).split(os.sep, 1)[0] == ".devin"
        failures = []
        failures.extend(_diff_dirs(temp_root / skills_dst, real_skills, allow_extras))
        failures.extend(_diff_dirs(temp_root / agents_dst, real_agents, allow_extras))

        if failures:
            print(f"Drift detected against {skills_dst} and {agents_dst}:", file=sys.stderr)
            for line in failures:
                print(f"  {line}", file=sys.stderr)
            return 1
        print(f"No drift: {skills_dst} and {agents_dst} are up to date.")
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mirror Claude harness into Devin CLI tree")
    parser.add_argument("--skills-src", default=".claude/skills", type=Path)
    parser.add_argument("--agents-src", default=".claude/agents", type=Path)
    parser.add_argument("--skills-dst", default=".devin/skills", type=Path)
    parser.add_argument("--agents-dst", default=".devin/agents", type=Path)
    parser.add_argument("--check", action="store_true", help="Compare only; do not write the live destination.")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    if not (repo_root / args.skills_src).exists():
        print(f"Skills source missing: {args.skills_src}", file=sys.stderr)
        return 1
    if not (repo_root / args.agents_src).exists():
        print(f"Agents source missing: {args.agents_src}", file=sys.stderr)
        return 1

    if args.check:
        return check_mirror(args.skills_src, args.agents_src, args.skills_dst, args.agents_dst)

    # Absolute paths make relative rewrites stable inside rewrite_body.
    os.chdir(Path.cwd())
    mirror_skills(args.skills_src.resolve(), args.skills_dst.resolve(), args.agents_dst.resolve())
    mirror_agents(args.agents_src.resolve(), args.agents_dst.resolve(), args.skills_dst.resolve())
    print(f"Mirrored Devin skills to {args.skills_dst} and agents to {args.agents_dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
