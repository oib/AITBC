---
title: Contributing
description: How to contribute to the AITBC project
---

# Contributing to AITBC

We welcome contributions from the community! This guide will help you get started.

## Ways to Contribute

### Code Contributions
- Fix bugs
- Add features
- Improve performance
- Write tests

### Documentation
- Improve docs
- Add examples
- Translate content
- Fix typos

### Community
- Answer questions
- Report issues
- Share feedback
- Organize events

## Getting Started

### 1. Fork Repository
```bash
git clone https://github.com/your-username/aitbc.git
cd aitbc
```

### 2. Setup Development Environment
```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Start development server
aitbc dev start
```

### 3. Create Branch
```bash
git checkout -b feature/your-feature-name
```

## Development Workflow

### Code Style
- Follow PEP 8 for Python
- Use ESLint for JavaScript
- Write clear commit messages
- Add tests for new features

### Testing
```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_jobs.py

# Check coverage
pytest --cov=aitbc
```

### Submitting Changes
1. Push to your fork
2. Create pull request
3. Wait for review
4. Address feedback
5. Merge!

## Reporting Issues

- Use GitHub Issues
- Provide clear description
- Include reproduction steps
- Add relevant logs

## Code of Conduct

Please read and follow our [Code of Conduct](https://github.com/aitbc/blob/main/CODE_OF_CONDUCT.md).

## Getting Help

- Discord: https://discord.gg/aitbc
- Email: dev@aitbc.io
- Documentation: https://docs.aitbc.io

Thank you for contributing! 🎉
