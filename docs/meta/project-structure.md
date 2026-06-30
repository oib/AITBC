# AITBC - Project Structure

**Last Updated**: 2026-06-30
**Version**: 1.0

## Root Directory Organization

The AITBC project is organized with a clean root directory containing only essential files:

```
/opt/aitbc/
├── README.md                # Main documentation
├── SETUP.md                 # Setup guide
├── LICENSE                  # Project license
├── pyproject.toml           # Python configuration
├── requirements.txt         # Dependencies
├── .pre-commit-config.yaml  # Code quality hooks
├── apps/                    # Application services
├── cli/                     # Command-line interface
├── scripts/                 # Automation scripts
├── config/                  # Configuration files
├── docs/                    # Documentation
├── tests/                   # Test suite
├── infra/                   # Infrastructure
└── contracts/               # Smart contracts
```

## Key Directories

- **`apps/`** - Core application services (coordinator-api, blockchain-node, etc.)
- **`scripts/`** - Setup and automation scripts
- **`config/quality/`** - Code quality tools and configurations
- **`docs/reports/`** - Implementation reports and summaries
- **`cli/`** - Command-line interface tools

For detailed structure information, see [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md).

## Recent Improvements (March 2026)

### Project Organization
- **Clean Root Directory**: Reduced from 25+ files to 12 essential files
- **Logical Grouping**: Related files organized into appropriate subdirectories
- **Professional Structure**: Follows Python project best practices
- **Documentation**: Comprehensive project structure documentation

## Related Topics

- [Project Overview](./project-overview.md) - General project information
- [Architecture Overview](./architecture-overview.md) - System architecture details
