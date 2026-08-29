#!/usr/bin/env python3
"""Convert ``@click.argument`` decorators to ``@click.option`` using libcst.

This is a developer helper for the 10/10 CLI help refactor.  It does the
mechanical decorator rewrite; help text and docstrings must still be reviewed
and expanded manually afterwards.

Usage:
    python scripts/dev/convert_positional_args.py cli/aitbc_cli/commands/wallet/basic.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import libcst as cst


HELP_HINTS = {
    "address": "Blockchain address to fund.",
    "amount": "Amount of AIT.",
    "backup_path": "Path to the backup file.",
    "description": "Free-form description.",
    "file_path": "Path to the file.",
    "job_id": "Coordinator job ID.",
    "name": "Wallet name.",
    "stake_id": "Stake ID.",
    "to_address": "Destination address.",
    "tx_id": "Transaction ID.",
    "signers": "One or more signer addresses.",
}


def _kebab(name: str) -> str:
    return name.replace("_", "-")


def _human(name: str) -> str:
    return " ".join(name.replace("_", " ").split()).capitalize()


def _option_help(var: str) -> cst.SimpleString:
    hint = HELP_HINTS.get(var, f"The {_human(var)}.")
    return cst.SimpleString(f'"{hint}"')


def _make_option_decorator(decorator: cst.Decorator) -> cst.Decorator:
    call = decorator.decorator
    if not isinstance(call, cst.Call):
        return decorator
    func = call.func
    if not (isinstance(func, cst.Attribute) and func.value.value == "click" and func.attr.value == "argument"):
        return decorator

    # First positional argument is the variable name.
    if not call.args or not isinstance(call.args[0].value, cst.SimpleString):
        return decorator
    var_name = call.args[0].value.value[1:-1]  # strip quotes

    # Parse the rest of the arguments.
    kwargs: dict[str, cst.BaseExpression] = {}
    for arg in call.args[1:]:
        if arg.keyword is not None:
            kwargs[arg.keyword.value] = arg.value

    new_args: list[cst.Arg] = [
        cst.Arg(value=cst.SimpleString(f'"--{_kebab(var_name)}"')),
        cst.Arg(value=cst.SimpleString(f'"{var_name}"')),
    ]

    # required
    if "required" in kwargs:
        if isinstance(kwargs["required"], cst.Name) and kwargs["required"].value == "False":
            new_args.append(cst.Arg(keyword=cst.Name("required"), value=cst.Name("False"), equal=cst.AssignEqual()))
        else:
            new_args.append(cst.Arg(keyword=cst.Name("required"), value=cst.Name("True"), equal=cst.AssignEqual()))
    elif "default" not in kwargs:
        new_args.append(cst.Arg(keyword=cst.Name("required"), value=cst.Name("True"), equal=cst.AssignEqual()))

    # nargs=-1 -> multiple=True
    if "nargs" in kwargs:
        nargs = kwargs["nargs"]
        is_variadic = (
            isinstance(nargs, cst.UnaryOperation)
            and isinstance(nargs.operator, cst.Minus)
            and isinstance(nargs.expression, cst.Integer)
            and nargs.expression.value == "1"
        )
        if is_variadic:
            new_args.append(cst.Arg(keyword=cst.Name("multiple"), value=cst.Name("True"), equal=cst.AssignEqual()))
        else:
            new_args.append(cst.Arg(keyword=cst.Name("nargs"), value=nargs, equal=cst.AssignEqual()))

    # type and default
    for key in ("type", "default"):
        if key in kwargs:
            new_args.append(cst.Arg(keyword=cst.Name(key), value=kwargs[key], equal=cst.AssignEqual()))

    # help
    if "help" in kwargs:
        new_args.append(cst.Arg(keyword=cst.Name("help"), value=kwargs["help"], equal=cst.AssignEqual()))
    else:
        new_args.append(cst.Arg(keyword=cst.Name("help"), value=_option_help(var_name), equal=cst.AssignEqual()))

    # any other kwargs
    handled = {"required", "nargs", "type", "default", "help"}
    for key, val in kwargs.items():
        if key not in handled:
            new_args.append(cst.Arg(keyword=cst.Name(key), value=val, equal=cst.AssignEqual()))

    new_call = cst.Call(
        func=cst.Attribute(value=cst.Name("click"), attr=cst.Name("option")),
        args=new_args,
        lpar=call.lpar,
        rpar=call.rpar,
    )
    return decorator.with_changes(decorator=new_call)


class ArgumentToOptionTransformer(cst.CSTTransformer):
    def leave_Decorator(self, original_node: cst.Decorator, updated_node: cst.Decorator) -> cst.Decorator:
        return _make_option_decorator(updated_node)


def convert_file(path: Path, dry_run: bool = False) -> list[str]:
    source = path.read_text()
    module = cst.parse_module(source)
    new_module = module.visit(ArgumentToOptionTransformer())
    new_source = new_module.code

    # Track which decorators we rewrote.
    converted: list[str] = []
    for line in source.splitlines():
        match = re.match(r"\s*@click\.argument\(['\"]([^'\"]+)['\"]", line)
        if match:
            converted.append(f"{match.group(1)}: {line.strip()}")

    if not dry_run and new_source != source:
        path.write_text(new_source)

    return converted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Python file to convert")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    changed = convert_file(Path(args.path), dry_run=args.dry_run)
    if changed:
        print(f"Converted {len(changed)} @click.argument decorators in {args.path}")
        for c in changed:
            print(f"  - {c}")
    else:
        print(f"No @click.argument decorators found in {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
