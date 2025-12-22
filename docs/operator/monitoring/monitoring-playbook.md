# AITBC Monitoring Playbook & On-Call Guide

## Overview

This document provides comprehensive monitoring procedures, on-call rotations, and incident response playbooks for the AITBC platform. It ensures reliable operation of all services and quick resolution of issues.

## Service Overview

### Core Services
- **Coordinator API**: Job management and marketplace coordination
- **Blockchain Nodes**: Consensus and transaction processing
- **Explorer UI**: Block explorer and transaction visualization
- **Marketplace UI**: User interface for marketplace operations
- **Wallet Daemon**: Cryptographic key management
- **Infrastructure**: PostgreSQL, Redis, Kubernetes cluster

### Critical Metrics
- **Availability**: 99.9% uptime SLA
- **Performance**: <200ms API response time (95th percentile)
- **Throughput**: 100+ TPS sustained
- **MTTR**: <2 minutes for critical incidents

## On-Call Rotation

### Rotation Schedule
- **Primary On-Call**: 1 week rotation, Monday 00:00 UTC to Monday 00:00 UTC
- **Secondary On-Call**: Shadow primary, handles escalations
- **Tertiary**: Backup for both primary and secondary
- **Rotation Handoff**: Every Monday at 08:00 UTC

### Team Structure
```
Week 1: Alice (Primary), Bob (Secondary), Carol (Tertiary)
Week 2: Bob (Primary), Carol (Secondary), Alice (Tertiary)
Week 3: Carol (Primary), Alice (Secondary), Bob (Tertiary)
```

### Handoff Procedures
1. **Pre-handoff Check** (Sunday 22:00 UTC):
   - Review active incidents
   - Check scheduled maintenance
   - Verify monitoring systems health

2. **Handoff Meeting** (Monday 08:00 UTC):
   - 15-minute video call
   - Discuss current issues
   - Transfer knowledge
   - Confirm contact information

3. **Post-handoff** (Monday 09:00 UTC):
   - Primary acknowledges receipt
   - Update on-call calendar
   - Test alerting systems

### Contact Information
- **Primary**: +1-555-ONCALL-1 (PagerDuty)
- **Secondary**: +1-555-ONCALL-2 (PagerDuty)
- **Tertiary**: +1-555-ONCALL-3 (PagerDuty)
- **Escalation Manager**: +1-555-ESCALATE
- **Emergency**: +1-555-EMERGENCY (Critical infrastructure only)

## Alerting & Escalation

### Alert Severity Levels

#### Critical (P0)
- Service completely down
- Data loss or corruption
- Security breach
- SLA violation in progress
- **Response Time**: 5 minutes
- **Escalation**: 15 minutes if no response

#### High (P1)
- Significant degradation
- Partial service outage
- High error rates (>10%)
- **Response Time**: 15 minutes
- **Escalation**: 1 hour if no response

#### Medium (P2)
- Minor degradation
- Elevated error rates (5-10%)
- Performance issues
- **Response Time**: 1 hour
- **Escalation**: 4 hours if no response

#### Low (P3)
- Informational alerts
- Non-critical issues
- **Response Time**: 4 hours
- **Escalation**: 24 hours if no response

### Escalation Policy
1. **Level 1**: Primary On-Call (5-60 minutes)
2. **Level 2**: Secondary On-Call (15 minutes - 4 hours)
3. **Level 3**: Tertiary On-Call (1 hour - 24 hours)
4. **Level 4**: Engineering Manager (4 hours)
5. **Level 5**: CTO (Critical incidents only)

### Alert Channels
- **PagerDuty**: Primary alerting system
- **Slack**: #on-call-aitbc channel
- **Email**: oncall@aitbc.io
- **SMS**: Critical alerts only
- **Phone**: Critical incidents only

## Incident Response

### Incident Classification

#### SEV-0 (Critical)
- Complete service outage
- Data loss or security breach
- Financial impact >$10,000/hour
- Customer impact >50%

#### SEV-1 (High)
- Significant service degradation
- Feature unavailable
- Financial impact $1,000-$10,000/hour
- Customer impact 10-50%

#### SEV-2 (Medium)
- Minor service degradation
- Performance issues
- Financial impact <$1,000/hour
- Customer impact <10%

#### SEV-3 (Low)
- Informational
- No customer impact

### Incident Response Process

#### 1. Detection & Triage (0-5 minutes)
```bash
# Check alert severity
# Verify impact
# Create incident channel
# Notify stakeholders
```

#### 2. Assessment (5-15 minutes)
- Determine scope
- Identify root cause area
- Estimate resolution time
- Declare severity level

#### 3. Communication (15-30 minutes)
- Update status page
- Notify customers (if needed)
- Internal stakeholder updates
- Set up war room

#### 4. Resolution (Varies)
- Implement fix
- Verify resolution
- Monitor for recurrence
- Document actions

#### 5. Recovery (30-60 minutes)
- Full service restoration
- Performance validation
- Customer communication
- Incident closure

## Service-Specific Runbooks

### Coordinator API

#### High Error Rate
**Symptoms**: 5xx errors >5%, response time >500ms
**Runbook**:
1. Check pod health: `kubectl get pods -l app=coordinator`
2. Review logs: `kubectl logs -f deployment/coordinator`
3. Check database connectivity
4. Verify Redis connection
5. Scale if needed: `kubectl scale deployment coordinator --replicas=5`

#### Service Unavailable
**Symptoms**: 503 errors, health check failures
**Runbook**:
1. Check deployment status
2. Review recent deployments
3. Rollback if necessary
4. Check resource limits
5. Verify ingress configuration

### Blockchain Nodes

#### Consensus Stalled
**Symptoms**: No new blocks, high finality latency
**Runbook**:
1. Check node sync status
2. Verify network connectivity
3. Review validator set
4. Check governance proposals
5. Restart if needed (with caution)

#### High Peer Drop Rate
**Symptoms**: Connected peers <50%, network partition
**Runbook**:
1. Check network policies
2. Verify DNS resolution
3. Review firewall rules
4. Check load balancer health
5. Restart networking components

### Database (PostgreSQL)

#### Connection Exhaustion
**Symptoms**: "Too many connections" errors
**Runbook**:
1. Check active connections
2. Identify long-running queries
3. Kill idle connections
4. Increase pool size if needed
5. Scale database

#### Replica Lag
**Symptoms**: Read replica lag >10 seconds
**Runbook**:
1. Check replica status
2. Review network latency
3. Verify disk space
4. Restart replication if needed
5. Failover if necessary

### Redis

#### Memory Pressure
**Symptoms**: OOM errors, high eviction rate
**Runbook**:
1. Check memory usage
2. Review key expiration
3. Clean up unused keys
4. Scale Redis cluster
5. Optimize data structures

#### Connection Issues
**Symptoms**: Connection timeouts, errors
**Runbook**:
1. Check max connections
2. Review connection pool
3. Verify network policies
4. Restart Redis if needed
5. Scale horizontally

## Monitoring Dashboards

### Primary Dashboards

#### 1. System Overview
- Service health status
- Error rates (4xx/5xx)
- Response times
- Throughput metrics
- Resource utilization

#### 2. Infrastructure
- Kubernetes cluster health
- Node resource usage
- Pod status and restarts
- Network traffic
- Storage capacity

#### 3. Application Metrics
- Job submission rates
- Transaction processing
- Marketplace activity
- Wallet operations
- Mining statistics

#### 4. Business KPIs
- Active users
- Transaction volume
- Revenue metrics
- Customer satisfaction
- SLA compliance

### Alert Rules

#### Critical Alerts
- Service down >1 minute
- Error rate >10%
- Response time >1 second
- Disk space >90%
- Memory usage >95%

#### Warning Alerts
- Error rate >5%
- Response time >500ms
- CPU usage >80%
- Queue depth >1000
- Replica lag >5s

## SLOs & SLIs

### Service Level Objectives

| Service | Metric | Target | Measurement |
|---------|--------|--------|-------------|
| Coordinator API | Availability | 99.9% | 30-day rolling |
| Coordinator API | Latency | <200ms | 95th percentile |
| Blockchain | Block Time | <2s | 24-hour average |
| Marketplace | Success Rate | 99.5% | Daily |
| Explorer | Response Time | <500ms | 95th percentile |

### Service Level Indicators

#### Availability
- HTTP status codes
- Health check responses
- Pod readiness status

#### Latency
- Request duration histogram
- Database query times
- External API calls

#### Throughput
- Requests per second
- Transactions per block
- Jobs completed per hour

#### Quality
- Error rates
- Success rates
- Customer satisfaction

## Post-Incident Process

### Immediate Actions (0-1 hour)
1. Verify full resolution
2. Monitor for recurrence
3. Update status page
4. Notify stakeholders

### Post-Mortem (1-24 hours)
1. Create incident document
2. Gather timeline and logs
3. Identify root cause
4. Document lessons learned

### Follow-up (1-7 days)
1. Schedule post-mortem meeting
2. Assign action items
3. Update runbooks
4. Improve monitoring

### Review (Weekly)
1. Review incident trends
2. Update SLOs if needed
3. Adjust alerting thresholds
4. Improve processes

## Maintenance Windows

### Scheduled Maintenance
- **Frequency**: Weekly maintenance window
- **Time**: Sunday 02:00-04:00 UTC
- **Duration**: Maximum 2 hours
- **Notification**: 72 hours advance

### Emergency Maintenance
- **Approval**: Engineering Manager required
- **Notification**: 4 hours advance (if possible)
- **Duration**: As needed
- **Rollback**: Always required

## Tools & Systems

### Monitoring Stack
- **Prometheus**: Metrics collection
- **Grafana**: Visualization and dashboards
- **Alertmanager**: Alert routing and management
- **PagerDuty**: On-call scheduling and escalation

### Observability
- **Jaeger**: Distributed tracing
- **Loki**: Log aggregation
- **Kiali**: Service mesh visualization
- **Kube-state-metrics**: Kubernetes metrics

### Communication
- **Slack**: Primary communication
- **Zoom**: War room meetings
- **Status Page**: Customer notifications
- **Email**: Formal communications

## Training & Onboarding

### New On-Call Engineer
1. Shadow primary for 1 week
2. Review all runbooks
3. Test alerting systems
4. Handle low-severity incidents
5. Solo on-call with mentor

### Ongoing Training
- Monthly incident drills
- Quarterly runbook updates
- Annual training refreshers
- Cross-team knowledge sharing

## Emergency Procedures

### Major Outage
1. Declare incident (SEV-0)
2. Activate war room
3. Customer communication
4. Executive updates
5. Recovery coordination

### Security Incident
1. Isolate affected systems
2. Preserve evidence
3. Notify security team
4. Customer notification
5. Regulatory compliance

### Data Loss
1. Stop affected services
2. Assess impact
3. Initiate recovery
4. Customer communication
5. Prevent recurrence

## Appendix

### A. Contact List
[Detailed contact information]

### B. Runbook Checklist
[Quick reference checklists]

### C. Alert Configuration
[Prometheus rules and thresholds]

### D. Dashboard Links
[Grafana dashboard URLs]

---

*Document Version: 1.0*
*Last Updated: 2024-12-22*
*Next Review: 2025-01-22*
*Owner: SRE Team*
