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

# Full set of valid Devin CLI tool names (used by normalize_tool and lint).
VALID_DEVIN_TOOLS = {
    "read", "write", "edit", "multi_edit", "exec", "grep", "glob",
    "skill", "todo_write", "web_search", "webfetch", "ask_user_question",
    "run_subagent", "read_subagent", "mcp_call_tool",
    "mcp_list_servers", "mcp_list_tools", "mcp_read_resource",
    "browser_preview", "close_browser_preview",
    "notebook_read", "notebook_edit",
    "request_scope", "get_output", "kill_shell",
}


def normalize_tool(name: str) -> str | None:
    name = str(name).strip()
    if name in TOOL_MAP:
        return TOOL_MAP[name]
    if name.startswith("mcp__"):
        return "mcp_call_tool"
    # Handle PascalCase MCP tool names (e.g. McpCallTool -> mcp_call_tool)
    lower = name.lower()
    if lower in TOOL_MAP.values():
        return lower
    if re.fullmatch(r"[a-z_]+", lower):
        return lower
    # Convert PascalCase to snake_case before falling back
    snake = re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")
    if snake in TOOL_MAP.values() or snake in VALID_DEVIN_TOOLS:
        return snake
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


def _passthrough_copy(src: Path, dst: Path, skills_dst: Path, agents_dst: Path) -> None:
    """Copy a file as-is, only rewriting harness/.claude path references.

    Used for the harness/devin -> .devin leg where the source is already in
    Devin format and re-parsing frontmatter would be a lossy double conversion.
    """
    try:
        text = src.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        import shutil
        shutil.copy2(src, dst)
        return
    new_text = rewrite_body(text, skills_dst, agents_dst)
    dst.write_text(new_text, encoding="utf-8")


def mirror_skills(skills_src: Path, skills_dst: Path, agents_dst: Path, passthrough: bool = False):
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

        if passthrough:
            _passthrough_copy(src_skill, dst_dir / "SKILL.md", skills_dst, agents_dst)
            # Rewrite references in companion files only (SKILL.md already
            # rewritten by _passthrough_copy).
            for child in dst_dir.iterdir():
                if child.is_file() and child.name != "SKILL.md":
                    rewrite_text_file(child, skills_dst, agents_dst)
                elif child.is_dir():
                    rewrite_tree(child, skills_dst, agents_dst)
            continue

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


def mirror_agents(agents_src: Path, agents_dst: Path, skills_dst: Path, passthrough: bool = False):
    agents_dst.mkdir(parents=True, exist_ok=True)
    for src_file in agents_src.iterdir():
        if not src_file.is_file() or not src_file.suffix == ".md" or src_file.name.lower().startswith("readme"):
            continue

        # S5: Guard underscore-prefixed shared fragments. In conversion mode
        # they are passthrough-copied (path rewrite only, no frontmatter
        # conversion) since they are shared fragments, not spawnable roles.
        # In passthrough mode they are also copied.
        if src_file.name.startswith("_"):
            _passthrough_copy(src_file, agents_dst / src_file.name, skills_dst, agents_dst)
            continue

        if passthrough:
            _passthrough_copy(src_file, agents_dst / src_file.name, skills_dst, agents_dst)
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


# --- S2: Semantic lint -------------------------------------------------------


def _lint_frontmatter(path: Path, fm: dict, errors: list[str]) -> None:
    """Validate a single file's frontmatter for Devin compatibility."""
    rel = str(path)
    # Check YAML was parsed (fm must be a dict).
    if fm is None:
        errors.append(f"{rel}: invalid or missing YAML frontmatter")
        return
    if not isinstance(fm, dict):
        errors.append(f"{rel}: YAML frontmatter parsed to {type(fm).__name__}, expected dict")
        return
    # Check tool names are in the Devin allowlist.
    tools = fm.get("allowed-tools", [])
    if isinstance(tools, list):
        for t in tools:
            if t not in VALID_DEVIN_TOOLS:
                errors.append(f"{rel}: unknown Devin tool '{t}' in allowed-tools")
    # Check model is not a Claude alias.
    model = fm.get("model")
    if model and re.fullmatch(r"claude-.*|opus|sonnet|codex|haiku", str(model), re.I):
        errors.append(f"{rel}: model '{model}' is a Claude alias, not a Devin model")


def lint_mirror(harness_devin: Path, live_devin: Path) -> int:
    """Semantic lint: verify converter output is Devin-valid and lossless.

    Checks:
    1. All YAML frontmatter in SKILL.md and agent .md files parses correctly.
    2. No Claude model aliases leaked into Devin files.
    3. No unknown Devin tool names in allowed-tools.
    4. subagent: true in harness/devin is preserved in .devin.
    5. Skill tool present in Devin agents whose Claude source had Skill.
    """
    repo_root = Path(__file__).resolve().parent.parent
    errors: list[str] = []

    def _collect_lint_targets(root: Path) -> list[Path]:
        """Collect SKILL.md files and agent .md files (not READMEs/references)."""
        if not root.exists():
            return []
        targets = []
        # SKILL.md files under skills/
        skills_dir = root / "skills"
        if skills_dir.exists():
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        targets.append(skill_md)
        # Agent .md files under agents/ (exclude _ prefixed and READMEs)
        agents_dir = root / "agents"
        if agents_dir.exists():
            for md in agents_dir.glob("*.md"):
                if md.name.lower().startswith("readme"):
                    continue
                targets.append(md)
        return sorted(targets)

    # 1-3: Lint SKILL.md and agent .md files in both trees.
    for tree in (harness_devin, live_devin):
        for md in _collect_lint_targets(tree):
            try:
                text = md.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            fm, _ = split_frontmatter(text)
            _lint_frontmatter(md, fm, errors)

    # 4: subagent preservation: harness/devin skills with subagent: true
    #    must also have subagent: true in .devin.
    harness_skills = harness_devin / "skills"
    live_skills = live_devin / "skills"
    if harness_skills.exists() and live_skills.exists():
        for skill_dir in harness_skills.iterdir():
            if not skill_dir.is_dir():
                continue
            src = skill_dir / "SKILL.md"
            if not src.exists():
                continue
            fm, _ = split_frontmatter(src.read_text(encoding="utf-8"))
            if fm and fm.get("subagent") is True:
                live_skill = live_skills / skill_dir.name / "SKILL.md"
                if live_skill.exists():
                    live_fm, _ = split_frontmatter(live_skill.read_text(encoding="utf-8"))
                    if not (live_fm and live_fm.get("subagent") is True):
                        errors.append(
                            f"{live_skill}: subagent: true lost (harness/devin has it)"
                        )

    # 5: Skill tool mapping — agents in harness/devin that list 'skill' should
    #    keep it in .devin.
    harness_agents = harness_devin / "agents"
    live_agents = live_devin / "agents"
    if harness_agents.exists() and live_agents.exists():
        for agent_md in harness_agents.glob("*.md"):
            if agent_md.name.startswith("_"):
                continue
            fm, _ = split_frontmatter(agent_md.read_text(encoding="utf-8"))
            if fm and "skill" in (fm.get("allowed-tools") or []):
                live_agent = live_agents / agent_md.name
                if live_agent.exists():
                    live_fm, _ = split_frontmatter(live_agent.read_text(encoding="utf-8"))
                    if not (live_fm and "skill" in (live_fm.get("allowed-tools") or [])):
                        errors.append(
                            f"{live_agent}: 'skill' tool lost from allowed-tools"
                        )

    if errors:
        print(f"Semantic lint found {len(errors)} issue(s):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("Semantic lint: all checks passed.")
    return 0


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


def check_mirror(skills_src: Path, agents_src: Path, skills_dst: Path, agents_dst: Path, passthrough: bool = False) -> int:
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
            mirror_skills(skills_src, temp_root / skills_dst, temp_root / agents_dst, passthrough=passthrough)
            mirror_agents(agents_src, temp_root / agents_dst, temp_root / skills_dst, passthrough=passthrough)
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
    parser.add_argument("--passthrough", action="store_true", help="Copy source as-is (Devin-to-Devin) instead of converting Claude frontmatter.")
    parser.add_argument("--lint", action="store_true", help="Run semantic lint on harness/devin/ and .devin/ (YAML validity, tool/model validity, subagent/skill preservation).")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    if not (repo_root / args.skills_src).exists():
        print(f"Skills source missing: {args.skills_src}", file=sys.stderr)
        return 1
    if not (repo_root / args.agents_src).exists():
        print(f"Agents source missing: {args.agents_src}", file=sys.stderr)
        return 1

    if args.lint:
        return lint_mirror(repo_root / "harness/devin", repo_root / ".devin")

    if args.check:
        return check_mirror(args.skills_src, args.agents_src, args.skills_dst, args.agents_dst, passthrough=args.passthrough)

    # Absolute paths make relative rewrites stable inside rewrite_body.
    os.chdir(Path.cwd())
    mirror_skills(args.skills_src.resolve(), args.skills_dst.resolve(), args.agents_dst.resolve(), passthrough=args.passthrough)
    mirror_agents(args.agents_src.resolve(), args.agents_dst.resolve(), args.skills_dst.resolve(), passthrough=args.passthrough)
    print(f"Mirrored Devin skills to {args.skills_dst} and agents to {args.agents_dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
