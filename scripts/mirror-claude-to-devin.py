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
import sys
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
    "Skill": None,
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
    """Normalize a Claude model name to a Devin model alias.

    Devin resolves the `opus` / `sonnet` / `codex` aliases to their CURRENT
    family, so bare aliases are kept as-is. Pinning them to a version number
    would silently downgrade the seat (`opus` means Opus 5, not Opus 4.6).
    """
    if not model:
        return None
    model = str(model).strip()
    if re.fullmatch(r"claude-sonnet(-\d.*)?", model, re.I):
        return "sonnet"
    if re.fullmatch(r"claude-opus(-\d.*)?", model, re.I):
        return "opus"
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

        raw_tools = fm.get("tools", fm.get("allowed-tools", []))
        if isinstance(raw_tools, str):
            raw_tools = [t.strip() for t in re.split(r"[,\s\[\]]+", raw_tools) if t.strip()]
        devin_tools = sorted({t for t in (normalize_tool(x) for x in raw_tools) if t})
        if devin_tools:
            new_fm["allowed-tools"] = devin_tools

        body = rewrite_body(body, skills_dst, agents_dst)
        (agents_dst / src_file.name).write_text(dump_frontmatter(new_fm) + "\n" + body, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mirror Claude harness into Devin CLI tree")
    parser.add_argument("--skills-src", default=".claude/skills", type=Path)
    parser.add_argument("--agents-src", default=".claude/agents", type=Path)
    parser.add_argument("--skills-dst", default=".devin/skills", type=Path)
    parser.add_argument("--agents-dst", default=".devin/agents", type=Path)
    args = parser.parse_args(argv)

    if not args.skills_src.exists():
        print(f"Skills source missing: {args.skills_src}", file=sys.stderr)
        return 1
    if not args.agents_src.exists():
        print(f"Agents source missing: {args.agents_src}", file=sys.stderr)
        return 1

    # Absolute paths make relative rewrites stable inside rewrite_body.
    os.chdir(Path.cwd())
    mirror_skills(args.skills_src.resolve(), args.skills_dst.resolve(), args.agents_dst.resolve())
    mirror_agents(args.agents_src.resolve(), args.agents_dst.resolve(), args.skills_dst.resolve())
    print(f"Mirrored Devin skills to {args.skills_dst} and agents to {args.agents_dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
