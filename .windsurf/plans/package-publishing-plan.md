---
description: Package Publishing Workflow for aitbc-sdk and aitbc-crypto
---

# Package Publishing Workflow

This workflow covers the packaging and publishing of AITBC SDKs to PyPI and npm.

## Prerequisites

- Active PyPI account with publishing permissions
- Active npm account with publishing permissions
- Gitea Actions configured for the repository
- Version management strategy defined

## Steps

### 1. PyPI Package Setup for aitbc-sdk

1. **Verify package structure**
   - Ensure `packages/py/aitbc-sdk/` has proper package structure
   - Check `pyproject.toml` configuration
   - Verify package metadata (name, version, description, authors)

2. **Configure PyPI publishing**
   - Add PyPI API token to Gitea repository secrets (`PYPI_API_TOKEN`)
   - Create Gitea Actions workflow for PyPI publishing
   - Configure automatic publishing on version tags

3. **Test package installation**
   - Build package locally: `cd packages/py/aitbc-sdk && python -m build`
   - Test installation from built wheel
   - Verify imports work correctly

4. **Publish to PyPI**
   - Create and push version tag (e.g., `v0.1.0`)
   - Gitea Actions will automatically publish to PyPI
   - Verify package appears on PyPI
   - Test installation from PyPI: `pip install aitbc-sdk`

### 2. PyPI Package Setup for aitbc-crypto

1. **Verify package structure**
   - Ensure `packages/py/aitbc-crypto/` has proper package structure
   - Check `pyproject.toml` configuration
   - Verify package metadata

2. **Configure PyPI publishing**
   - Use existing PyPI token from aitbc-sdk
   - Create Gitea Actions workflow for aitbc-crypto publishing
   - Configure automatic publishing on version tags

3. **Test package installation**
   - Build package locally: `cd packages/py/aitbc-crypto && python -m build`
   - Test installation from built wheel
   - Verify cryptographic operations work correctly

4. **Publish to PyPI**
   - Create and push version tag
   - Gitea Actions will automatically publish
   - Verify package appears on PyPI
   - Test installation from PyPI: `pip install aitbc-crypto`

### 3. npm Package Setup for JavaScript/TypeScript SDK

1. **Verify package structure**
   - Ensure `packages/js/aitbc-sdk/` has proper package structure
   - Check `package.json` configuration
   - Verify package metadata (name, version, description, author)

2. **Configure npm publishing**
   - Add npm authentication token to Gitea repository secrets (`NPM_TOKEN`)
   - Create Gitea Actions workflow for npm publishing
   - Configure `.npmrc` for proper authentication

3. **Test package build**
   - Build package locally: `cd packages/js/aitbc-sdk && npm run build`
   - Test TypeScript compilation
   - Verify type definitions (.d.ts files) are generated

4. **Publish to npm**
   - Create and push version tag
   - Gitea Actions will automatically publish to npm
   - Verify package appears on npm registry
   - Test installation from npm: `npm install aitbc-sdk`

### 4. Version Management

1. **Define semantic versioning strategy**
   - Follow SemVer (MAJOR.MINOR.PATCH)
   - MAJOR: Breaking changes
   - MINOR: New features, backward compatible
   - PATCH: Bug fixes, backward compatible

2. **Configure version management**
   - Set up automated version bumping in Gitea Actions
   - Create version tags for releases
   - Maintain CHANGELOG.md with release notes

3. **Version synchronization**
   - Ensure aitbc-sdk and aitbc-crypto versions are synchronized
   - Coordinate Python and JavaScript SDK releases
   - Document version compatibility matrix

## Verification

- [ ] aitbc-sdk published to PyPI and installable
- [ ] aitbc-crypto published to PyPI and installable
- [ ] aitbc-sdk published to npm and installable
- [ ] Gitea Actions workflows successfully publish on tags
- [ ] Version management strategy documented
- [ ] CHANGELOG.md maintained with release notes

## Troubleshooting

- **PyPI publishing fails**: Check PyPI token permissions, verify package name availability
- **npm publishing fails**: Verify npm token, check package name availability, ensure `.npmrc` is configured
- **Build fails locally**: Check dependencies, verify Python/Node.js versions
- **Installation test fails**: Verify package structure, check imports/exports

## Related Files

- `packages/py/aitbc-sdk/pyproject.toml`
- `packages/py/aitbc-crypto/pyproject.toml`
- `packages/js/aitbc-sdk/package.json`
- `.gitea/workflows/publish-python.yml`
- `.gitea/workflows/publish-js.yml`
