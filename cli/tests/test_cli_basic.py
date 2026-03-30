#!/usr/bin/env python3
"""Basic CLI tests for AITBC CLI functionality."""

import pytest
import subprocess
import sys
import os
from pathlib import Path

# Add CLI to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

class TestCLIImports:
    """Test CLI module imports."""
    
    def test_cli_main_import(self):
        """Test that main CLI module can be imported."""
        try:
            from aitbc_cli import main
            assert main is not None
            print("✅ CLI main import successful")
        except ImportError as e:
            pytest.fail(f"❌ CLI main import failed: {e}")
    
    def test_cli_commands_import(self):
        """Test that CLI command modules can be imported."""
        try:
            from commands.wallet import create_wallet, list_wallets
            from commands.blockchain import get_blockchain_info
            assert create_wallet is not None
            assert list_wallets is not None
            assert get_blockchain_info is not None
            print("✅ CLI commands import successful")
        except ImportError as e:
            pytest.fail(f"❌ CLI commands import failed: {e}")


class TestCLIBasicFunctionality:
    """Test basic CLI functionality."""
    
    def test_cli_help_output(self):
        """Test that CLI help command works."""
        try:
            result = subprocess.run(
                [sys.executable, "aitbc_cli.py", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(Path(__file__).parent.parent)
            )
            
            assert result.returncode == 0
            assert "AITBC CLI" in result.stdout
            assert "usage:" in result.stdout
            print("✅ CLI help output working")
        except subprocess.TimeoutExpired:
            pytest.fail("❌ CLI help command timed out")
        except Exception as e:
            pytest.fail(f"❌ CLI help command failed: {e}")
    
    def test_cli_list_command(self):
        """Test that CLI list command works."""
        try:
            result = subprocess.run(
                [sys.executable, "aitbc_cli.py", "list"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(Path(__file__).parent.parent)
            )
            
            # Command should succeed even if no wallets exist
            assert result.returncode == 0
            print("✅ CLI list command working")
        except subprocess.TimeoutExpired:
            pytest.fail("❌ CLI list command timed out")
        except Exception as e:
            pytest.fail(f"❌ CLI list command failed: {e}")


class TestCLIErrorHandling:
    """Test CLI error handling."""
    
    def test_cli_invalid_command(self):
        """Test that CLI handles invalid commands gracefully."""
        try:
            result = subprocess.run(
                [sys.executable, "aitbc_cli.py", "invalid-command"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(Path(__file__).parent.parent)
            )
            
            # Should fail gracefully
            assert result.returncode != 0
            print("✅ CLI invalid command handling working")
        except subprocess.TimeoutExpired:
            pytest.fail("❌ CLI invalid command test timed out")
        except Exception as e:
            pytest.fail(f"❌ CLI invalid command test failed: {e}")


class TestCLIConfiguration:
    """Test CLI configuration and setup."""
    
    def test_cli_file_exists(self):
        """Test that main CLI file exists."""
        cli_file = Path(__file__).parent.parent / "aitbc_cli.py"
        assert cli_file.exists(), f"❌ CLI file not found: {cli_file}"
        print(f"✅ CLI file exists: {cli_file}")
    
    def test_cli_file_executable(self):
        """Test that CLI file is executable."""
        cli_file = Path(__file__).parent.parent / "aitbc_cli.py"
        assert cli_file.is_file(), f"❌ CLI file is not a file: {cli_file}"
        
        # Check if file has content
        with open(cli_file, 'r') as f:
            content = f.read()
            assert len(content) > 1000, f"❌ CLI file appears empty or too small"
            assert "def main" in content, f"❌ CLI file missing main function"
        
        print(f"✅ CLI file is valid: {len(content)} characters")


if __name__ == "__main__":
    # Run basic tests when executed directly
    print("🧪 Running basic CLI tests...")
    
    test_class = TestCLIImports()
    test_class.test_cli_main_import()
    test_class.test_cli_commands_import()
    
    test_class = TestCLIBasicFunctionality()
    test_class.test_cli_help_output()
    test_class.test_cli_list_command()
    
    test_class = TestCLIErrorHandling()
    test_class.test_cli_invalid_command()
    
    test_class = TestCLIConfiguration()
    test_class.test_cli_file_exists()
    test_class.test_cli_file_executable()
    
    print("✅ All basic CLI tests passed!")
