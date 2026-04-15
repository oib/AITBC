# AITBC Systemd Git Workflow Skill

## Description
Expert skill for managing systemd service files using proper git workflow instead of scp operations. Ensures systemd configurations are always synchronized via git repository rather than direct file copying.

## Core Principles

### Git-Tracked Files Only
- All systemd service files must be edited in `/opt/aitbc/systemd/` (git-tracked directory)
- NEVER edit files directly in `/etc/systemd/system/`
- NEVER use scp to copy systemd files between nodes

### Symbolic Link Architecture
- `/etc/systemd/system/aitbc-*.service` -> `/opt/aitbc/systemd/aitbc-*.service`
- Symlinks ensure active systemd files always match repository
- Changes in repository automatically reflected in active configuration

## Standard Workflow

### Local Changes
1. Edit files in `/opt/aitbc/systemd/`
2. Commit changes: `git add systemd/ && git commit -m "description"`
3. Push to gitea: `git push`

### Remote Sync (aitbc1)
1. Pull changes: `git pull`
2. Create/update symlinks: `/opt/aitbc/scripts/utils/link-systemd.sh`
3. Reload systemd: `systemctl daemon-reload`
4. Restart affected services: `systemctl restart aitbc-*`

## Available Scripts

### link-systemd.sh
- Location: `/opt/aitbc/scripts/utils/link-systemd.sh`
- Purpose: Creates symbolic links from `/etc/systemd/system/` to `/opt/aitbc/systemd/`
- Usage: `/opt/aitbc/scripts/utils/link-systemd.sh`
- Benefits: Automatic sync, no manual file copying needed

### sync-systemd.sh
- Location: `/opt/aitbc/scripts/sync/sync-systemd.sh`
- Purpose: Copies repository files to active systemd (alternative to symlinks)
- Usage: `/opt/aitbc/scripts/sync/sync-systemd.sh`
- Note: Prefer link-systemd.sh for automatic sync

## Common Issues

### Git Conflicts on Remote Nodes
**Symptom**: `git pull` fails with "local changes would be overwritten"

**Resolution**:
1. Discard local changes: `git reset --hard HEAD`
2. Pull changes: `git pull`
3. Re-run link-systemd.sh: `/opt/aitbc/scripts/utils/link-systemd.sh`

### Broken Symlinks
**Symptom**: Systemd service fails to load or uses old configuration

**Resolution**:
1. Verify symlinks: `ls -la /etc/systemd/system/aitbc-*`
2. Re-create symlinks: `/opt/aitbc/scripts/utils/link-systemd.sh`
3. Reload systemd: `systemctl daemon-reload`

### SCP Usage Warning
**Symptom**: Direct scp to `/etc/systemd/system/` breaks symlinks

**Resolution**:
1. Never use scp to `/etc/systemd/system/`
2. Always use git workflow
3. If scp was used, restore proper symlinks with link-systemd.sh

## Verification Commands

### Check Symlink Status
```bash
ls -la /etc/systemd/system/aitbc-*
readlink /etc/systemd/system/aitbc-blockchain-node.service
```

### Verify Git Status
```bash
git status
git diff systemd/
```

### Check Service Configuration
```bash
systemctl cat aitbc-blockchain-node.service
```

## Best Practices

1. **Always edit in git-tracked directory**: `/opt/aitbc/systemd/`
2. **Commit before pushing**: Ensure changes are properly committed
3. **Pull before link-systemd.sh**: Ensure repository is up-to-date
4. **Test locally first**: Verify changes work before syncing to remote
5. **Document changes**: Use descriptive commit messages
6. **Monitor logs**: Check service logs after changes
7. **Run as root**: No sudo needed - we are root on both nodes

## Memory Reference
See memory entry `systemd-git-workflow` for detailed workflow documentation (no sudo needed - we are root on both nodes).

## Related Skills
- aitbc-basic-operations-skill: Basic git operations
- aitbc-system-architect: System architecture understanding
- blockchain-troubleshoot-recovery: Service troubleshooting
