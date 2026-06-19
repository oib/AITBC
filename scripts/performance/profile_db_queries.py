#!/usr/bin/env python3
"""
DB Query Profiling Script for Coordinator API

Analyzes database queries in routers for N+1 issues and provides recommendations.
"""

import ast
import sys
from pathlib import Path


def analyze_file_for_db_queries(file_path: Path) -> dict[str, any]:
    """Analyze a Python file for database query patterns."""
    results = {
        "file": str(file_path),
        "session_execute_count": 0,
        "session_query_count": 0,
        "potential_n_plus_1": [],
        "lines_with_queries": [],
    }

    content = file_path.read_text()
    lines = content.split("\n")

    for i, line in enumerate(lines, 1):
        if "session.execute" in line:
            results["session_execute_count"] += 1
            results["lines_with_queries"].append((i, line.strip()))

        if "session.query" in line:
            results["session_query_count"] += 1
            results["lines_with_queries"].append((i, line.strip()))

    # Check for potential N+1 patterns (session.execute inside loops)
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.For) or isinstance(node, ast.While):
                # Check if there's a session.execute in the loop body
                loop_lines = set()
                for child in ast.walk(node):
                    if hasattr(child, "lineno"):
                        loop_lines.add(child.lineno)

                for line_num, line_content in results["lines_with_queries"]:
                    if line_num in loop_lines:
                        results["potential_n_plus_1"].append((line_num, line_content))
    except SyntaxError:
        pass

    return results


def main() -> int:
    """Main profiling function."""
    routers_dir = Path("/opt/aitbc/apps/coordinator-api/src/app/routers")
    services_dir = Path("/opt/aitbc/apps/coordinator-api/src/app/services")

    print("=" * 60)
    print("DB Query Profiling for Coordinator API")
    print("=" * 60)
    print()

    all_results = []

    # Analyze routers
    if routers_dir.exists():
        for py_file in routers_dir.rglob("*.py"):
            result = analyze_file_for_db_queries(py_file)
            if result["session_execute_count"] > 0 or result["session_query_count"] > 0:
                all_results.append(result)

    # Analyze services
    if services_dir.exists():
        for py_file in services_dir.rglob("*.py"):
            result = analyze_file_for_db_queries(py_file)
            if result["session_execute_count"] > 0 or result["session_query_count"] > 0:
                all_results.append(result)

    # Print results
    total_execute = sum(r["session_execute_count"] for r in all_results)
    total_query = sum(r["session_query_count"] for r in all_results)
    total_n_plus_1 = sum(len(r["potential_n_plus_1"]) for r in all_results)

    print(f"Total files with DB queries: {len(all_results)}")
    print(f"Total session.execute() calls: {total_execute}")
    print(f"Total session.query() calls: {total_query}")
    print(f"Potential N+1 issues: {total_n_plus_1}")
    print()

    if total_n_plus_1 > 0:
        print("⚠️  POTENTIAL N+1 ISSUES FOUND:")
        print()
        for result in all_results:
            if result["potential_n_plus_1"]:
                print(f"File: {result['file']}")
                for line_num, line_content in result["potential_n_plus_1"]:
                    print(f"  Line {line_num}: {line_content}")
                print()
    else:
        print("✅ No N+1 issues detected")
        print()

    print("Files with DB queries:")
    for result in all_results:
        print(f"  {result['file']}:")
        print(f"    session.execute: {result['session_execute_count']}")
        print(f"    session.query: {result['session_query_count']}")
        if result["lines_with_queries"]:
            print(f"    Query lines: {[ln for ln, _ in result['lines_with_queries'][:5]]}")
        print()

    print("=" * 60)
    print("Profiling Complete")
    print("=" * 60)

    return 0 if total_n_plus_1 == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
