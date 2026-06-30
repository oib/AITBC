# AITBC Agent Coordinator - Operator Guide

**Last Updated:** 2026-06-30
**Version:** 2.0 (Split into topic-focused files)

> **Important:** This document describes the Agent Coordinator service. The Agent Coordinator service runs on port 9001. For the Coordinator API (job submission), use port 8203. For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

This guide provides operators with the knowledge to deploy, configure, monitor, and troubleshoot the AITBC Agent Coordinator service.

## Documentation Structure

This guide has been split into topic-focused files for easier navigation:

### Core Topics

- **[Deployment](./operator-deployment.md)** - Installation, prerequisites, service configuration, and Redis setup
- **[Agent Registration](./operator-registration.md)** - Manual and automated agent registration procedures
- **[Monitoring](./operator-monitoring.md)** - Health checks, service status, and agent monitoring
- **[Troubleshooting](./operator-troubleshooting.md)** - Common issues, solutions, and troubleshooting checklist
- **[Performance Tuning](./operator-performance.md)** - Load balancing strategies, priority queues, and resource limits
- **[Security](./operator-security.md)** - Network security, authentication, and data encryption
- **[Backup and Recovery](./operator-backup.md)** - Redis backup, service configuration backup, and restore procedures
- **[Scaling](./operator-scaling.md)** - Horizontal scaling and Redis clustering
- **[Maintenance](./operator-maintenance.md)** - Regular maintenance tasks, agent cleanup, and service restart procedures
- **[Alerting](./operator-alerting.md)** - Recommended alerts and monitoring tools

## Quick Navigation

**For New Operators:**
1. Start with [Deployment](./operator-deployment.md)
2. Review [Agent Registration](./operator-registration.md)
3. Set up [Monitoring](./operator-monitoring.md)

**For Operations:**
1. Check [Performance Tuning](./operator-performance.md) for optimization
2. Review [Security](./operator-security.md) for hardening
3. Configure [Alerting](./operator-alerting.md) for proactive monitoring

**For Troubleshooting:**
- See [Troubleshooting](./operator-troubleshooting.md) for common issues and solutions
- Use the troubleshooting checklist at the end of that file

---

**Note**: This file has been split into topic-focused files for easier navigation. See the [Documentation Structure](#documentation-structure) section above for links to the individual topic files.
