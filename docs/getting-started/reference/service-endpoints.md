# Service Endpoints

For authoritative port configuration, see [Service Ports Reference](../../reference/SERVICE_PORTS.md).

## Quick Reference

| Service | Port | Health Endpoint |
|---------|------|----------------|
| Wallet API | 8015 | `http://localhost:8015/health` |
| Exchange API | 8010 | `http://localhost:8010/health` |
| Coordinator API | 8011 | `http://localhost:8011/health` |
| Blockchain RPC | 8006 | `http://localhost:8006/health` |
| Marketplace | 8102 | `http://localhost:8102/health` |

**Note:** Port configurations are defined in service wrapper scripts and application main.py files. See [Service Ports Reference](../../reference/SERVICE_PORTS.md) for complete details and source references.

## See Also

- [Management Commands](management-commands.md)
- [Network Requirements](network-requirements.md)
