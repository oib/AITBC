---
description: Deployment Automation Workflow for AITBC Services
---

# Deployment Automation Workflow

This workflow covers the automation of AITBC service deployment with one-command setup.

## Prerequisites

- Linux server with systemd support
- Python 3.13+ installed
- SSH access to target servers
- Domain name configured (for SSL certificates)

## Steps

### 1. System Service One-Command Setup (systemd)

1. **Create systemd service templates**
   - Create service files for each AITBC component:
     - `aitbc-coordinator-api.service`
     - `aitbc-blockchain-node.service`
     - `aitbc-wallet.service`
     - `aitbc-gpu-miner.service`
     - `aitbc-agent-daemon.service`
   - Store templates in `systemd/` directory
   - Include proper dependencies and restart policies

2. **Configure service dependencies**
   - Define startup order (blockchain → coordinator → wallet → miners)
   - Add `After=` and `Requires=` directives
   - Configure automatic restart on failure
   - Set resource limits (CPU, memory)

3. **Create service management script**
   - Script: `scripts/service/manage-services.sh`
   - Commands: start, stop, restart, status, logs
   - Handle multiple services with dependency ordering
   - Include health checks before starting dependent services

### 2. One-Command Deployment Script (`./deploy.sh`)

1. **Create main deployment script**
   - Script: `scripts/deploy/deploy.sh`
   - Make executable: `chmod +x scripts/deploy/deploy.sh`
   - Include error handling and rollback capability

2. **Deployment script functionality**
   ```bash
   # Main deployment steps
   - Check system prerequisites
   - Install dependencies (Python, system packages)
   - Clone or update repository
   - Create virtual environment
   - Install Python dependencies
   - Configure environment variables
   - Initialize databases
   - Start systemd services
   - Run health checks
   - Display deployment status
   ```

3. **Add rollback capability**
   - Backup previous deployment
   - Rollback on failure
   - Restore previous configuration
   - Restart services with old version

### 3. Environment Configuration Templates (.env.example)

1. **Create .env.example template**
   - File: `.env.example` at project root
   - Include all required environment variables
   - Add comments explaining each variable
   - Group variables by service/component

2. **Template sections**
   ```bash
   # Blockchain Configuration
   CHAIN_ID=ait-mainnet
   BLOCKCHAIN_RPC_PORT=8006
   
   # Coordinator API
   COORDINATOR_API_PORT=8001
   COORDINATOR_API_HOST=0.0.0.0
   DATABASE_URL=postgresql://user:pass@localhost/aitbc
   
   # Wallet
   WALLET_DAEMON_PORT=8000
   WALLET_PASSWORD=your_secure_password
   
   # GPU Miner
   MINER_API_KEY=your_api_key
   MINER_GPU_DEVICE=0
   ```

3. **Create validation script**
   - Script: `scripts/deploy/validate-env.sh`
   - Check all required variables are set
   - Validate variable formats (ports, URLs)
   - Test database connectivity
   - Verify API keys are valid format

### 4. Service Health Checks and Monitoring

1. **Create health check endpoints**
   - Add `/health/live` endpoint to each service
   - Add `/health/ready` endpoint for readiness checks
   - Return JSON with service status and dependencies

2. **Create monitoring script**
   - Script: `scripts/monitoring/health-check.sh`
   - Check all service health endpoints
   - Monitor service resource usage (CPU, memory, disk)
   - Alert on service failures
   - Log health check results

3. **Integrate with systemd**
   - Add `ExecStartPost=` for health checks
   - Configure restart on health check failure
   - Use systemd notify for service readiness

### 5. Manual SSL Certificate Handling

- SSL certificate provisioning and renewal are handled manually outside this workflow.
- Configure nginx with manually issued certificates as needed.

## Verification

- [ ] All systemd services start in correct order
- [ ] Deployment script completes successfully
- [ ] .env.example template is complete
- [ ] Health checks pass for all services
- [ ] SSL certificates are configured manually and services are accessible via HTTPS
- [ ] Rollback capability tested

## Troubleshooting

- **Service fails to start**: Check logs with `journalctl -u service-name`, verify dependencies
- **Deployment script fails**: Check error logs, verify prerequisites, test individual steps
- **Health checks fail**: Verify service is running, check endpoint configuration
- **SSL configuration fails**: Check domain DNS, verify nginx config, and confirm the manually issued certificate paths
- **Environment validation fails**: Verify all required variables are set, check formats

## Related Files

- `systemd/*.service`
- `scripts/deploy/deploy.sh`
- `.env.example`
- `scripts/deploy/validate-env.sh`
- `scripts/monitoring/health-check.sh`
- `nginx/nginx.conf`
