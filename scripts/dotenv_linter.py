#!/usr/bin/env python3
"""
Dotenv Linter for AITBC

This script checks for configuration drift between .env.example and actual
environment variable usage in the codebase. It ensures that all environment
variables used in the code are documented in .env.example and vice versa.

Usage:
    python scripts/dotenv_linter.py
    python scripts/dotenv_linter.py --fix
    python scripts/dotenv_linter.py --verbose
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Set, Dict, List, Tuple
import ast
import subprocess


class DotenvLinter:
    """Linter for .env files and environment variable usage."""
    
    def __init__(self, project_root: Path = None):
        """Initialize the linter."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.env_example_path = self.project_root / ".env.example"
        self.python_files = self._find_python_files()
        
    def _find_python_files(self) -> List[Path]:
        """Find all Python files in the project."""
        python_files = []
        for root, dirs, files in os.walk(self.project_root):
            # Skip hidden directories and common exclusions
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                '__pycache__', 'node_modules', '.git', 'venv', 'env', '.venv'
            }]
            
            for file in files:
                if file.endswith('.py'):
                    python_files.append(Path(root) / file)
        
        return python_files
    
    def _parse_env_example(self) -> Set[str]:
        """Parse .env.example and extract all environment variable keys."""
        env_vars = set()
        
        if not self.env_example_path.exists():
            print(f"❌ .env.example not found at {self.env_example_path}")
            return env_vars
        
        with open(self.env_example_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Extract variable name (everything before =)
                if '=' in line:
                    var_name = line.split('=')[0].strip()
                    if var_name:
                        env_vars.add(var_name)
        
        return env_vars
    
    def _find_env_usage_in_python(self) -> Set[str]:
        """Find all environment variable usage in Python files."""
        env_vars = set()
        
        # Patterns to search for
        patterns = [
            r'os\.environ\.get\([\'"]([^\'"]+)[\'"]',
            r'os\.environ\[([\'"]([^\'"]+)[\'"])\]',
            r'os\.getenv\([\'"]([^\'"]+)[\'"]',
            r'getenv\([\'"]([^\'"]+)[\'"]',
            r'environ\.get\([\'"]([^\'"]+)[\'"]',
            r'environ\[([\'"]([^\'"]+)[\'"])\]',
        ]
        
        for python_file in self.python_files:
            try:
                with open(python_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                for pattern in patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        var_name = match.group(1)
                        env_vars.add(var_name)
                        
            except (UnicodeDecodeError, PermissionError) as e:
                print(f"⚠️  Could not read {python_file}: {e}")
        
        return env_vars
    
    def _find_env_usage_in_config_files(self) -> Set[str]:
        """Find environment variable usage in configuration files."""
        env_vars = set()
        
        # Check common config files
        config_files = [
            'pyproject.toml',
            'pytest.ini',
            'setup.cfg',
            'tox.ini',
            '.github/workflows/*.yml',
            '.github/workflows/*.yaml',
            'docker-compose.yml',
            'docker-compose.yaml',
            'Dockerfile',
        ]
        
        for pattern in config_files:
            for config_file in self.project_root.glob(pattern):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Look for environment variable patterns
                    env_patterns = [
                        r'\${([A-Z_][A-Z0-9_]*)}',  # ${VAR_NAME}
                        r'\$([A-Z_][A-Z0-9_]*)',     # $VAR_NAME
                        r'env\.([A-Z_][A-Z0-9_]*)',    # env.VAR_NAME
                        r'os\.environ\([\'"]([^\'"]+)[\'"]',  # os.environ("VAR_NAME")
                        r'getenv\([\'"]([^\'"]+)[\'"]',      # getenv("VAR_NAME")
                    ]
                    
                    for env_pattern in env_patterns:
                        matches = re.finditer(env_pattern, content)
                        for match in matches:
                            var_name = match.group(1) if match.groups() else match.group(0)
                            if var_name.isupper():
                                env_vars.add(var_name)
                                
                except (UnicodeDecodeError, PermissionError) as e:
                    print(f"⚠️  Could not read {config_file}: {e}")
        
        return env_vars
    
    def _find_env_usage_in_shell_scripts(self) -> Set[str]:
        """Find environment variable usage in shell scripts."""
        env_vars = set()
        
        shell_files = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                '__pycache__', 'node_modules', '.git', 'venv', 'env', '.venv'
            }]
            
            for file in files:
                if file.endswith(('.sh', '.bash', '.zsh')):
                    shell_files.append(Path(root) / file)
        
        for shell_file in shell_files:
            try:
                with open(shell_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Look for environment variable patterns in shell scripts
                patterns = [
                    r'\$\{([A-Z_][A-Z0-9_]*)\}',  # ${VAR_NAME}
                    r'\$([A-Z_][A-Z0-9_]*)',     # $VAR_NAME
                    r'export\s+([A-Z_][A-Z0-9_]*)=',  # export VAR_NAME=
                    r'([A-Z_][A-Z0-9_]*)=',        # VAR_NAME=
                ]
                
                for pattern in patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        var_name = match.group(1)
                        env_vars.add(var_name)
                        
            except (UnicodeDecodeError, PermissionError) as e:
                print(f"⚠️  Could not read {shell_file}: {e}")
        
        return env_vars
    
    def _find_all_env_usage(self) -> Set[str]:
        """Find all environment variable usage across the project."""
        all_vars = set()
        
        # Python files
        python_vars = self._find_env_usage_in_python()
        all_vars.update(python_vars)
        
        # Config files
        config_vars = self._find_env_usage_in_config_files()
        all_vars.update(config_vars)
        
        # Shell scripts
        shell_vars = self._find_env_usage_in_shell_scripts()
        all_vars.update(shell_vars)
        
        return all_vars
    
    def _check_missing_in_example(self, used_vars: Set[str], example_vars: Set[str]) -> Set[str]:
        """Find variables used in code but missing from .env.example."""
        missing = used_vars - example_vars
        
        # Filter out common system variables that don't need to be in .env.example
        system_vars = {
            'PATH', 'HOME', 'USER', 'SHELL', 'TERM', 'LANG', 'LC_ALL',
            'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_DEFAULT_ENV',
            'GITHUB_ACTIONS', 'CI', 'TRAVIS', 'APPVEYOR', 'CIRCLECI',
            'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy',
            'PWD', 'OLDPWD', 'SHLVL', '_', 'HOSTNAME', 'HOSTTYPE', 'OSTYPE',
            'MACHTYPE', 'UID', 'GID', 'EUID', 'EGID', 'PS1', 'PS2', 'IFS',
            'DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SSH_AUTH_SOCK',
            'SSH_CONNECTION', 'SSH_CLIENT', 'SSH_TTY', 'LOGNAME', 'USERNAME'
        }
        
        return missing - system_vars
    
    def _check_unused_in_example(self, used_vars: Set[str], example_vars: Set[str]) -> Set[str]:
        """Find variables in .env.example but not used in code."""
        unused = example_vars - used_vars
        
        # Filter out variables that might be used by external tools or services
        external_vars = {
            'NODE_ENV', 'NPM_CONFIG_PREFIX', 'NPM_AUTH_TOKEN',
            'DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
            'KUBERNETES_SERVICE_HOST', 'KUBERNETES_SERVICE_PORT',
            'REDIS_URL', 'MEMCACHED_URL', 'ELASTICSEARCH_URL',
            'SENTRY_DSN', 'ROLLBAR_ACCESS_TOKEN', 'HONEYBADGER_API_KEY'
        }
        
        return unused - external_vars
    
    def lint(self, verbose: bool = False) -> Tuple[int, int, int, Set[str], Set[str]]:
        """Run the linter and return results."""
        print("🔍 Dotenv Linter for AITBC")
        print("=" * 50)
        
        # Parse .env.example
        example_vars = self._parse_env_example()
        if verbose:
            print(f"📄 Found {len(example_vars)} variables in .env.example")
            if example_vars:
                print(f"   {', '.join(sorted(example_vars))}")
        
        # Find all environment variable usage
        used_vars = self._find_all_env_usage()
        if verbose:
            print(f"🔍 Found {len(used_vars)} variables used in code")
            if used_vars:
                print(f"   {', '.join(sorted(used_vars))}")
        
        # Check for missing variables
        missing_vars = self._check_missing_in_example(used_vars, example_vars)
        
        # Check for unused variables
        unused_vars = self._check_unused_in_example(used_vars, example_vars)
        
        return len(example_vars), len(used_vars), len(missing_vars), missing_vars, unused_vars
    
    def fix_env_example(self, missing_vars: Set[str], verbose: bool = False):
        """Add missing variables to .env.example."""
        if not missing_vars:
            if verbose:
                print("✅ No missing variables to add")
            return
        
        print(f"🔧 Adding {len(missing_vars)} missing variables to .env.example")
        
        with open(self.env_example_path, 'a') as f:
            f.write("\n# Auto-generated variables (added by dotenv_linter)\n")
            for var in sorted(missing_vars):
                f.write(f"{var}=\n")
        
        print(f"✅ Added {len(missing_vars)} variables to .env.example")
    
    def generate_report(self, example_count: int, used_count: int, missing_count: int, 
                        missing_vars: Set[str], unused_vars: Set[str]) -> str:
        """Generate a detailed report."""
        report = []
        
        report.append("📊 Dotenv Linter Report")
        report.append("=" * 50)
        report.append(f"Variables in .env.example: {example_count}")
        report.append(f"Variables used in code: {used_count}")
        report.append(f"Missing from .env.example: {missing_count}")
        report.append(f"Unused in .env.example: {len(unused_vars)}")
        report.append("")
        
        if missing_vars:
            report.append("❌ Missing Variables (used in code but not in .env.example):")
            for var in sorted(missing_vars):
                report.append(f"   - {var}")
            report.append("")
        
        if unused_vars:
            report.append("⚠️  Unused Variables (in .env.example but not used in code):")
            for var in sorted(unused_vars):
                report.append(f"   - {var}")
            report.append("")
        
        if not missing_vars and not unused_vars:
            report.append("✅ No configuration drift detected!")
        
        return "\n".join(report)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Dotenv Linter for AITBC - Check for configuration drift",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/dotenv_linter.py              # Check for drift
  python scripts/dotenv_linter.py --verbose    # Verbose output
  python scripts/dotenv_linter.py --fix        # Auto-fix missing variables
  python scripts/dotenv_linter.py --check      # Exit with error code on issues
        """
    )
    
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing variables in .env.example")
    parser.add_argument("--check", action="store_true", help="Exit with error code if issues found")
    
    args = parser.parse_args()
    
    # Initialize linter
    linter = DotenvLinter()
    
    # Run linting
    example_count, used_count, missing_count, missing_vars, unused_vars = linter.lint(args.verbose)
    
    # Generate report
    report = linter.generate_report(example_count, used_count, missing_count, missing_vars, unused_vars)
    print(report)
    
    # Auto-fix if requested
    if args.fix and missing_vars:
        linter.fix_env_example(missing_vars, args.verbose)
    
    # Exit with error code if check requested and issues found
    if args.check and (missing_vars or unused_vars):
        print(f"❌ Configuration drift detected: {missing_count} missing, {len(unused_vars)} unused")
        sys.exit(1)
    
    # Success
    print("✅ Dotenv linter completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
