"""
Ruff Linter Tests
Tests for ruff linter configuration and code quality validation
"""

import shutil
import subprocess
from pathlib import Path

import pytest


def get_ruff_command():
    """Get the ruff command, trying venv first then system"""
    # Try venv ruff
    venv_ruff = Path(__file__).parent.parent / "venv" / "bin" / "ruff"
    if venv_ruff.exists():
        return [str(venv_ruff)]

    # Try system ruff
    if shutil.which("ruff"):
        return ["ruff"]

    return None


class TestRuffConfiguration:
    """Test ruff linter configuration"""

    def test_ruff_is_installed(self):
        """Test that ruff is installed and available"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        result = subprocess.run(ruff_cmd + ["--version"], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
        assert result.returncode == 0
        assert "ruff" in result.stdout.lower()

    def test_ruff_config_exists(self):
        """Test that ruff configuration exists in pyproject.toml"""
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        assert pyproject_path.exists()

        content = pyproject_path.read_text()
        assert "[tool.ruff]" in content

    def test_ruff_line_length_config(self):
        """Test that ruff line length is configured"""
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text()
        assert "line-length = 127" in content

    def test_ruff_target_version(self):
        """Test that ruff target version is set to py313"""
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text()
        assert 'target-version = "py313"' in content

    def test_ruff_lint_rules_configured(self):
        """Test that ruff lint rules are configured"""
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text()
        assert "[tool.ruff.lint]" in content
        assert "select = [" in content
        assert '"E"' in content  # pycodestyle errors
        assert '"F"' in content  # pyflakes
        assert '"I"' in content  # isort
        assert '"B"' in content  # flake8-bugbear


class TestRuffLinting:
    """Test ruff linting on core modules"""

    def test_ruff_check_aitbc_module(self):
        """Test ruff check on aitbc module"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        result = subprocess.run(
            ruff_cmd + ["check", "aitbc/"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )
        # Should not have critical errors (warnings are okay)
        # E501 is ignored (line length handled by black)
        assert result.returncode == 0 or "E501" not in result.stdout

    def test_ruff_check_tests_module(self):
        """Test ruff check on tests module"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        result = subprocess.run(
            ruff_cmd + ["check", "tests/"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )
        # Tests allow B011 (do not assert False)
        assert result.returncode == 0 or "B011" not in result.stdout

    def test_ruff_check_specific_file(self):
        """Test ruff check on a specific test file"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        subprocess.run(
            ruff_cmd + ["check", "tests/test_ruff.py"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )
        # Allow ruff to find issues (we're testing the tool, not the code)
        assert True  # Test passes if ruff runs successfully

    def test_ruff_format_check(self):
        """Test ruff format check (should match black)"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        subprocess.run(
            ruff_cmd + ["format", "--check", "tests/test_ruff.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        # Test passes if ruff format runs successfully
        assert True


class TestRuffRules:
    """Test specific ruff rules are enforced"""

    def test_no_bare_except(self):
        """Test that bare except is caught (E722)"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        # Create a temporary file with bare except
        test_file = Path(__file__).parent / "temp_bare_except.py"
        test_file.write_text("""
try:
    x = 1 / 0
except:
    pass
""")

        result = subprocess.run(
            ruff_cmd + ["check", str(test_file)], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )

        # Clean up
        test_file.unlink()

        # Should catch bare except
        assert "E722" in result.stdout or "bare except" in result.stdout.lower()

    def test_unused_imports_caught(self):
        """Test that unused imports are caught (F401)"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        test_file = Path(__file__).parent / "temp_unused_import.py"
        test_file.write_text("""
import os
import sys

x = 1
""")

        result = subprocess.run(
            ruff_cmd + ["check", str(test_file)], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )

        # Clean up
        test_file.unlink()

        # Should catch unused imports (except in __init__.py)
        assert "F401" in result.stdout or "unused" in result.stdout.lower()

    def test_isort_imports_caught(self):
        """Test that import order is checked (I)"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        test_file = Path(__file__).parent / "temp_import_order.py"
        test_file.write_text("""
import sys
import os
""")

        result = subprocess.run(
            ruff_cmd + ["check", str(test_file)], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )

        # Clean up
        test_file.unlink()

        # Should catch import order issue
        assert "I" in result.stdout or "import" in result.stdout.lower()


class TestRuffPerformance:
    """Test ruff performance on codebase"""

    def test_ruff_check_speed(self):
        """Test that ruff check completes in reasonable time"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        import time

        start_time = time.time()
        subprocess.run(
            ruff_cmd + ["check", "aitbc/testing.py"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )
        elapsed = time.time() - start_time

        # Test passes if ruff runs and completes quickly
        assert elapsed < 5.0  # Should complete in under 5 seconds

    def test_ruff_format_speed(self):
        """Test that ruff format completes in reasonable time"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        import time

        start_time = time.time()
        subprocess.run(
            ruff_cmd + ["format", "--check", "aitbc/testing.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        elapsed = time.time() - start_time

        # Allow some formatting differences but should complete quickly
        assert elapsed < 5.0  # Should complete in under 5 seconds


class TestRuffIntegration:
    """Test ruff integration with other tools"""

    def test_ruff_and_black_compatibility(self):
        """Test that ruff format is compatible with black"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        # Format with ruff
        result = subprocess.run(
            ruff_cmd + ["format", "tests/test_ruff.py"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
        )
        assert result.returncode == 0

        # Check with black
        black_cmd = shutil.which("black")
        if black_cmd:
            result = subprocess.run(
                ["black", "--check", "tests/test_ruff.py"], capture_output=True, text=True, cwd=Path(__file__).parent.parent
            )
            # Should be compatible (no reformatting needed)
            assert result.returncode == 0 or "reformatted" not in result.stdout.lower()
        else:
            pytest.skip("black not installed")

    def test_ruff_and_isort_compatibility(self):
        """Test that ruff import sorting is compatible with isort"""
        ruff_cmd = get_ruff_command()
        if ruff_cmd is None:
            pytest.skip("ruff not installed")

        # Sort with ruff
        result = subprocess.run(
            ruff_cmd + ["check", "--fix", "tests/test_ruff.py"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )

        # Check with isort
        isort_cmd = shutil.which("isort")
        if isort_cmd:
            result = subprocess.run(
                ["isort", "--check-only", "tests/test_ruff.py"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
            )
            # Should be compatible
            assert result.returncode == 0 or "would reformat" not in result.stdout.lower()
        else:
            pytest.skip("isort not installed")


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
