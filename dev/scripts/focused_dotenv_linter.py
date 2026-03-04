#!/usr/bin/env python3
"""
Focused Dotenv Linter for AITBC

This script specifically checks for environment variable usage patterns that
actually require .env.example documentation, filtering out script variables and
other non-environment variable patterns.

Usage:
    python scripts/focused_dotenv_linter.py
    python scripts/focused_dotenv_linter.py --fix
    python scripts/focused_dotenv_linter.py --verbose
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Set, Dict, List, Tuple
import ast


class FocusedDotenvLinter:
    """Focused linter for actual environment variable usage."""
    
    def __init__(self, project_root: Path = None):
        """Initialize the linter."""
        self.project_root = project_root or Path(__file__).parent.parent
        self.env_example_path = self.project_root / ".env.example"
        self.python_files = self._find_python_files()
        
        # Common script/internal variables to ignore
        self.script_vars = {
            'PID', 'PIDS', 'PID_FILE', 'CHILD_PIDS', 'API_PID', 'COORD_PID', 'MARKET_PID',
            'EXCHANGE_PID', 'NODE_PID', 'API_STATUS', 'FRONTEND_STATUS', 'CONTRACTS_STATUS',
            'NODE1_HEIGHT', 'NODE2_HEIGHT', 'NODE3_HEIGHT', 'NEW_NODE1_HEIGHT',
            'NEW_NODE2_HEIGHT', 'NEW_NODE3_HEIGHT', 'NODE3_STATUS', 'NODE3_NEW_STATUS',
            'OLD_DIFF', 'NEW_DIFF', 'DIFF12', 'DIFF23', 'NEW_DIFF', 'DIFF',
            'COVERAGE', 'MYTHRIL_REPORT', 'MYTHRIL_TEXT', 'SLITHER_REPORT', 'SLITHER_TEXT',
            'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_STEP_SUMMARY', 'PYTEST_CURRENT_TEST',
            'NC', 'REPLY', 'RUNNER', 'TIMESTAMP', 'DATE', 'VERSION', 'SCRIPT_VERSION',
            'VERBOSE', 'DEBUG', 'DRY_RUN', 'AUTO_MODE', 'DEV_MODE', 'TEST_MODE',
            'PRODUCTION_MODE', 'ENVIRONMENT', 'APP_ENV', 'NODE_ENV', 'LIVE_SERVER',
            'LOCAL_MODEL_PATH', 'FASTTEXT_MODEL_PATH', 'BUILD_DIR', 'OUTPUT_DIR',
            'TEMP_DIR', 'TEMP_DEPLOY_DIR', 'BACKUP_DIR', 'BACKUP_FILE', 'BACKUP_NAME',
            'LOG_DIR', 'MONITORING_DIR', 'REPORT_DIR', 'DOCS_DIR', 'SCRIPTS_DIR',
            'SCRIPT_DIR', 'CONFIG_DIR', 'CONFIGS_DIR', 'CONFIGS', 'PACKAGES_DIR',
            'SERVICES_DIR', 'CONTRACTS_DIR', 'INFRA_DIR', 'FRONTEND_DIR', 'EXCHANGE_DIR',
            'EXPLORER_DIR', 'ROOT_DIR', 'PROJECT_ROOT', 'PROJECT_DIR', 'SOURCE_DIR',
            'VENV_DIR', 'INSTALL_DIR', 'DEBIAN_DIR', 'DEB_OUTPUT_DIR', 'DIST_DIR',
            'LEGACY_DIR', 'MIGRATION_EXAMPLES_DIR', 'GPU_ACCEL_DIR', 'ZK_DIR',
            'WHEEL_FILE', 'PACKAGE_FILE', 'PACKAGE_NAME', 'PACKAGE_VERSION', 'PACKAGE_PATH',
            'PACKAGE_SIZE', 'PKG_NAME', 'PKG_VERSION', 'PKG_PATH', 'PKG_IDENTIFIER',
            'PKG_INSTALL_LOCATION', 'PKG_MANAGER', 'PKG_PATHS', 'CUSTOM_PACKAGES',
            'SELECTED_PACKAGES', 'COMPONENTS', 'PHASES', 'REQUIRED_VERSION',
            'SCRIPTS', 'SERVICES', 'SERVERS', 'CONTAINER', 'CONTAINER_NAME', 'CONTAINER_IP',
            'DOMAIN', 'PORT', 'HOST', 'SERVER', 'SERVICE_NAME', 'NAMESPACE',
            'CLIENT_ID', 'CLIENT_REGION', 'CLIENT_KEY', 'CLIENT_WALLET', 'MINER_ID',
            'MINER_REGION', 'MINER_KEY', 'MINER_WALLET', 'AGENT_TYPE', 'CATEGORY',
            'NETWORK', 'CHAIN', 'CHAINS', 'CHAIN_ID', 'SUPPORTED_CHAINS',
            'NODE1', 'NODE2', 'NODE3', 'NODE_MAP', 'NODE1_CONFIG', 'NODE1_DIR',
            'NODE2_DIR', 'NODE3_DIR', 'NODE_ENV', 'PLATFORM', 'ARCH', 'ARCH_NAME',
            'CHIP_FAMILY', 'PYTHON_VERSION', 'BASH_VERSION', 'ZSH_VERSION',
            'DEBIAN_VERSION', 'SHELL_PROFILE', 'SHELL_RC', 'POWERSHELL_PROFILE',
            'SYSTEMD_PATH', 'WSL_SCRIPT_DIR', 'SSH_KEY', 'SSH_USER', 'SSL_CERT_PATH',
            'SSL_KEY_PATH', 'SSL_ENABLED', 'NGINX_CONFIG', 'WEB_ROOT', 'WEBHOOK_SECRET',
            'WORKERS', 'AUTO_SCALING', 'MAX_INSTANCES', 'MIN_INSTANCES', 'EMERGENCY_ONLY',
            'SKIP_BUILD', 'SKIP_TESTS', 'SKIP_SECURITY', 'SKIP_MONITORING', 'SKIP_VERIFICATION',
            'SKIP_FRONTEND', 'RESET', 'UPDATE', 'UPDATE_ALL', 'UPDATE_CLI', 'UPDATE_SERVICES',
            'INSTALL_CLI', 'INSTALL_SERVICES', 'UNINSTALL', 'UNINSTALL_CLI_ONLY',
            'UNINSTALL_SERVICES_ONLY', 'DEPLOY_CONTRACTS', 'DEPLOY_FRONTEND', 'DEPLOY_SERVICES',
            'BACKUP_BEFORE_DEPLOY', 'DEPLOY_PATH', 'COMPLETE_INSTALL', 'DIAGNOSE',
            'HEALTH_CHECK', 'HEALTH_URL', 'RUN_MYTHRIL', 'RUN_SLITHER', 'TEST_CONTRACTS',
            'VERIFY_CONTRACTS', 'SEND_AMOUNT', 'RETURN_ADDRESS', 'TXID', 'BALANCE',
            'MINT_PER_UNIT', 'MIN_CONFIRMATIONS', 'PRODUCTION_GAS_LIMIT', 'PRODUCTION_GAS_PRICE',
            'PRIVATE_KEY', 'PRODUCTION_PRIVATE_KEY', 'PROPOSER_KEY', 'ENCRYPTION_KEY',
            'BITCOIN_ADDRESS', 'BITCOIN_PRIVATE_KEY', 'BITCOIN_TESTNET', 'BTC_TO_AITBC_RATE',
            'VITE_APP_NAME', 'VITE_APP_VERSION', 'VITE_APP_DESCRIPTION', 'VITE_NETWORK_NAME',
            'VITE_CHAIN_ID', 'VITE_RPC_URL', 'VITE_WS_URL', 'VITE_API_BASE_URL',
            'VITE_ENABLE_ANALYTICS', 'VITE_ENABLE_ERROR_REPORTING', 'VITE_SENTRY_DSN',
            'VITE_AGENT_BOUNTY_ADDRESS', 'VITE_AGENT_STAKING_ADDRESS', 'VITE_AITBC_TOKEN_ADDRESS',
            'VITE_DISPUTE_RESOLUTION_ADDRESS', 'VITE_PERFORMANCE_VERIFIER_ADDRESS',
            'VITE_ESCROW_SERVICE_ADDRESS', 'COMPREHENSIVE', 'HIGH', 'MEDIUM', 'LOW',
            'RED', 'GREEN', 'YELLOW', 'BLUE', 'MAGENTA', 'CYAN', 'PURPLE', 'WHITE',
            'NC', 'EDITOR', 'PAGER', 'LANG', 'LC_ALL', 'TERM', 'SHELL', 'USER', 'HOME',
            'PATH', 'PWD', 'OLDPWD', 'SHLVL', '_', 'HOSTNAME', 'HOSTTYPE', 'OSTYPE',
            'MACHTYPE', 'UID', 'GID', 'EUID', 'EGID', 'PS1', 'PS2', 'IFS', 'DISPLAY',
            'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SSH_AUTH_SOCK', 'SSH_CONNECTION',
            'SSH_CLIENT', 'SSH_TTY', 'LOGNAME', 'USERNAME', 'CURRENT_USER'
        }
        
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
        """Find actual environment variable usage in Python files."""
        env_vars = set()
        
        # More specific patterns for actual environment variables
        patterns = [
            r'os\.environ\.get\([\'"]([A-Z_][A-Z0-9_]*)[\'"]',
            r'os\.environ\[([\'"]([A-Z_][A-Z0-9_]*)[\'"])\]',
            r'os\.getenv\([\'"]([A-Z_][A-Z0-9_]*)[\'"]',
            r'getenv\([\'"]([A-Z_][A-Z0-9_]*)[\'"]',
            r'environ\.get\([\'"]([A-Z_][A-Z0-9_]*)[\'"]',
            r'environ\[([\'"]([A-Z_][A-Z0-9_]*)[\'"])\]',
        ]
        
        for python_file in self.python_files:
            try:
                with open(python_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                for pattern in patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        var_name = match.group(1)
                        # Only include if it looks like a real environment variable
                        if var_name.isupper() and len(var_name) > 1:
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
                    
                    # Look for environment variable patterns in config files
                    env_patterns = [
                        r'\${([A-Z_][A-Z0-9_]*)}',  # ${VAR_NAME}
                        r'\$([A-Z_][A-Z0-9_]*)',     # $VAR_NAME
                        r'env\.([A-Z_][A-Z0-9_]*)',    # env.VAR_NAME
                        r'os\.environ\([\'"]([A-Z_][A-Z0-9_]*)[\'"]',  # os.environ("VAR_NAME")
                        r'getenv\([\'"]([A-Z_][A-Z0-9_]*)[\'"]',      # getenv("VAR_NAME")
                    ]
                    
                    for env_pattern in env_patterns:
                        matches = re.finditer(env_pattern, content)
                        for match in matches:
                            var_name = match.group(1)
                            if var_name.isupper() and len(var_name) > 1:
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
                        if var_name.isupper() and len(var_name) > 1:
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
        
        # Filter out script variables and system variables
        filtered_vars = all_vars - self.script_vars
        
        # Additional filtering for common non-config variables
        non_config_vars = {
            'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy',
            'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_DEFAULT_ENV',
            'GITHUB_ACTIONS', 'CI', 'TRAVIS', 'APPVEYOR', 'CIRCLECI',
            'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'CLASSPATH',
            'JAVA_HOME', 'NODE_PATH', 'GOPATH', 'RUST_HOME',
            'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME',
            'TERM', 'COLUMNS', 'LINES', 'PS1', 'PS2', 'PROMPT_COMMAND'
        }
        
        return filtered_vars - non_config_vars
    
    def _check_missing_in_example(self, used_vars: Set[str], example_vars: Set[str]) -> Set[str]:
        """Find variables used in code but missing from .env.example."""
        missing = used_vars - example_vars
        return missing
    
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
        print("🔍 Focused Dotenv Linter for AITBC")
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
            print(f"🔍 Found {len(used_vars)} actual environment variables used in code")
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
            f.write("\n# Auto-generated variables (added by focused_dotenv_linter)\n")
            for var in sorted(missing_vars):
                f.write(f"{var}=\n")
        
        print(f"✅ Added {len(missing_vars)} variables to .env.example")
    
    def generate_report(self, example_count: int, used_count: int, missing_count: int, 
                        missing_vars: Set[str], unused_vars: Set[str]) -> str:
        """Generate a detailed report."""
        report = []
        
        report.append("📊 Focused Dotenv Linter Report")
        report.append("=" * 50)
        report.append(f"Variables in .env.example: {example_count}")
        report.append(f"Actual environment variables used: {used_count}")
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
        description="Focused Dotenv Linter for AITBC - Check for actual configuration drift",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/focused_dotenv_linter.py              # Check for drift
  python scripts/focused_dotenv_linter.py --verbose    # Verbose output
  python scripts/focused_dotenv_linter.py --fix        # Auto-fix missing variables
  python scripts/focused_dotenv_linter.py --check      # Exit with error code on issues
        """
    )
    
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing variables in .env.example")
    parser.add_argument("--check", action="store_true", help="Exit with error code if issues found")
    
    args = parser.parse_args()
    
    # Initialize linter
    linter = FocusedDotenvLinter()
    
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
    print("✅ Focused dotenv linter completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
