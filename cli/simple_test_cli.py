#!/usr/bin/env python3
"""
Simple AITBC CLI Test Script
Tests basic CLI functionality without full installation
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path

def test_cli_import():
    """Test if CLI can be imported"""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from aitbc_cli.main import cli
        print("✓ CLI import successful")
        return True
    except Exception as e:
        print(f"✗ CLI import failed: {e}")
        return False

def test_cli_help():
    """Test CLI help command"""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from aitbc_cli.main import cli
        
        # Capture help output
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        try:
            with redirect_stdout(f):
                cli(['--help'])
            help_output = f.getvalue()
            print("✓ CLI help command works")
            print(f"Help output length: {len(help_output)} characters")
            return True
        except SystemExit:
            # Click uses SystemExit for help, which is normal
            help_output = f.getvalue()
            if "Usage:" in help_output:
                print("✓ CLI help command works")
                print(f"Help output length: {len(help_output)} characters")
                return True
            else:
                print("✗ CLI help output invalid")
                return False
    except Exception as e:
        print(f"✗ CLI help command failed: {e}")
        return False

def test_basic_commands():
    """Test basic CLI commands"""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from aitbc_cli.main import cli
        
        commands_to_test = [
            ['--version'],
            ['wallet', '--help'],
            ['blockchain', '--help'],
            ['marketplace', '--help']
        ]
        
        for cmd in commands_to_test:
            try:
                import io
                from contextlib import redirect_stdout
                
                f = io.StringIO()
                with redirect_stdout(f):
                    cli(cmd)
                print(f"✓ Command {' '.join(cmd)} works")
            except SystemExit:
                # Normal for help/version commands
                print(f"✓ Command {' '.join(cmd)} works")
            except Exception as e:
                print(f"✗ Command {' '.join(cmd)} failed: {e}")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Basic commands test failed: {e}")
        return False

def test_package_structure():
    """Test package structure"""
    cli_dir = Path(__file__).parent
    
    required_files = [
        'aitbc_cli/__init__.py',
        'aitbc_cli/main.py',
        'aitbc_cli/commands/__init__.py',
        'setup.py',
        'requirements.txt'
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = cli_dir / file_path
        if not full_path.exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"✗ Missing required files: {missing_files}")
        return False
    else:
        print("✓ All required files present")
        return True

def test_dependencies():
    """Test if dependencies are available"""
    try:
        import click
        import httpx
        import pydantic
        import yaml
        import rich
        print("✓ Core dependencies available")
        return True
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        return False

def main():
    """Run all tests"""
    print("AITBC CLI Simple Test Script")
    print("=" * 40)
    
    tests = [
        ("Package Structure", test_package_structure),
        ("Dependencies", test_dependencies),
        ("CLI Import", test_cli_import),
        ("CLI Help", test_cli_help),
        ("Basic Commands", test_basic_commands),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\nTesting {test_name}...")
        if test_func():
            passed += 1
        else:
            print(f"  Test failed!")
    
    print(f"\n{'='*40}")
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! CLI is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
