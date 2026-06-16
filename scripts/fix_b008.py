#!/usr/bin/env python3
"""
Automated B008 fix for FastAPI Depends in default arguments.
Replaces: `param: Type = Depends(dep_func)`
With: `param: Annotated[Type, Depends(dep_func)]`
"""

import re
from pathlib import Path


def has_annotated_import(content: str) -> bool:
    """Check if 'from typing import Annotated' or 'import Annotated from typing' exists."""
    patterns = [
        r"from typing import.*\bAnnotated\b",
        r"import typing.*\bAnnotated\b",
        r"^from typing_extensions import.*\bAnnotated\b",
    ]
    for pattern in patterns:
        if re.search(pattern, content, re.MULTILINE):
            return True
    return False


def add_annotated_import(content: str) -> str:
    """Add Annotated import to typing imports."""
    # Try to find existing typing import and add Annotated
    typing_import_pattern = r"^(from typing import\s+)([^\n]+)$"

    def repl(match):
        imports = match.group(2)
        if "Annotated" not in imports:
            return f"{match.group(1)}{imports}, Annotated"
        return match.group(0)

    new_content = re.sub(typing_import_pattern, repl, content, flags=re.MULTILINE)

    # If no typing import found, add one after other imports
    if new_content == content:
        # Find the last import line
        import_lines = list(re.finditer(r"^(?:from|import)\s+", content, re.MULTILINE))
        if import_lines:
            last_import = import_lines[-1]
            insert_pos = last_import.end()
            new_content = content[:insert_pos] + "\nfrom typing import Annotated" + content[insert_pos:]
        else:
            # No imports at all, add at top
            new_content = "from typing import Annotated\n" + content

    return new_content


def fix_b008_in_file(file_path: Path) -> tuple[int, str]:
    """Fix B008 violations in a single file. Returns (count_fixed, new_content)."""
    content = file_path.read_text()
    fixed_count = 0

    # Pattern: param: Type = Depends(something)
    # Could have Union, Optional, List, Dict, etc.
    # Match: param: Type = Depends(...)
    # where Type could be complex (Union[...], Optional[...], etc.)

    # More precise pattern: parameter with type annotation and = Depends(...)

    def replace_dep(match):
        nonlocal fixed_count
        full_match = match.group(0)
        param_name = match.group(2)
        type_annotation = match.group(3).strip()

        # Skip if already Annotated
        if type_annotation.startswith("Annotated["):
            return full_match

        # Skip if it's not a simple type (has complex default that's not Depends)
        if "=" in type_annotation and "Depends" not in full_match:
            return full_match

        fixed_count += 1
        return (
            f"{param_name}: Annotated[{type_annotation}, Depends(match.group(4))]"
            if False
            else f"{param_name}: Annotated[{type_annotation}, {match.group(0).split('=')[1].strip()}]"
        )

    # Use a more careful approach - find = Depends( pattern
    # We need to handle multi-line Depends calls
    lines = content.split("\n")
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for pattern: param: Type = Depends(
        # Could be on single line or multi-line
        if "= Depends(" in line and ":" in line.split("=")[0]:
            # Found a B008 candidate
            # Check if already Annotated
            if "Annotated[" not in line:
                # Try to fix on this line
                # Pattern: param: Type = Depends(...)
                param_part = line.split("=")[0].strip()
                dep_part = "=" + "=".join(line.split("=")[1:])

                # Extract param name and type
                if ":" in param_part:
                    name_type = param_part.strip()
                    # Replace: name: Type = Depends(...) -> name: Annotated[Type, Depends(...)]
                    new_line = f"{name_type.rstrip()}: Annotated[{name_type.split(':')[1].strip()}, {dep_part.strip()}]"

                    # Check if we need to add Annotated import
                    if not has_annotated_import("\n".join(new_lines + [line] + lines[i + 1 :])):
                        pass  # Will add at the end

                    new_lines.append(new_line)
                    fixed_count += 1
                    i += 1
                    continue

        new_lines.append(line)
        i += 1

    new_content = "\n".join(new_lines)

    # Add Annotated import if fixes were made
    if fixed_count > 0 and not has_annotated_import(new_content):
        new_content = add_annotated_import(new_content)

    return fixed_count, new_content


def main():
    root = Path("/opt/aitbc")

    # Get all Python files with B008
    result = subprocess.run(
        ["ruff", "check", ".", "--select=B008", "--output-format=concise"], capture_output=True, text=True, cwd=root
    )

    # Parse file paths
    files_with_b008 = set()
    for line in result.stdout.split("\n"):
        if "B008" in line and ":" in line:
            file_path = line.split(":")[0]
            files_with_b008.add(root / file_path)

    print(f"Found {len(files_with_b008)} files with B008 violations")

    total_fixed = 0
    for file_path in sorted(files_with_b008):
        if not file_path.exists():
            continue

        fixed, new_content = fix_b008_in_file(file_path)
        if fixed > 0:
            file_path.write_text(new_content)
            print(f"  Fixed {fixed} in {file_path}")
            total_fixed += fixed

    print(f"Total fixed: {total_fixed}")


if __name__ == "__main__":
    import subprocess

    main()
