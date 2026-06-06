# Disaster Recovery Communication Plan

**Version:** 1.0
**Date:** 2026-05-11
**Status:** Active
**Last Updated:** 2026-05-11

## Overview

This document defines communication protocols for disaster recovery incidents.

## Internal Communication

### During Incident
- **Primary Channel:** Customize (e.g., Slack #incidents)
- **Backup Channel:** Customize (e.g., phone call)
- **Frequency:** Every 15-30 minutes (customize)
- **Content:** Status updates, ETA, blockers

### After Incident
- **Primary Channel:** Customize (e.g., Email + Slack)
- **Timing:** Within 24 hours (customize)
- **Content:** Post-mortem, lessons learned, action items

## External Communication

### Customers
- **Channel:** Status page, email
- **Timing:** P1/P2: Immediate; P3/P4: Within 4 hours
- **Content:** Incident description, impact, ETA, resolution

### Stakeholders
- **Channel:** Email, phone
- **Timing:** P1/P2: Within 1 hour; P3/P4: Within 4 hours
- **Content:** Business impact, recovery status, financial impact

### Public
- **Channel:** Status page, social media (if major incident)
- **Timing:** Only for major incidents (P1)
- **Content:** High-level status, no technical details

## Communication Templates

### Initial Incident Notification (Internal)
```
INCIDENT DECLARED - [Severity] - [Service]

Summary: [Brief description]
Impact: [Affected users/services]
Started: [Timestamp]
Owner: [On-call engineer]
Slack: #incidents-[ticket-number]
```

### Customer Notification
```
Service Incident - [Service Name]

We are currently experiencing an issue affecting [service].
Our team is actively working to resolve this.
We will provide updates every 30 minutes.

Status: [Current status]
Started: [Timestamp]
```

### Resolution Notification
```
Incident Resolved - [Service Name]

The incident affecting [service] has been resolved.
Normal service has been restored.

Started: [Timestamp]
Resolved: [Timestamp]
Duration: [Duration]
Root Cause: [Brief description]
Prevention: [What we're doing to prevent recurrence]
```

## See Also

- [Disaster Scenarios](disaster-scenarios.md) - Disaster scenarios and recovery procedures
- [Disaster Contacts and Escalation](disaster-contacts-escalation.md) - Contact information and escalation procedures
- [Disaster Failover and Backup](disaster-failover-backup.md) - Failover mechanisms and backup procedures
- [Disaster Drills and Maintenance](disaster-drills-maintenance.md) - Drills, metrics, and maintenance
