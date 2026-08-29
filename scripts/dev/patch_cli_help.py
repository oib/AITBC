#!/usr/bin/env python3
"""Patch CLI command/group docstrings and epilog examples from a JSON mapping.

This is a developer helper to apply manually-curated help content to source
files in bulk.  It uses libcst so it preserves formatting and comments.

Usage:
    python scripts/dev/patch_cli_help.py \
        cli/aitbc_cli/commands/wallet/basic.py \
        /tmp/wallet_basic_help.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import libcst as cst


HELP_EXAMPLE_HEADER = "\n\nExamples:\n"


def _dedent(text: str) -> str:
    return re.sub(r"\n\s+", " ", text.strip()).strip()


def _format_epilog(examples: list[str]) -> str:
    lines = ["Examples:"]
    for ex in examples:
        lines.append("")
        lines.append(f"  {ex}")
    return "\n".join(lines)


def _is_command_decorator(dec: cst.Decorator) -> bool:
    call = dec.decorator
    if not isinstance(call, cst.Call):
        return False
    func = call.func
    # click.group / click.command / <group>.command
    if isinstance(func, cst.Attribute) and func.attr.value in {"command", "group"}:
        return True
    if isinstance(func, cst.Name) and func.value in {"command", "group"}:
        return True
    return False


def _add_epilog_to_decorator(dec: cst.Decorator, examples: list[str]) -> cst.Decorator:
    call = dec.decorator
    if not isinstance(call, cst.Call):
        return dec

    new_keywords = [arg for arg in call.args if not (arg.keyword is not None and arg.keyword.value == "epilog")]

    text = _format_epilog(examples)
    epilog_value = cst.SimpleString(f'"""{text}"""')

    new_keywords.append(cst.Arg(keyword=cst.Name("epilog"), value=epilog_value, equal=cst.AssignEqual()))

    new_call = call.with_changes(args=new_keywords)
    return dec.with_changes(decorator=new_call)


def _update_docstring(func_def: cst.FunctionDef, description: str) -> cst.FunctionDef:
    # Build a clean docstring.
    # First line is the short help (click uses it in group listings).
    # We keep description as one or two sentences; click uses the whole thing.
    text = _dedent(description)
    docstring = f'"""{text}"""'

    body = list(func_def.body.body)
    if body and isinstance(body[0], cst.SimpleStatementLine):
        first = body[0].body[0]
        if isinstance(first, cst.Expr) and isinstance(first.value, cst.SimpleString):
            # Replace existing docstring.
            body[0] = cst.SimpleStatementLine(
                body=[cst.Expr(value=cst.SimpleString(docstring))],
                leading_lines=body[0].leading_lines,
            )
            return func_def.with_changes(body=func_def.body.with_changes(body=body))

    # No existing docstring; prepend one.
    body.insert(
        0,
        cst.SimpleStatementLine(
            body=[cst.Expr(value=cst.SimpleString(docstring))],
            leading_lines=[],
        ),
    )
    return func_def.with_changes(body=func_def.body.with_changes(body=body))


class HelpPatcher(cst.CSTTransformer):
    def __init__(self, mapping: dict[str, dict[str, str | list[str]]]) -> None:
        super().__init__()
        self.mapping = mapping

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        name = original_node.name.value
        if name not in self.mapping:
            return updated_node

        entry = self.mapping[name]
        description = entry.get("description")
        examples = entry.get("examples")

        decorators = list(updated_node.decorators)
        new_decorators: list[cst.Decorator] = []
        for dec in decorators:
            if _is_command_decorator(dec) and examples:
                new_decorators.append(_add_epilog_to_decorator(dec, examples))
            else:
                new_decorators.append(dec)

        if description:
            updated_node = _update_docstring(updated_node, description)

        return updated_node.with_changes(decorators=new_decorators)


def patch_file(path: Path, mapping: dict[str, dict[str, str | list[str]]]) -> set[str]:
    source = path.read_text()
    module = cst.parse_module(source)
    new_module = module.visit(HelpPatcher(mapping))
    new_source = new_module.code

    if new_source != source:
        path.write_text(new_source)
        return set(mapping.keys())
    return set()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Python file to patch")
    parser.add_argument("mapping", help="JSON file with mapping {func_name: {description, examples}}")
    args = parser.parse_args()

    mapping: dict[str, dict[str, str | list[str]]] = json.loads(Path(args.mapping).read_text())
    patched = patch_file(Path(args.path), mapping)
    if patched:
        print(f"Patched {len(patched)} commands in {args.path}: {', '.join(sorted(patched))}")
    else:
        print(f"No matching commands found in {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
