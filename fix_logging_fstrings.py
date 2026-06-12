#!/usr/bin/env python3
"""Automatically convert f-strings in logging statements to lazy % formatting."""

import ast
import re
import sys
from pathlib import Path

# Common logging function names
LOGGING_FUNCTIONS = {
    'debug', 'info', 'warning', 'warn', 'error', 'exception', 'critical', 'log'
}


class LoggingFStringTransformer(ast.NodeTransformer):
    """AST transformer to convert f-strings in logging calls to lazy % formatting."""

    def __init__(self):
        self.changes_made = 0

    def visit_Call(self, node):
        """Visit function calls and transform logging f-strings."""
        # Check if this is a logging call
        if not isinstance(node.func, ast.Attribute):
            return node

        func_name = node.func.attr
        if func_name not in LOGGING_FUNCTIONS:
            return node

        # Check if the first argument is an f-string
        if not node.args:
            return node

        first_arg = node.args[0]
        if not isinstance(first_arg, ast.JoinedStr):
            return node

        # Convert f-string to % formatting
        self.changes_made += 1
        return self._convert_fstring_to_percent(node, first_arg)

    def _convert_fstring_to_percent(self, call_node, fstring_node):
        """Convert an f-string logging call to % formatting."""
        # Extract the format string and values
        format_parts = []
        values = []

        for value in fstring_node.values:
            if isinstance(value, ast.Constant):
                # Literal string part
                format_parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                # Interpolated value
                format_parts.append('%s')
                values.append(value.value)

        # Create the new format string
        format_string = ''.join(format_parts)

        # Build the new call node
        new_args = [ast.Constant(value=format_string)]
        new_args.extend(values)

        # Create a new Call node with the same function but new arguments
        new_call = ast.Call(
            func=call_node.func,
            args=new_args,
            keywords=call_node.keywords
        )

        # Copy location info
        ast.copy_location(new_call, call_node)
        ast.fix_missing_locations(new_call)

        return new_call


def fix_file(file_path: Path) -> int:
    """Fix f-strings in logging statements in a single file."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return 0

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        return 0

    transformer = LoggingFStringTransformer()
    new_tree = transformer.visit(tree)

    if transformer.changes_made == 0:
        return 0

    # Generate the new code
    new_content = ast.unparse(new_tree)

    # Write back
    file_path.write_text(new_content, encoding='utf-8')
    return transformer.changes_made


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: fix_logging_fstrings.py <directory>")
        sys.exit(1)

    base_dir = Path(sys.argv[1])
    if not base_dir.exists():
        print(f"Directory not found: {base_dir}")
        sys.exit(1)

    total_changes = 0
    total_files = 0

    for py_file in base_dir.rglob('*.py'):
        changes = fix_file(py_file)
        if changes > 0:
            total_changes += changes
            total_files += 1
            print(f"Fixed {changes} error(s) in {py_file}")

    print(f"\nTotal: {total_changes} errors fixed in {total_files} files")


if __name__ == '__main__':
    main()
