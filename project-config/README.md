# Project Configuration

This directory contains all project configuration files.

## Files

- `pyproject.toml` - Python project configuration with build system, dependencies, and metadata
- `requirements.txt` - Python dependencies list
- `poetry.lock` - Dependency lock file for reproducible builds
- `.gitignore` - Git ignore patterns for the project
- `.deployment_progress` - Tracks deployment progress and status

## Usage

### Installing Dependencies

```bash
# Using pip
pip install -r requirements.txt

# Using poetry (if available)
poetry install
```

### Project Configuration

The `pyproject.toml` file contains:
- Project metadata (name, version, description)
- Build system configuration
- Dependency specifications
- Tool configurations (black, ruff, mypy, etc.)

### Git Configuration

The `.gitignore` file excludes:
- Python cache files
- Virtual environments
- IDE files
- Build artifacts
- Log files
- Temporary files

## Notes

- Configuration files are kept separate from source code for better organization
- The project uses modern Python packaging standards (PEP 517/518)
- Dependencies are pinned for reproducible builds
