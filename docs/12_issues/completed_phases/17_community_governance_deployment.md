# OpenClaw Community & Governance Deployment Guide

## 1. Overview
This guide covers the deployment and initialization of the OpenClaw Community Platform and Decentralized Governance (DAO) systems implemented in Phase 10 (Weeks 13-18).

## 2. Components Deployed
1. **Developer Ecosystem**: Developer profiles, skills tracking, SDK releases.
2. **Third-Party Marketplace**: Publication and purchasing of agent solutions.
3. **Innovation Labs**: Collaborative, crowdfunded open-source research.
4. **Community Platform**: Discussion forums and hackathon management.
5. **Decentralized Governance (DAO)**: Proposals, voting, liquid democracy, and treasury execution.

## 3. Database Initialization
Run the Alembic migrations to apply the new schema changes for `domain/community.py` and `domain/governance.py`.
\`\`\`bash
cd /home/oib/windsurf/aitbc/apps/coordinator-api
alembic revision --autogenerate -m "Add community and governance models"
alembic upgrade head
\`\`\`

## 4. API Registration
Ensure the new routers are included in the main FastAPI application (`main.py`):
\`\`\`python
from app.routers import community
from app.routers import governance

app.include_router(community.router)
app.include_router(governance.router)
\`\`\`

## 5. Genesis Setup for DAO
To bootstrap the DAO, an initial treasury funding and admin roles must be established.

### 5.1 Initialize Treasury
\`\`\`sql
INSERT INTO dao_treasury (treasury_id, total_balance, allocated_funds, last_updated) 
VALUES ('main_treasury', 1000000.0, 0.0, NOW());
\`\`\`

### 5.2 Create Foundation Profile
Using the API:
\`\`\`bash
curl -X POST "http://localhost:8000/v1/governance/profiles" \
     -H "Content-Type: application/json" \
     -d '{"user_id": "foundation_genesis", "initial_voting_power": 100000.0}'
\`\`\`

## 6. Monitoring & Maintenance
- **Transparency Reports**: Configure a cron job or Celery task to hit the `/v1/governance/analytics/reports` endpoint at the end of every quarter.
- **Hackathon Management**: Ensure community moderators with tier `EXPERT` or higher are assigned to review and approve hackathon events.

## 7. Next Steps
The core marketplace and governance systems are now complete. The platform is ready for comprehensive security auditing and production scaling.
