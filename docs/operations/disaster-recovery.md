# AITBC Disaster Recovery Plan

**Version:** 1.0
**Date:** 2026-05-11
**Status:** Active
**Last Updated:** 2026-05-11

## Executive Summary

This document outlines the comprehensive disaster recovery procedures for the AITBC platform. It defines disaster scenarios, recovery procedures, contact information, escalation paths, and communication protocols to ensure business continuity in the event of system failures or disasters.

## Disaster Scenarios

### 1. Database Corruption
- **Description:** PostgreSQL database corruption due to hardware failure, software bug, or malicious attack
- **Impact:** Loss of job data, marketplace offers/bids, user sessions, configuration
- **RTO:** 1 hour
- **RPO:** 24 hours
- **Recovery Strategy:** Restore from latest PostgreSQL backup

### 2. Service Failure
- **Description:** Critical service failure (coordinator-api, blockchain-node, marketplace, exchange)
- **Impact:** Service unavailability, transaction processing halt
- **RTO:** 30 minutes
- **RPO:** 0 minutes (stateless services)
- **Recovery Strategy:** Restart services, failover to standby instances

### 3. Network Partition
- **Description:** Network connectivity loss between components or regions
- **Impact:** Distributed system inconsistency, service degradation
- **RTO:** 2 hours
- **RPO:** 0 minutes
- **Recovery Strategy:** Restore network connectivity, resynchronize state

### 4. Data Center Outage
- **Description:** Complete data center failure (power, cooling, network)
- **Impact:** Complete system unavailability
- **RTO:** 4 hours
- **RPO:** 24 hours
- **Recovery Strategy:** Failover to alternate data center

### 5. Security Breach
- **Description:** Unauthorized access, data breach, ransomware attack
- **Impact:** Data compromise, service disruption, reputational damage
- **RTO:** Variable (depends on breach severity)
- **RPO:** 24 hours
- **Recovery Strategy:** Contain breach, restore from pre-breach backup, patch vulnerabilities

### 6. Ransomware Attack
- **Description:** Malicious encryption of data/systems
- **Impact:** Data unavailability, service disruption
- **RTO:** 8-24 hours
- **RPO:** 24 hours
- **Recovery Strategy:** Restore from clean backups, rebuild systems

## Contact Information

### Primary Contacts

| Role | Name | Email | Phone | Timezone |
|------|------|-------|-------|----------|
| CTO | | | | UTC |
| Engineering Lead | | | | UTC |
| DevOps Lead | | | | UTC |
| Security Lead | | | | UTC |
| Operations Manager | | | | UTC |

### Secondary Contacts

| Role | Name | Email | Phone | Timezone |
|------|------|-------|-------|----------|
| Database Administrator | | | | UTC |
| Network Engineer | | | | UTC |
| Security Analyst | | | | UTC |

### External Contacts

| Service | Contact | Email | Phone |
|---------|---------|-------|-------|
| Cloud Provider (AWS) | | | |
| DNS Provider | | | |
| Security Incident Response | | | |
| Legal Counsel | | | |
| Public Relations | | | |

## Escalation Procedures

### Severity Levels

#### P1 - Critical (System Down)
- **Definition:** Complete system outage affecting all users
- **Response Time:** 15 minutes
- **Escalation Path:** On-call Engineer → Engineering Lead → CTO
- **Communication:** Immediate stakeholder notification

#### P2 - Major (Service Degradation)
- **Definition:** Critical functionality impaired, partial outage
- **Response Time:** 30 minutes
- **Escalation Path:** On-call Engineer → Engineering Lead
- **Communication:** Stakeholder notification within 1 hour

#### P3 - Minor (Limited Impact)
- **Definition:** Non-critical functionality impaired, limited users affected
- **Response Time:** 1 hour
- **Escalation Path:** On-call Engineer
- **Communication:** Stakeholder notification within 4 hours

#### P4 - Low (Minimal Impact)
- **Definition:** Cosmetic issues, documentation errors
- **Response Time:** 4 hours
- **Escalation Path:** Team Lead
- **Communication:** Next business day

### Escalation Flowchart

```
Incident Detected
    ↓
On-call Engineer (15 min)
    ↓ (if unresolved)
Engineering Lead (30 min)
    ↓ (if unresolved)
CTO (1 hour)
    ↓ (if unresolved)
Executive Team (2 hours)
```

## Recovery Procedures

### Pre-Recovery Steps

1. **Assess Impact**
   - Determine scope and severity of incident
   - Identify affected components and users
   - Estimate recovery time
   - Classify incident severity (P1-P4)

2. **Declare Incident**
   - Notify on-call engineer
   - Create incident ticket
   - Initiate escalation based on severity
   - Activate incident response team

3. **Contain Incident**
   - Isolate affected systems
   - Prevent further damage
   - Preserve forensic evidence (if security incident)
   - Implement temporary workarounds

### Recovery by Scenario

#### Database Corruption Recovery

```bash
# 1. Stop affected services
kubectl scale deployment coordinator-api --replicas=0
kubectl scale deployment marketplace --replicas=0
kubectl scale deployment exchange --replicas=0

# 2. Identify latest clean backup
aws s3 ls s3://aitbc-backups-default/postgresql/ | tail -1

# 3. Download backup
aws s3 cp s3://aitbc-backups-default/postgresql/[latest-backup].sql.gz /tmp/

# 4. Restore database
./infra/scripts/restore_postgresql.sh default /tmp/[latest-backup].sql.gz

# 5. Verify data integrity
kubectl exec -n default deployment/postgres -- psql -U aitbc -d aitbc -c "SELECT COUNT(*) FROM jobs;"

# 6. Restart services
kubectl scale deployment coordinator-api --replicas=3
kubectl scale deployment marketplace --replicas=2
kubectl scale deployment exchange --replicas=2

# 7. Verify system health
curl -s http://coordinator-api:8011/v1/health
```

**Verification Steps:**
1. Check database connectivity
2. Verify job data integrity
3. Test API endpoints
4. Monitor error rates
5. Validate user access

#### Service Failure Recovery

```bash
# 1. Check service status
kubectl get pods -n default
kubectl describe deployment [service-name]

# 2. Check service logs
kubectl logs -l app=[service-name] --tail=100

# 3. Restart affected service
kubectl rollout restart deployment [service-name]

# 4. If restart fails, scale down and up
kubectl scale deployment [service-name] --replicas=0
kubectl scale deployment [service-name] --replicas=[original-count]

# 5. Verify service health
kubectl exec -n default deployment/[service-name] -- curl -s http://localhost:[port]/v1/health
```

**Verification Steps:**
1. Check pod status
2. Verify service endpoints
3. Test critical functionality
4. Monitor service metrics

#### Network Partition Recovery

```bash
# 1. Diagnose network issue
kubectl get pods -n default -o wide
kubectl exec -n default [pod-name] -- ping [target-host]
kubectl exec -n default [pod-name] -- traceroute [target-host]

# 2. Check network policies
kubectl get networkpolicies -n default

# 3. Check DNS resolution
kubectl exec -n default [pod-name] -- nslookup [service-name]

# 4. Restart affected services if needed
kubectl rollout restart deployment [service-name]

# 5. Verify connectivity
kubectl exec -n default [pod-name] -- curl -s http://[service-name]:[port]/v1/health
```

**Verification Steps:**
1. Verify network connectivity
2. Test DNS resolution
3. Check service communication
4. Verify data synchronization

#### Data Center Outage Recovery

```bash
# 1. Activate alternate data center
kubectl config use-context [alt-cluster-context]

# 2. Verify alternate cluster health
kubectl get nodes
kubectl get pods -A

# 3. Restore from backup if needed
aws s3 cp s3://aitbc-backups-alt/[latest-backup].sql.gz /tmp/
./infra/scripts/restore_postgresql.sh alt /tmp/[latest-backup].sql.gz

# 4. Update DNS to point to alternate data center
aws route53 change-resource-record-sets --hosted-zone-id [zone-id] --change-batch [change-batch]

# 5. Verify service availability
curl -s https://api.aitbc.io/v1/health
```

**Verification Steps:**
1. Verify alternate cluster health
2. Test DNS propagation
3. Verify service availability
4. Monitor system performance

#### Security Breach Recovery

```bash
# 1. Contain breach
sudo systemctl stop [affected-service]
iptables -A INPUT -s [attacker-ip] -j DROP

# 2. Preserve forensic evidence
sudo cp -r /var/log /tmp/forensic-logs
sudo journalctl -u [affected-service] > /tmp/forensic-logs/service.log

# 3. Identify compromise scope
grep -r "malicious" /var/log/
check system logs for suspicious activity

# 4. Patch vulnerabilities
./infra/scripts/apply-security-patches.sh

# 5. Restore from pre-breach backup
aws s3 cp s3://aitbc-backups/[pre-breach-backup].sql.gz /tmp/
./infra/scripts/restore_postgresql.sh default /tmp/[pre-breach-backup].sql.gz

# 6. Restart services
kubectl scale deployment [affected-service] --replicas=[original-count]

# 7. Monitor for re-infection
./scripts/monitoring/security-monitor.sh
```

**Verification Steps:**
1. Verify breach containment
2. Validate patch application
3. Verify data integrity
4. Monitor for suspicious activity
5. Conduct security audit

#### Ransomware Attack Recovery

```bash
# 1. Isolate infected systems
kubectl scale deployment --all --replicas=0
kubectl cordon [node-name]

# 2. Identify infection scope
find /app/data -name "*.encrypted"
grep -r "ransomware" /var/log/

# 3. Wipe and rebuild systems
./infra/scripts/rebuild-systems.sh

# 4. Restore from clean backup
aws s3 cp s3://aitbc-backups/[clean-backup].tar.gz /tmp/
tar -xzf /tmp/[clean-backup].tar.gz -C /app/data/

# 5. Verify no ransomware remains
./scripts/security/ransomware-scan.sh

# 6. Restart services
kubectl scale deployment --all --replicas=[original-counts]

# 7. Implement additional security measures
./infra/scripts/harden-security.sh
```

**Verification Steps:**
1. Verify system cleanliness
2. Validate data integrity
3. Test all services
4. Monitor for re-infection
5. Conduct security audit

### Post-Recovery Steps

1. **Verify System Health**
   - Check all services are running
   - Verify data integrity
   - Test critical functionality
   - Monitor error rates

2. **Document Incident**
   - Create incident report
   - Document root cause
   - Record recovery actions
   - Identify lessons learned

3. **Update Procedures**
   - Update disaster recovery plan
   - Improve monitoring/alerting
   - Add new prevention measures
   - Update runbooks

4. **Communicate Resolution**
   - Notify stakeholders
   - Update status page
   - Send post-mortem to team
   - Close incident ticket

## Communication Plan

### Internal Communication

#### During Incident
- **Primary Channel:** Slack #incidents
- **Backup Channel:** Phone call
- **Frequency:** Every 15-30 minutes
- **Content:** Status updates, ETA, blockers

#### After Incident
- **Primary Channel:** Email + Slack
- **Timing:** Within 24 hours
- **Content:** Post-mortem, lessons learned, action items

### External Communication

#### Customers
- **Channel:** Status page, email
- **Timing:** P1/P2: Immediate; P3/P4: Within 4 hours
- **Content:** Incident description, impact, ETA, resolution

#### Stakeholders
- **Channel:** Email, phone
- **Timing:** P1/P2: Within 1 hour; P3/P4: Within 4 hours
- **Content:** Business impact, recovery status, financial impact

#### Public
- **Channel:** Status page, social media (if major incident)
- **Timing:** Only for major incidents (P1)
- **Content:** High-level status, no technical details

### Communication Templates

#### Initial Incident Notification (Internal)
```
INCIDENT DECLARED - [Severity] - [Service]

Summary: [Brief description]
Impact: [Affected users/services]
Started: [Timestamp]
Owner: [On-call engineer]
Slack: #incidents-[ticket-number]
```

#### Customer Notification
```
Service Incident - [Service Name]

We are currently experiencing an issue affecting [service].
Our team is actively working to resolve this.
We will provide updates every 30 minutes.

Status: [Current status]
Started: [Timestamp]
```

#### Resolution Notification
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

## Failover Mechanisms

### Service Failover

#### Kubernetes Pod Failover
- **Mechanism:** Kubernetes automatically restarts failed pods
- **Configuration:** Pod replicas set to 3+ for critical services
- **Health Checks:** Liveness and readiness probes configured
- **Failover Time:** <5 minutes

#### Database Failover
- **Mechanism:** PostgreSQL streaming replication
- **Configuration:** Primary + 2 standby replicas
- **Failover Trigger:** Automated via Patroni
- **Failover Time:** <2 minutes

#### Redis Failover
- **Mechanism:** Redis Sentinel
- **Configuration:** Master + 2 slaves + 3 sentinels
- **Failover Trigger:** Automatic via Sentinel
- **Failover Time:** <30 seconds

### Geographic Failover

#### Data Center Failover
- **Mechanism:** Multi-region deployment
- **Configuration:** Active-active or active-passive
- **Failover Trigger:** Manual or automated (based on health checks)
- **Failover Time:** <4 hours

#### DNS Failover
- **Mechanism:** Route53 health checks + DNS failover
- **Configuration:** Multi-region DNS records
- **Failover Trigger:** Automatic health checks
- **Failover Time:** <5 minutes (DNS propagation)

### Data Failover

#### Blockchain State Synchronization
- **Mechanism:** Peer-to-peer blockchain sync
- **Configuration:** Multiple nodes in different regions
- **Failover Trigger:** Automatic via consensus
- **Failover Time:** Depends on chain height (typically <1 hour)

## Backup Procedures

### Backup Schedule

| Component | Frequency | Time (UTC) | Type | Retention |
|-----------|-----------|------------|------|-----------|
| PostgreSQL | Daily | 02:00 | Full | 30 days |
| PostgreSQL | Weekly | 02:00 Sunday | Full | 90 days |
| Redis | Daily | 02:01 | Full | 30 days |
| Ledger | Daily | 02:02 | Full + Incremental | 30 days |
| Configuration | On change | - | Full | 90 days |

### Backup Verification

1. **Automated Verification**
   - Check backup completion via monitoring
   - Validate backup integrity via checksums
   - Test restore monthly (automated)

2. **Manual Verification**
   - Quarterly full restore test
   - Annual disaster recovery drill
   - Document verification results

### Backup Locations

- **Primary:** S3 (us-east-1)
- **Secondary:** S3 (us-west-2)
- **Tertiary:** On-premise backup server
- **Encryption:** Server-side encryption (AES-256)
- **Access:** IAM-restricted, audit-logged

## Disaster Recovery Drills

### Drill Schedule

| Drill Type | Frequency | Duration | Participants |
|------------|-----------|----------|--------------|
| Tabletop Exercise | Quarterly | 2 hours | Engineering, Ops, Security |
| Service Failover | Monthly | 1 hour | DevOps |
| Database Restore | Monthly | 1 hour | DBA, DevOps |
| Full System Recovery | Quarterly | 4 hours | All teams |
| Data Center Failover | Annually | 8 hours | All teams |

### Drill Procedures

#### Pre-Drill Preparation
1. Define drill scenario and objectives
2. Notify participants in advance
3. Prepare test environment (if needed)
4. Set up monitoring and logging
5. Establish success criteria

#### During Drill
1. Execute drill according to scenario
2. Document actions and timing
3. Record issues and blockers
4. Monitor system behavior
5. Communicate progress

#### Post-Drill Review
1. Collect metrics and observations
2. Identify gaps and improvements
3. Update procedures and documentation
4. Share lessons learned
5. Schedule follow-up actions

### Drill Report Template

```
Disaster Recovery Drill Report

Date: [Date]
Type: [Drill Type]
Scenario: [Description]
Participants: [Names]

Objectives:
- [Objective 1]
- [Objective 2]

Results:
- Success Criteria: [Met/Not Met]
- RTO Achieved: [Time]
- RPO Achieved: [Time]

Issues Encountered:
- [Issue 1]
- [Issue 2]

Lessons Learned:
- [Lesson 1]
- [Lesson 2]

Action Items:
- [Action 1] - [Owner] - [Due Date]
- [Action 2] - [Owner] - [Due Date]

Next Drill: [Date]
```

## Metrics and Monitoring

### Key Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Backup Success Rate | >99% | Daily |
| Restore Success Rate | 100% | Monthly test |
| RTO Achievement | <Target | Per incident |
| RPO Achievement | <Target | Per incident |
| Drill Participation | 100% | Per drill |

### Monitoring

#### Backup Monitoring
- Backup completion status
- Backup size and duration
- Backup integrity checks
- Storage capacity

#### Recovery Monitoring
- Recovery time tracking
- Recovery success rate
- System health post-recovery
- Error rates post-recovery

#### Drill Monitoring
- Drill completion rate
- Drill success rate
- Participant feedback
- Action item completion

## Maintenance

### Plan Review
- **Frequency:** Quarterly
- **Owner:** Operations Manager
- **Participants:** Engineering, DevOps, Security
- **Output:** Updated plan version

### Contact Updates
- **Frequency:** Monthly
- **Owner:** HR/Operations
- **Process:** Verify all contacts are current

### Procedure Updates
- **Frequency:** As needed
- **Trigger:** System changes, incident lessons learned
- **Process:** Update documentation, notify team

## Appendix

### A. Quick Reference Card

```
EMERGENCY CONTACTS:
CTO: [Phone]
Engineering Lead: [Phone]
On-call: [Phone]

CRITICAL COMMANDS:
Check status: kubectl get pods -A
Check logs: kubectl logs -l app=[service]
Restart: kubectl rollout restart deployment [service]
Scale: kubectl scale deployment [service] --replicas=N

BACKUP RESTORE:
PostgreSQL: ./infra/scripts/restore_postgresql.sh default [backup]
Redis: kubectl cp [backup] default/redis-0:/data/dump.rdb
Ledger: tar -xzf [backup] -C /tmp/ && kubectl cp /tmp/chain/ default/node:/app/data/

DNS FAILOVER:
aws route53 change-resource-record-sets --hosted-zone-id [id] --change-batch [batch]
```

### B. Incident Response Checklist

- [ ] Assess impact and severity
- [ ] Declare incident and notify on-call
- [ ] Create incident ticket
- [ ] Activate incident response team
- [ ] Contain incident
- [ ] Begin recovery procedures
- [ ] Communicate with stakeholders
- [ ] Monitor recovery progress
- [ ] Verify system health
- [ ] Document incident
- [ ] Post-incident review
- [ ] Update procedures
- [ ] Close incident ticket

### C. Change History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-11 | Initial creation | |

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| CTO | | | |
| Engineering Lead | | | |
| DevOps Lead | | | |
| Security Lead | | | |
| Operations Manager | | | |
