# AITBC Repository - Hub Status

## 🚨 IMPORTANT: This repository is now a HUB ONLY

This repository is no longer a development environment. It serves as a **hub between Gitea and GitHub** for:

- Code synchronization between Gitea and GitHub
- Issue tracking and project management
- Documentation storage
- Release management

## ❌ Removed Components

All localhost development services have been removed:

### Services Removed
- aitbc-agent-coordinator.service
- aitbc-agent-registry.service  
- aitbc-ai-service.service
- aitbc-blockchain-node-test.service
- aitbc-coordinator-api.service
- aitbc-exchange.service
- aitbc-explorer.service
- aitbc-marketplace-enhanced.service

### Directories Removed (Runtime Components Only)
- Runtime virtual environments (`.venv/`)
- Application logs and data files
- Systemd service files
- Python bytecode cache files

### Directories Preserved (Source Code)
- `/apps/` - Application source code (preserved for hub operations)
- `/cli/` - Command line interface source code (preserved for hub operations)  
- `/infra/` - Infrastructure configuration (preserved for hub operations)
- `/scripts/` - Development and deployment scripts (preserved for hub operations)
- `/dev/` - Development environment setup (preserved for hub operations)
- `/config/` - Configuration templates (preserved for hub operations)

### System Changes
- All systemd service files removed
- All Python bytecode cache files cleaned
- All running processes stopped

## ✅ What Remains

The repository now contains source code and hub infrastructure:

- **Source Code** in `/apps/`, `/cli/`, `/packages/`, `/contracts/`, `/plugins/`
- **Documentation** in `/docs/`
- **Tests** in `/tests/`
- **Infrastructure** in `/infra/` (deployment configs, Helm charts, Terraform)
- **Scripts** in `/scripts/` (development, deployment, maintenance)
- **Development Setup** in `/dev/` (environment configuration)
- **Website** in `/website/`
- **Git configuration** for hub operations
- **CI/CD workflows** for automated sync

## 🔄 Hub Operations

This repository now operates as:

1. **Gitea ↔ GitHub Sync**: Automatic bidirectional synchronization
2. **Issue Management**: Centralized issue tracking
3. **Release Management**: Automated release publishing
4. **Documentation Hub**: Central documentation storage

## 🚫 No Local Development

**DO NOT** attempt to run AITBC services locally. All development should happen in:
- Containerized environments
- Remote servers
- Cloud deployments

## 📞 Support

For development environments and deployments, refer to:
- Production deployment guides in `/docs/`
- Container setups in `/deployment/`
- Release notes in `/RELEASE_v*.md`

---

**Status**: Hub-Only Configuration  
**Last Updated**: 2026-03-23  
**Purpose**: Gitea ↔ GitHub Synchronization Hub
