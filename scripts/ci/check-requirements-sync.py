#!/usr/bin/env python3
"""
Check that requirements.txt is in sync with pyproject.toml.

This script compares the parsed dependencies from pyproject.toml with
the requirements.txt file to ensure they match. It's used in CI to
prevent drift between the Poetry source of truth and the generated
requirements file used for CI compatibility.
"""

import sys
import re
from pathlib import Path
from typing import Dict, List

def parse_requirements_txt(req_path: Path) -> Dict[str, str]:
    """Parse requirements.txt into a dict of package: version_spec."""
    deps = {}
    with open(req_path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            # Parse package name and version spec
            # Handles: package>=1.0.0, package==1.0.0, package
            match = re.match(r'^([a-zA-Z0-9_-]+)([><=!~]+.+)?$', line)
            if match:
                pkg, version = match.groups()
                deps[pkg.lower()] = version or ''
    return deps

def parse_pyproject_toml(pyproject_path: Path) -> Dict[str, str]:
    """Parse pyproject.toml dependencies into a dict of package: version_spec."""
    deps = {}
    with open(pyproject_path) as f:
        content = f.read()
        # Extract dependencies section
        deps_match = re.search(r'\[tool\.poetry\.dependencies\](.*?)(?:\[|\Z)', content, re.DOTALL)
        if deps_match:
            deps_section = deps_match.group(1)
            for line in deps_section.split('\n'):
                line = line.strip()
                # Skip comments, empty lines, and python = line
                if not line or line.startswith('#') or line.startswith('python ='):
                    continue
                # Parse package name and version spec
                match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*"(.+?)"', line)
                if match:
                    pkg, version = match.groups()
                    deps[pkg.lower()] = version
    return deps

def main():
    repo_root = Path(__file__).resolve().parents[2]
    req_path = repo_root / "requirements.txt"
    pyproject_path = repo_root / "pyproject.toml"

    if not req_path.exists():
        print(f"ERROR: {req_path} not found")
        sys.exit(1)

    if not pyproject_path.exists():
        print(f"ERROR: {pyproject_path} not found")
        sys.exit(1)

    req_deps = parse_requirements_txt(req_path)
    pyproject_deps = parse_pyproject_toml(pyproject_path)

    # Check for packages in requirements.txt not in pyproject.toml
    extra_in_req = set(req_deps.keys()) - set(pyproject_deps.keys())
    if extra_in_req:
        print(f"ERROR: Packages in requirements.txt but not in pyproject.toml: {extra_in_req}")
        sys.exit(1)

    # Check for packages in pyproject.toml not in requirements.txt
    extra_in_pyproject = set(pyproject_deps.keys()) - set(req_deps.keys())
    if extra_in_pyproject:
        print(f"ERROR: Packages in pyproject.toml but not in requirements.txt: {extra_in_pyproject}")
        sys.exit(1)

    # Check version mismatches
    version_mismatches = []
    for pkg in req_deps:
        if req_deps[pkg] != pyproject_deps[pkg]:
            # Normalize comparison (>= vs >=, etc.)
            req_ver = req_deps[pkg].replace('>=', '>=').replace('==', '==')
            py_ver = pyproject_deps[pkg].replace('>=', '>=').replace('==', '==')
            if req_ver != py_ver:
                version_mismatches.append(f"{pkg}: requirements.txt={req_deps[pkg]}, pyproject.toml={pyproject_deps[pkg]}")

    if version_mismatches:
        print("ERROR: Version mismatches between requirements.txt and pyproject.toml:")
        for mismatch in version_mismatches:
            print(f"  - {mismatch}")
        print("\nTo fix, run: pip-compile pyproject.toml")
        sys.exit(1)

    print("OK: requirements.txt is in sync with pyproject.toml")
    sys.exit(0)

if __name__ == "__main__":
    main()
