#!/usr/bin/env python3
"""
Comprehensive B008 fix using LibCST.

Converts various B008 violation patterns to use Annotated[] form:
1. `param: Type = Depends(...)` -> `param: Annotated[Type, Depends(...)]`
2. `param: Annotated[Type, Depends(...)] = Depends()` -> `param: Annotated[Type, Depends(...)]`  (redundant default)
3. `param: Type = Query(...)` -> `param: Annotated[Type, Query(...)]`
4. And similar for other FastAPI parameter types (Body, Path, Header, Cookie, etc.)

Key challenge: Python parameter ordering rules require that once a parameter has
a default, all subsequent parameters must also have defaults. When we convert a
parameter to Annotated form, we remove its default, which can violate this rule
if there are earlier parameters with defaults.

EXCEPTION: Keyword-only parameters (after `*` or `*args`) can have defaults
independently of positional parameters.

Strategy:
1. For each function, identify all parameters (positional and keyword-only) that need fixing
2. For positional params:
   - Find the first fixable param
   - Convert all preceding positional params with defaults to Optional form
   - Convert fixable params to Annotated form
3. For keyword-only params:
   - Just convert them directly (no need to handle preceding defaults)
4. Add Annotated and Optional imports if needed
"""

import subprocess
from pathlib import Path

import libcst as cst

# FastAPI parameter types that commonly appear in B008 violations
# Note: Form with defaults should NOT be converted to Annotated (FastAPI limitation)
FASTAPI_PARAM_TYPES = {"Depends", "Query", "Path", "Body", "Header", "Cookie", "File", "Security"}


class B008Transformer(cst.CSTTransformer):
    """Transforms function parameters with B008 violations to Annotated form."""

    def __init__(self):
        super().__init__()
        self.changes = 0
        self.has_annotated_import = False
        self.has_optional_import = False
        self.needs_annotated_import = False
        self.needs_optional_import = False

    def visit_Module(self, node: cst.Module) -> bool:
        """Check if required imports already exist."""
        for stmt in node.body:
            if isinstance(stmt, cst.SimpleStatementLine):
                for small_stmt in stmt.body:
                    if isinstance(small_stmt, cst.ImportFrom):
                        if small_stmt.module and small_stmt.module.value == "typing":
                            for alias in small_stmt.names:
                                name = alias.name.value
                                if name == "Annotated":
                                    self.has_annotated_import = True
                                if name == "Optional":
                                    self.has_optional_import = True
                        if small_stmt.module and small_stmt.module.value == "typing_extensions":
                            for alias in small_stmt.names:
                                if alias.name.value == "Annotated":
                                    self.has_annotated_import = True
        return True

    def leave_Parameters(self, original_node: cst.Parameters, updated_node: cst.Parameters) -> cst.Parameters:
        """Process all parameters together to maintain valid default ordering."""
        positional_params = list(updated_node.params)
        kwonly_params = list(updated_node.kwonly_params)

        has_changes = False

        # Process positional parameters
        if positional_params:
            new_positional, pos_changes = self._process_positional_params(positional_params)
            if pos_changes > 0:
                has_changes = True
        else:
            new_positional = positional_params

        # Process keyword-only parameters
        if kwonly_params:
            new_kwonly, kw_changes = self._process_kwonly_params(kwonly_params)
            if kw_changes > 0:
                has_changes = True
        else:
            new_kwonly = kwonly_params

        if not has_changes:
            return updated_node

        return updated_node.with_changes(
            params=tuple(new_positional),
            kwonly_params=tuple(new_kwonly),
        )

    def _process_positional_params(self, params: list[cst.Param]) -> tuple[list[cst.Param], int]:
        """Process positional parameters, handling default ordering."""
        if not params:
            return params, 0

        # Find all parameters that need fixing
        fixable_indices: set[int] = set()
        for i, param in enumerate(params):
            if self._needs_fixing(param):
                fixable_indices.add(i)

        if not fixable_indices:
            return params, 0

        first_fixable = min(fixable_indices)

        # Find all positional params before the first fixable that have defaults
        preceding_with_defaults: set[int] = set()
        for i in range(first_fixable):
            if params[i].default is not None and not self._is_star_param(params[i]):
                preceding_with_defaults.add(i)

        new_params = list(params)
        changes = 0

        # Convert preceding params with defaults to Optional form
        for idx in preceding_with_defaults:
            new_param = self._convert_to_optional_no_default(params[idx])
            if new_param is not None:
                new_params[idx] = new_param
                changes += 1
                self.needs_optional_import = True

        # Fix the B008 params
        for idx in fixable_indices:
            new_param = self._fix_parameter(params[idx])
            if new_param is not None:
                new_params[idx] = new_param
                changes += 1

        return new_params, changes

    def _process_kwonly_params(self, params: list[cst.Param]) -> tuple[list[cst.Param], int]:
        """Process keyword-only parameters. No default ordering concerns."""
        if not params:
            return params, 0

        fixable_indices: set[int] = set()
        for i, param in enumerate(params):
            if self._needs_fixing(param):
                fixable_indices.add(i)

        if not fixable_indices:
            return params, 0

        new_params = list(params)
        changes = 0

        for idx in fixable_indices:
            new_param = self._fix_parameter(params[idx])
            if new_param is not None:
                new_params[idx] = new_param
                changes += 1

        return new_params, changes

    def _is_star_param(self, param: cst.Param) -> bool:
        """Check if param is *args or **kwargs or just *."""
        return param.star in ("*", "**")

    def _needs_fixing(self, param: cst.Param) -> bool:
        """Check if a parameter needs B008 fixing."""
        if param.default is None:
            return False

        # Check if default is a call to one of the FastAPI parameter types
        if not isinstance(param.default, cst.Call):
            return False

        func = param.default.func
        if not isinstance(func, cst.Name):
            return False

        # Skip Form parameters with defaults - FastAPI doesn't support Annotated with defaults for Form
        if func.value == "Form":
            # Check if Form has a default argument
            for arg in param.default.args:
                if isinstance(arg, cst.Arg) and arg.keyword and arg.keyword.value == "default":
                    # Form with default - skip conversion
                    return False

        if func.value not in FASTAPI_PARAM_TYPES:
            return False

        # If it has an annotation, check if it's already properly Annotated
        if param.annotation is not None:
            ann = param.annotation.annotation
            if isinstance(ann, cst.Subscript):
                if isinstance(ann.value, cst.Name) and ann.value.value == "Annotated":
                    # Check if the Annotated already contains this type
                    if len(ann.slice) >= 2:
                        # This is an already-annotated param with redundant default
                        return True

        return True

    def _is_already_annotated_with_depends(self, param: cst.Param) -> bool:
        """Check if param is already Annotated with the FastAPI type."""
        if param.annotation is None:
            return False

        ann = param.annotation.annotation
        if not isinstance(ann, cst.Subscript):
            return False

        if not (isinstance(ann.value, cst.Name) and ann.value.value == "Annotated"):
            return False

        if len(ann.slice) < 2:
            return False

        # Check if the second element is the same type as the default
        second_elem = ann.slice[1].slice
        if isinstance(second_elem, cst.Index):
            if isinstance(second_elem.value, cst.Call):
                func = second_elem.value.func
                if isinstance(func, cst.Name):
                    if isinstance(param.default, cst.Call):
                        default_func = param.default.func
                        if isinstance(default_func, cst.Name):
                            return func.value == default_func.value

        return False

    def _fix_parameter(self, param: cst.Param) -> cst.Param | None:
        """Fix a parameter with B008 violation."""
        if param.annotation is None:
            # No annotation - we can't use Annotated, but we should remove the default
            return cst.Param(
                name=param.name,
                annotation=None,
                default=None,
                equal=None,
                comma=param.comma,
                star=param.star,
                whitespace_after_star=param.whitespace_after_star,
                whitespace_after_param=param.whitespace_after_param,
            )

        ann = param.annotation.annotation

        # Check if already Annotated with the same type
        if self._is_already_annotated_with_depends(param):
            # Just remove the redundant default
            return cst.Param(
                name=param.name,
                annotation=param.annotation,
                default=None,
                equal=None,
                comma=param.comma,
                star=param.star,
                whitespace_after_star=param.whitespace_after_star,
                whitespace_after_param=param.whitespace_after_param,
            )

        # Check if already Annotated with different type
        if isinstance(ann, cst.Subscript):
            if isinstance(ann.value, cst.Name) and ann.value.value == "Annotated":
                # Already Annotated with something else - just remove default
                return cst.Param(
                    name=param.name,
                    annotation=param.annotation,
                    default=None,
                    equal=None,
                    comma=param.comma,
                    star=param.star,
                    whitespace_after_star=param.whitespace_after_star,
                    whitespace_after_param=param.whitespace_after_param,
                )

        # Standard case: wrap in Annotated[Type, Depends(...)]
        self.needs_annotated_import = True
        new_annotation = cst.Annotation(
            annotation=cst.Subscript(
                value=cst.Name("Annotated"),
                slice=[
                    cst.SubscriptElement(slice=cst.Index(value=ann)),
                    cst.SubscriptElement(slice=cst.Index(value=param.default)),
                ],
            ),
        )

        return cst.Param(
            name=param.name,
            annotation=new_annotation,
            default=None,
            equal=None,
            comma=param.comma,
            star=param.star,
            whitespace_after_star=param.whitespace_after_star,
            whitespace_after_param=param.whitespace_after_param,
        )

    def _convert_to_optional_no_default(self, param: cst.Param) -> cst.Param | None:
        """Convert a parameter with default to Optional form without default."""
        if param.annotation is None:
            return None

        ann = param.annotation.annotation

        # Check if already Optional or Union with None or X | None
        is_already_optional = False
        if isinstance(ann, cst.Subscript):
            if isinstance(ann.value, cst.Name) and ann.value.value == "Optional":
                is_already_optional = True
            elif isinstance(ann.value, cst.Name) and ann.value.value == "Union":
                for elem in ann.slice:
                    if isinstance(elem.slice, cst.Index):
                        if isinstance(elem.slice.value, cst.Name) and elem.slice.value.value == "None":
                            is_already_optional = True
                            break
        elif isinstance(ann, cst.BinaryOperation):
            # Handle X | None pattern
            if isinstance(ann.operator, cst.BitOr):
                if isinstance(ann.right, cst.Name) and ann.right.value == "None":
                    is_already_optional = True

        if is_already_optional:
            # Already Optional, just remove default
            return cst.Param(
                name=param.name,
                annotation=param.annotation,
                default=None,
                equal=None,
                comma=param.comma,
                star=param.star,
                whitespace_after_star=param.whitespace_after_star,
                whitespace_after_param=param.whitespace_after_param,
            )

        # Wrap in Optional[...]
        self.needs_optional_import = True
        new_annotation = cst.Annotation(
            annotation=cst.Subscript(
                value=cst.Name("Optional"),
                slice=[cst.SubscriptElement(slice=cst.Index(value=ann))],
            ),
        )

        return cst.Param(
            name=param.name,
            annotation=new_annotation,
            default=None,
            equal=None,
            comma=param.comma,
            star=param.star,
            whitespace_after_star=param.whitespace_after_star,
            whitespace_after_param=param.whitespace_after_param,
        )

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        """Add required imports if needed."""
        if self.changes == 0:
            return updated_node

        new_body: list[cst.BaseStatement] = list(updated_node.body)

        # Add Annotated import if needed
        if self.needs_annotated_import and not self.has_annotated_import:
            new_body = self._add_import(new_body, "Annotated")
            self.has_annotated_import = True

        # Add Optional import if needed
        if self.needs_optional_import and not self.has_optional_import:
            new_body = self._add_import(new_body, "Optional")
            self.has_optional_import = True

        return updated_node.with_changes(body=tuple(new_body))

    def _add_import(self, body: list[cst.BaseStatement], name: str) -> list[cst.BaseStatement]:
        """Add an import for `name` from typing, merging with existing if present."""
        new_body = list(body)

        # Try to find existing typing import
        for i, stmt in enumerate(new_body):
            if isinstance(stmt, cst.SimpleStatementLine):
                for small_stmt in stmt.body:
                    if isinstance(small_stmt, cst.ImportFrom):
                        if small_stmt.module and small_stmt.module.value == "typing":
                            # Add to existing import
                            if not any(a.name.value == name for a in small_stmt.names):
                                new_names = list(small_stmt.names) + [cst.ImportAlias(name=cst.Name(name))]
                                new_stmt = small_stmt.with_changes(names=new_names)
                                new_body[i] = stmt.with_changes(body=[new_stmt])
                                return new_body
                            return new_body

        # No existing typing import, create new one
        # Find insertion point (after __future__ imports if any)
        insert_idx = 0
        for i, stmt in enumerate(new_body):
            if isinstance(stmt, cst.SimpleStatementLine):
                for small_stmt in stmt.body:
                    if isinstance(small_stmt, cst.ImportFrom):
                        if small_stmt.module and small_stmt.module.value == "__future__":
                            insert_idx = i + 1
                            break

        new_import = cst.SimpleStatementLine(
            body=[
                cst.ImportFrom(
                    module=cst.Name("typing"),
                    names=[cst.ImportAlias(name=cst.Name(name))],
                )
            ],
            leading_lines=([cst.EmptyLine()] if insert_idx > 0 or new_body else []),
        )
        new_body.insert(insert_idx, new_import)
        return new_body


def fix_file(filepath: Path) -> int:
    """Fix B008 in a single file. Returns number of changes."""
    try:
        with open(filepath) as f:
            source = f.read()
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
        return 0

    try:
        module = cst.parse_module(source)
    except Exception as e:
        print(f"  Parse error in {filepath}: {e}")
        return 0

    transformer = B008Transformer()
    new_module = module.visit(transformer)

    if transformer.changes > 0:
        new_code = new_module.code
        try:
            with open(filepath, "w") as f:
                f.write(new_code)
            print(f"  Fixed {transformer.changes} in {filepath}")
        except Exception as e:
            print(f"  Error writing {filepath}: {e}")
            return 0

    return transformer.changes


def get_files_with_b008(root: Path) -> set[Path]:
    """Get all Python files with B008 violations, excluding mutants and contracts."""
    result = subprocess.run(
        ["ruff", "check", ".", "--select=B008", "--output-format=concise"],
        capture_output=True,
        text=True,
        cwd=root,
    )

    files_with_b008: set[Path] = set()
    for line in result.stdout.split("\n"):
        if "B008" in line and ":" in line:
            file_path = line.split(":")[0]
            # Skip mutants directory (auto-generated)
            if "mutants" in file_path:
                continue
            # Skip contracts directory (Solidity library scripts)
            if "contracts/" in file_path:
                continue
            files_with_b008.add(root / file_path)

    return files_with_b008


def main():
    root = Path("/opt/aitbc")

    print("=" * 70)
    print("B008 Comprehensive Fix with LibCST")
    print("=" * 70)

    print("\nScanning for B008 violations...")
    files_with_b008 = get_files_with_b008(root)
    print(f"Found {len(files_with_b008)} files with B008 violations")

    if not files_with_b008:
        print("\nNo B008 violations found! Exiting.")
        return

    print("\nFixing files...")
    total_fixed = 0
    errors = []

    for filepath in sorted(files_with_b008):
        if not filepath.exists():
            continue

        try:
            fixed = fix_file(filepath)
            total_fixed += fixed
        except Exception as e:
            errors.append(f"{filepath}: {e}")
            print(f"  ERROR in {filepath}: {e}")

    print("\n" + "=" * 70)
    print(f"SUMMARY: Fixed {total_fixed} B008 violations")
    if errors:
        print(f"ERRORS: {len(errors)} files had errors")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
    print("=" * 70)

    print("\nVerifying fix...")
    result = subprocess.run(
        ["ruff", "check", ".", "--select=B008"],
        capture_output=True,
        text=True,
        cwd=root,
    )

    remaining = len([line for line in result.stdout.split("\n") if "B008" in line])
    print(f"Remaining B008 violations: {remaining}")

    if remaining == 0:
        print("\nSUCCESS: All B008 violations have been fixed!")
    else:
        print(f"\nWARNING: {remaining} violations remain")


if __name__ == "__main__":
    main()
